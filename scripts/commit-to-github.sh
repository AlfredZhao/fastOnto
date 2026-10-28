#!/usr/bin/env bash
# Commit all project changes and optionally publish an annotated version tag.
# Never changes remote configuration, pulls, rebases, force-pushes or resets.
set -euo pipefail
export GIT_OPTIONAL_LOCKS=0

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PROJECT_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd -P)"
REMOTE="${GIT_REMOTE:-origin}"
MESSAGE=''
VERSION=''
NO_TAG=0
NO_PUSH=0
SKIP_BUILD=0
DRY_RUN=0

usage() {
  cat <<'USAGE'
用法：scripts/commit-to-github.sh [提交说明] [选项]

  -m, --message MSG    提交说明；默认 Update fastOnto <本机时间>
  --version X.Y.Z     创建附注标签 vX.Y.Z（也接受 vX.Y.Z）
  -t, --tag X.Y.Z     --version 的别名；默认提交说明 Release X.Y.Z
  --no-tag            不创建/推送标签，与参数顺序无关
  --no-push           只在本地 commit/tag，不需要配置远端
  --remote NAME       指定已配置的远端名；默认 GIT_REMOTE 或 origin
  --skip-build        跳过 frontend 的 npm run build
  --dry-run           离线预览；不构建、不暂存、不提交、不打标签、不推送
  -h, --help          显示帮助

默认将整个项目的非忽略新增/修改/删除一起提交，然后推送当前同名分支。
首次提交支持；无文件变化时不造空提交，仍可打标签/重试推送。
已有同名标签只在工作区干净且指向当前 HEAD 时复用，绝不移动标签。
发布仅创建 Git 标签；不自动改写 CHANGELOG.md、包版本或创建 GitHub Release。
远端地址、Git 作者身份与 SSH/凭据助手需自行配置。不要把令牌写入远端 URL。

示例：
  bash scripts/commit-to-github.sh --dry-run
  bash scripts/commit-to-github.sh -m "完善模型工作台" --no-push
  bash scripts/commit-to-github.sh --version 0.2.0 -m "Release 0.2.0"
USAGE
}

fail() { printf '错误：%s\n' "$*" >&2; exit 1; }
argument_error() { printf '参数错误：%s\n' "$*" >&2; exit 2; }
require_value() { [[ $# -ge 2 && -n "$2" ]] || argument_error "$1 缺少参数值"; }

while (($#)); do
  case "$1" in
    -m|--message) require_value "$@"; [[ -z "$MESSAGE" ]] || argument_error '提交说明只能指定一次'; MESSAGE="$2"; shift 2 ;;
    --version|--tag|-t) require_value "$@"; [[ -z "$VERSION" ]] || argument_error '版本只能指定一次'; VERSION="$2"; shift 2 ;;
    --remote) require_value "$@"; REMOTE="$2"; shift 2 ;;
    --no-tag) NO_TAG=1; shift ;;
    --no-push) NO_PUSH=1; shift ;;
    --skip-build) SKIP_BUILD=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; [[ -z "$MESSAGE" ]] || argument_error '提交说明只能指定一次'; MESSAGE="$*"; break ;;
    -*) argument_error "未知选项 $1" ;;
    *) [[ -z "$MESSAGE" ]] || argument_error '多词提交说明请用引号包裹或使用 --'; MESSAGE="$1"; shift ;;
  esac
done

