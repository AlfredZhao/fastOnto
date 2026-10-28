# Git 提交与版本标签脚本

入口：`scripts/commit-to-github.sh`，参考 trustedKnowledge 的同名脚本，适配 fastOnto 的初始仓库和安全边界。此功能仅为本机 CLI，没有新增可远程执行 Git 的业务接口。

## 用法

```bash
# 首先离线查看将包含哪些文件
bash scripts/commit-to-github.sh --dry-run

# 本地 commit，不推送，不要求远端
bash scripts/commit-to-github.sh -m "完善文档导入" --no-push

# commit 后推送当前分支
bash scripts/commit-to-github.sh -m "完善服务脚本"

# commit（如有变更）+ 附注标签 v0.2.0 + 原子推送分支及此标签
bash scripts/commit-to-github.sh --version 0.2.0
# --tag / -t 是 --version 的别名，版本也接受 v0.2.0
bash scripts/commit-to-github.sh --tag v0.2.0 -m "Release 0.2.0"

# 其他选项
bash scripts/commit-to-github.sh --version 0.2.1 --no-tag
bash scripts/commit-to-github.sh --remote origin --skip-build -m "仅文档更新"
bash scripts/commit-to-github.sh --help
```

脚本从自身位置定位项目根目录，从 `scripts/` 或其他目录调用均可。无需 Conda/Python；依赖 Bash、Git、flock，默认构建时还需要 npm 和已安装的前端依赖。脚本不自动安装依赖。

**提交范围是整个项目全部非忽略的新增、修改和删除，不是仅暂存区。** 原先分段暂存的改动也会合并纳入此次提交，执行前应审阅文件；不适合仅提交部分文件的操作，部分提交请使用原生 Git。

## 首次使用

脚本不会自动 git init、配置作者、添加远端或重命名分支。项目若尚无首个提交，仍可正常工作；当前分支是什么就推送同名分支，不假设一定为 main。

按自己的实际信息在本机配置，例如：

```bash
# 只有未初始化时才需要 git init
# git init

git config user.name "你的名字"
git config user.email "你的邮箱"

# 已有 origin 时不要重复 add；请自行确认目标仓库
# 使用 SSH 或 Git 凭据助手，不要在地址中嵌入令牌
# git remote add origin git@github.com:YOUR_ACCOUNT/fastOnto.git
```

没有远端时仍可 `--dry-run` 或 `--no-push`。默认远端为 origin，可用 `--remote NAME` 或环境变量 `GIT_REMOTE` 指定已配置远端；不会创建 GitHub 仓库、获取 SSH 密钥、读取凭据文件或提取保存密码。

## 行为与参考脚本的差异

- 默认提交说明为 `Update fastOnto <本机日期时间>`；版本模式为 `Release X.Y.Z`。版本仅接受不含前导零的 X.Y.Z/vX.Y.Z，不支持预发布后缀。
- 默认先 `npm run build`，再暂存/提交；`--skip-build` 可跳过。构建检查不等于完整回归，请发布前另行运行 `bash scripts/check.sh`。
- **dry-run 完全离线**，不构建、不建发布锁、不刷新索引、不暂存/提交/打标签/推送；只检查本地状态、已有差异和路径，不保证远端可写或构建通过。未跟踪文件的完整 diff 检查在正式暂存后进行。
- `--version` 创建附注标签，不自动新增或更新 `CHANGELOG.md` 的版本章节，也不修改 pyproject.toml、package.json 等版本号。请自行更新并一同提交。它不是 GitHub Release 页面/API 发布功能。
- `--no-tag` 与参数顺序无关，只禁用标签；不会写入或重排 CHANGELOG。
- 没有文件变更时不造空提交，但仍可给当前提交打标签、推送此前未推送的提交，或重试失败的发布。
- 已有同名本地标签仅在工作区干净且指向当前 HEAD 时复用（用于重试），不会移动/删除标签。存在新修改或标签指向别处时明确失败。
- detached HEAD、未完成 merge/rebase/cherry-pick/revert/bisect、未解决冲突、异常 Git 索引/目录环境变量都会被拒绝。发布脚本之间用排他锁防止并发；不要同时手工修改 Git 分支/索引。构建期间分支或 HEAD 发生变化会停止后续提交。
- 推送始终明确使用选定远端和当前同名分支，不因旧 upstream 推到另一个仓库；成功后设置对应 upstream。
- 使用 `git push --atomic` 一次推送分支和指定标签，关闭隐式 followTags，不推其他标签、不强推。只支持一个推送地址；服务器不支持 atomic 或拒绝任何引用时返回失败，不降级为多步部分推送。
- 不自动 pull、fetch、rebase、reset 或删除本地提交/标签。远端领先/分叉或受保护时，需用户自行处理。

## 文件与凭据防护

`.gitignore` 排除 .env、日志、运行状态、Python 缓存、依赖/构建产物；本次补充 nohup.out、常见密钥文件和本机凭据目录。原有 reference/ 忽略规则保留。

脚本还检查候选文件、暂存结果和最终提交树的路径，拒绝 .env（允许 .env.example）、.runtime、logs、.aws、.ssh、私钥、nohup 输出、pyc、node_modules、dist、reference 等敏感/本地产物，即使有人用 `git add -f` 强行暂存也会阻止发布。正常删除这些已跟踪文件可提交，但不会清理过去的提交历史。

**这是路径防误提交，不是完整密钥扫描。** 源码、说明文档、.env.example 或历史提交仍可能被人写入真实密钥；必须自行审阅，已泄露凭据须另行轮换并处理历史。脚本不会打印文件内容或远端地址；发现 HTTP URL 内嵌用户信息/令牌参数时拒绝推送。Git/构建输出仍遵循本机配置，请勿将凭据写入提交说明、钩子或构建日志。

## 失败与重试

- 缺少远端、作者身份或构建失败：本脚本尚未暂存/提交（构建本身可能生成其产物）。
- 新文件暂存后 diff 校验或 commit 失败：暂存区可能已变化，保留现场，不自动 reset。
- commit 已完成但 tag/push 失败：本地提交/标签保留，明确返回非零。网络错误可能发生在远端已接收之后，必须先核对远端状态。
- 修复网络/权限/远端问题后，可在工作区干净且标签仍指向 HEAD 的情况下用相同版本重试；不会因此产生重复提交。若已继续开发，应先人工决定发布哪个提交，不要强行覆盖版本标签。

测试只在临时仓库和本机 bare 远端执行，不访问 GitHub，不提交或推送 fastOnto 当前仓库。