[[ "$REMOTE" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || argument_error '--remote/GIT_REMOTE 必须为远端名称，不能是 URL'
TAG=''
if [[ -n "$VERSION" ]]; then
  VERSION="${VERSION#v}"
  [[ "$VERSION" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || argument_error '版本必须为 X.Y.Z 或 vX.Y.Z，例如 0.2.0'
  ((NO_TAG)) || TAG="v$VERSION"
fi
if [[ -z "$MESSAGE" ]]; then
  if [[ -n "$VERSION" ]]; then MESSAGE="Release $VERSION"; else MESSAGE="Update fastOnto $(date '+%Y-%m-%d %H:%M:%S')"; fi
fi

command -v git >/dev/null || fail '找不到 git'
# Do not let inherited Git plumbing variables redirect writes to another index/repo.
for name in GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES; do
  [[ -z "${!name:-}" ]] || fail "请先取消环境变量 $name，避免操作其他仓库或索引"
done
cd -- "$PROJECT_ROOT"
top="$(git rev-parse --show-toplevel 2>/dev/null)" || fail '项目尚未初始化 Git；请先手工 git init'
[[ "$(cd -- "$top" && pwd -P)" == "$PROJECT_ROOT" ]] || fail '脚本所在项目不是 Git 仓库根目录，拒绝操作父仓库'
BRANCH="$(git symbolic-ref --quiet --short HEAD)" || fail '当前为 detached HEAD，请先切回分支'
HEAD_BEFORE="$(git rev-parse --verify HEAD 2>/dev/null || true)"
for operation in MERGE_HEAD CHERRY_PICK_HEAD REVERT_HEAD rebase-merge rebase-apply BISECT_LOG; do
  [[ ! -e "$(git rev-parse --git-path "$operation")" ]] || fail "存在未完成的 Git 操作：$operation，请先手工处理"
done
[[ -z "$(git ls-files --unmerged)" ]] || fail '存在未解决的合并冲突'

# A dry run does not even create a repository lock file or refresh the index.
if ((!DRY_RUN)); then
  command -v flock >/dev/null || fail '缺少 flock（util-linux）'
  common="$(git rev-parse --git-common-dir)"
  exec 9>"$common/fastonto-publish.lock"
  flock -n 9 || fail '已有提交/发布脚本正在运行，请稍后重试'
fi

blocked_path() {
  local path="$1" base="${1##*/}"
  case "/$path/" in
    */.runtime/*|*/logs/*|*/.aws/*|*/.ssh/*|*/.codegraph/*|*/node_modules/*|*/__pycache__/*|*/.pytest_cache/*|*/.venv/*|*/dist/*|*/test-results/*|*/playwright-report/*|*/reference/*) return 0 ;;
  esac
  case "$base" in
    .env.example) return 1 ;;
    .env|.env.*|.git-credentials|.netrc|*.key|*.pem|*.p12|*.pfx|*.jks|id_rsa|id_ed25519|id_ecdsa|*.log|nohup.out*|*.py[cod]|*.pid) return 0 ;;
  esac
  return 1
}

check_paths() {
  local path mode="${1:-worktree}" bad=0
  while IFS= read -r -d '' path; do
    # A deleted worktree file will be removed by add -A, not published again.
    if [[ "$mode" == worktree && ! -e "$path" && ! -L "$path" ]]; then continue; fi
    if blocked_path "$path"; then
      printf '禁止提交的敏感/运行产物路径：%q\n' "$path" >&2
      bad=1
    fi
  done
  ((bad == 0)) || fail '请先检查忽略规则/已跟踪文件；脚本不会替你删除文件或取消暂存。这不是完整的密钥扫描。'
}

check_worktree_paths() { check_paths worktree < <(git ls-files -z --cached --others --exclude-standard); }
check_tag() {
  [[ -n "$TAG" ]] || return 0
  if git show-ref --verify --quiet "refs/tags/$TAG"; then
    local target head
    target="$(git rev-parse --verify "refs/tags/$TAG^{commit}" 2>/dev/null)" || fail '已有标签不是提交标签，拒绝修改'
    head="$(git rev-parse --verify HEAD 2>/dev/null)" || fail '没有 HEAD，不能复用标签'
    [[ "$target" == "$head" && -z "$(git status --porcelain --untracked-files=all)" ]] || fail "标签 $TAG 已存在且不满足干净 HEAD 复用条件；请选择新版本"
  fi
}
check_worktree_paths
check_tag

REMOTE_READY=0
if git remote get-url "$REMOTE" >/dev/null 2>&1; then
  REMOTE_READY=1
elif ((!NO_PUSH && !DRY_RUN)); then
  fail "未配置远端 $REMOTE；请先手工配置，或使用 --no-push / --dry-run"
fi
if ((!NO_PUSH && REMOTE_READY)); then
  # get-url expands insteadOf/pushInsteadOf. Do not echo URLs (they may contain secrets).
  urls="$(git remote get-url --push --all "$REMOTE")"
  [[ -n "$urls" && "$urls" != *$'\n'* ]] || fail '只支持一个推送地址，避免多地址发布部分成功'
  case "$urls" in
    http://*|https://*)
      authority="${urls#*://}"; authority="${authority%%/*}"
      [[ "$authority" != *@* && "$urls" != *\?* && "$urls" != *\#* ]] || fail '远端 HTTP URL 含用户信息或参数；请改用 SSH/凭据助手，不要在 URL 写令牌' ;;
    ssh://*) authority="${urls#ssh://}"; authority="${authority%%/*}"; [[ ! "$authority" =~ :[^@]*@ ]] || fail 'SSH URL 不应包含密码' ;;
  esac
  [[ "$(git config --bool --get "remote.$REMOTE.mirror" || true)" != true ]] || fail '拒绝 mirror 远端，避免意外推送其他引用'
fi

printf '项目：%s\n分支：%s\n远端：%s（仅显示名称，不显示地址）\n' "$PROJECT_ROOT" "$BRANCH" "$REMOTE"
[[ -z "$TAG" ]] || printf '版本标签：%s\n' "$TAG"
printf '将包含全部非忽略的新增、修改和删除（并非仅当前暂存内容）：\n'
git status --short --untracked-files=all
git --no-pager diff --stat
git --no-pager diff --cached --stat
git diff --check >/dev/null 2>&1 || fail '未暂存差异有空白或冲突标记问题；请本机运行 git diff --check 检查'
git diff --cached --check >/dev/null 2>&1 || fail '暂存差异有空白或冲突标记问题；请本机运行 git diff --cached --check 检查'

if ((DRY_RUN)); then
  ((REMOTE_READY || NO_PUSH)) || printf '提示：尚未配置远端；正式推送前需配置，预演不联网验证。\n'
  if ((!SKIP_BUILD)) && [[ -f frontend/package.json ]]; then printf '正式执行将运行 npm run build；预演不运行构建。\n'; fi
  printf '预演完成：未构建、暂存、提交、打标签、改写 CHANGELOG 或推送。\n'
  exit 0
fi

if ((!SKIP_BUILD)) && [[ -f frontend/package.json ]]; then
  command -v npm >/dev/null || fail '找不到 npm；请加载 Node 环境，或显式 --skip-build'
  (cd frontend && npm run build 9>&-) || fail '前端构建失败；尚未由本脚本暂存/提交'
fi
check_worktree_paths
check_tag

[[ "$(git symbolic-ref --quiet --short HEAD || true)" == "$BRANCH" && "$(git rev-parse --verify HEAD 2>/dev/null || true)" == "$HEAD_BEFORE" ]] || fail '校验/构建期间分支或 HEAD 已变化；请检查后重试，不会继续暂存或提交'

changes="$(git status --porcelain --untracked-files=all)"
if [[ -n "$changes" || -n "$TAG" ]]; then
  git var GIT_AUTHOR_IDENT >/dev/null 2>&1 && git var GIT_COMMITTER_IDENT >/dev/null 2>&1 || fail 'Git 作者身份未配置，请设置 user.name / user.email'
fi
if [[ -n "$changes" ]]; then
  git add -A -- . || fail '暂存失败；请检查原有暂存区，脚本不会自动 reset'
  check_paths index < <(git ls-files -z --cached)
  git diff --cached --check >/dev/null 2>&1 || fail '包含新文件的暂存差异检查失败；已暂存但未提交，请手工检查'
  if ! git diff --cached --quiet; then
    git commit -m "$MESSAGE" 9>&- || fail '提交失败；保留暂存区，不自动撤销用户修改'
  fi
else
  printf '没有文件变更，不创建空提交。\n'
fi
git rev-parse --verify HEAD >/dev/null 2>&1 || fail '仓库仍无提交，无法创建标签或推送'
# Hooks are user-controlled; check the resulting committed file names again before publishing.
check_paths head < <(git ls-tree -r -z --name-only HEAD)
if [[ -n "$TAG" ]] && ! git show-ref --verify --quiet "refs/tags/$TAG"; then
  git tag -a "$TAG" -m "Release $VERSION" 9>&- || fail '标签创建失败；本地提交已保留，未推送'
fi
[[ "$(git symbolic-ref --quiet --short HEAD || true)" == "$BRANCH" ]] || fail '提交期间分支已变化；保留本地结果，拒绝推送'
if [[ -n "$TAG" ]]; then
  [[ "$(git rev-parse --verify "refs/tags/$TAG^{commit}" 2>/dev/null || true)" == "$(git rev-parse HEAD)" ]] || fail '版本标签未指向本次 HEAD；保留本地结果，拒绝推送'
fi
if ((NO_PUSH)); then
  printf '本地操作完成；--no-push 未连接远端。\n'
else
  refs=("HEAD:refs/heads/$BRANCH")
  [[ -z "$TAG" ]] || refs+=("refs/tags/$TAG:refs/tags/$TAG")
  # Explicit destination, no force, no unrelated followTags. Branch + chosen tag
  # must be accepted together; do not fall back to a partially successful push.
  git -c push.followTags=false push --atomic --set-upstream "$REMOTE" "${refs[@]}" 9>&- || fail '推送失败或未能确认完成；本地提交/标签保留。请检查远端状态后重试，不会自动强推或回滚'
  printf '推送完成：%s / %s\n' "$REMOTE" "$BRANCH"
fi
printf '当前提交：'
git rev-parse --short HEAD
[[ -z "$TAG" ]] || printf '标签：%s\n' "$TAG"
