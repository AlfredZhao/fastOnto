# fastOnto

LinkML + FastAPI + React + Oracle 26ai 的本体工作台基础版本。

**原则：本体平台管理语义，不接管业务数据。SH 只读直连，不修改表结构或业务记录，不默认复制业务数据。**

## 首次操作示例

从 **新建模型 → 标准与发布机构** 开始，按 `docs/tutorial-standards.md` 练习类、属性、关系、IRI、校验和版本。示例不是完整标准本体；不改动 SH，也不自动发布映射。创建新草稿前请保存或下载原稿。

外部文档建模见 `docs/document-import.md`：**导入文件 → 审核候选 → 生成独立草稿 → 保存版本 → 导出**。可上传 `models/document-dictionary-example.md` 体验。本地规则提取，不调用外部 AI、不保存原文件、不导入业务记录；普通正文不自动推断语义。

围绕“构建、定义、映射、使用”的演示步骤见 `docs/ontology-demo.md`。

## 当前交付范围

- 中文建模工作台：深浅主题、响应式布局、类/属性检查器、模型关系列表。
- 校验后的可拖拽本体关系图；布局按模型校验摘要自动保存到当前浏览器并可恢复默认，属性可展开查看；拖拽仅整理阅读布局，LinkML YAML 仍是唯一可编辑模型主源。
- LinkML YAML 编辑与受限建模子集校验；YAML / JSON Schema / OWL / SHACL 下载。
- 新建模型、模板选择、YAML 导入、另存为独立模型；XLSX / DOCX / Markdown / TXT 导入向导，审核候选类、属性、对象关系与来源位置，生成 LinkML 草稿。
- 模型源码保存到 FASTONTO，追加历史版本；通过 expected_revision 防止覆盖并发修改。
- 业务域内可维护规则、指标、操作的声明式草稿；字段映射可基于同名属性/字段生成待人工审核的自动建议，并可下载应用构建蓝图作为方案交接基线。
- 8 张 SH 核心表的白名单分页预览，保留重复销售记录；金额按十进制字符串输出。
- FASTONTO schema-private RDF 网络 `FO_NET`、R2RML 虚拟图 `FO_SH_V1`。
- 两个普通 SQL View 引用 SH.CUSTOMERS / SH.PRODUCTS，无物化实例副本。
- 系统页可执行固定的产品虚拟 RDF 查询，返回 URI 和 RDF term；不接受用户自定义 SPARQL。
- 数据库用户、Argon2id 密码哈希、登录/退出、首次强制改密、账户改密、CSRF 和可撤销会话。

**尚未实现**：图形拖拽编辑、已有 YAML 的双向结构化表单编辑、任意正文 AI 语义建模、旧版 XLS/DOC 导入、可视化映射编辑、版本差异/回滚 UI、审批发布、业务实例 SHACL 校验、任意 SPARQL 查询台、SSO/MFA、多租户隔离和多人协作。当前是单一可信管理员工作区，不提供公开注册。模型关系列表不是实例图。

## 环境与安装

Python 使用独立 Conda 环境 `fastonto`（Python 3.12），项目依赖已装入该环境。不要使用 base 或 `pip --user`。

在新机器重建：

```bash
conda env create -f environment.yml
conda run -n fastonto python -m pip install -r requirements.lock
conda run -n fastonto python -m pip install --no-deps -e .
cd frontend
npm ci
npx playwright install chromium
```

`requirements.lock` 固定本次解析出的 Python 依赖（包含开发测试依赖）；`frontend/package-lock.json` 固定前端依赖。`environment.yml` 禁用用户级共享 Python 包加载。Node 22.22.3 已验证。

## 配置 Python 数据库连接

SQLcl 保存连接用于人工迁移与验收；后端不会提取其密码，也不会把 SQLcl 当作 HTTP 请求执行器。

```bash
cp -n .env.example .env
chmod 600 .env
```

仅在本机编辑 `.env`：

```dotenv
FASTONTO_DB_USER=FASTONTO
FASTONTO_DB_PASSWORD=在本机填写
FASTONTO_DB_DSN=主机:1521/服务名
```

不要把密码发送到聊天、提交 Git 或放在命令行参数中。DSN 可使用标准 Easy Connect 字符串；不要把 SQLcl 保存连接名 `test_fastonto` 当作 Python DSN（除非它另外也是已配置的 Oracle Net 别名）。修改配置后手工重新启动后端。

所有业务接口（包括模板、校验和导出）现在均需登录。数据库未配置或不可用时登录不能完成，不会返回假业务数据。仅 `/api/health` 提供匿名的最小进程存活检查。

## 登录与 HTTPS 访问

本机已初始化应用账号 `admin`。在服务器终端查看随机临时密码：

```bash
cat .runtime/initial-admin.txt
```

该文件权限为 600，目录为 700，已加入 Git 忽略；不要发送其内容到聊天或日志。数据库只存 Argon2id 哈希。首次登录必须改密，改密后可在“账户安全”再次修改；改密撤销全部旧会话。临时密码改完即失效，本机文件可由你自行删除。

新环境需要先运行迁移，再执行一次：

```bash
conda run -n fastonto python -m app.bootstrap_admin
```

已有 admin 不会被重置。此命令不提供密码找回/覆盖功能。

在本机 `.env` 中填写 HTTPS 部署地址（不要把真实公网域名提交到仓库）：

```dotenv
FASTONTO_PUBLIC_ORIGIN=https://your-server.example:8025
```

HTTPS Gateway 模式下，后端仍只监听 `127.0.0.1:8026`；网关负责 TLS 和前端静态资源。前端代理会覆盖客户端伪造的转发 IP 头，保留 Origin 供后端校验；文件访问限制在 frontend 内，拒绝 .env、.runtime 和密钥文件。

## 数据库迁移与验收

本环境需依次对 `FASTONTO` 应用迁移 001 至 010，详见 `docs/verification.md`。

其他环境或重新验收时，从项目根目录手工执行：

```bash
sql -S /nolog @db/apply.sql
sql -S /nolog @db/verify.sql
```

- 脚本只允许 `FASTONTO` / `ORCLPDB1`；其他部署必须显式审查并调整容器保护条件。
- Oracle DDL 自动提交；中途失败不意味着整体回滚。修复后可重跑同一迁移，不自动删除网络或数据。
- 版本号 001 至 010 已使用；后续变更使用新迁移，不偷偷覆写已有映射或用户密码。
- 迁移 004/005 只建立 FASTONTO 内的业务域、本体和治理草稿元数据；工作空间仅保留为内部扩展容器，不在当前 UI 或 API 中暴露。不会修改 SH，也不会使治理草稿自动变为运行中的 RDF 映射。
- 迁移 006 支持登记外部 Oracle 只读数据源。其 DSN、用户名和密码以 AES-256-GCM 密文保存在 FASTONTO；主密钥仅在本机 `FASTONTO_SOURCE_MASTER_KEY`，不写入数据库、不返回浏览器。HTTPS 下可浏览指定 Schema 的表/视图、字段和有界样例数据，并下载 LinkML 建模候选；不开放任意 SQL。
- 迁移 009 建立受控分析场景元数据，迁移 010 建立维度展示规则元数据；二者只保存 FASTONTO 元数据，不修改 SH。
- 迁移 008 支持配置多个兼容 OpenAI Chat Completions 的 LLM。服务基础地址可为 HTTP 或 HTTPS；API Key 与外部 Oracle 源凭据共用本机 `FASTONTO_SOURCE_MASTER_KEY`，以 AES-256-GCM 密文保存在 FASTONTO；密钥和 API Key 均不返回浏览器。可在“LLM 配置”新增模型、测试连通性并设置默认模型；导入非 YAML 文档时会将文档预处理结果发送给所选模型生成候选，仍须人工审核。
- RDF 网络会创建 Oracle 内部表、索引等对象；这些不是 SH 业务表副本。R2RML 映射本身也以少量元数据三元组保存。
- `https://fastonto.example/` 是本地验证用 URI 命名空间，不进行联网解引用。正式发布前需明确 URI 管理策略。

## 后台启动、停止与重启

```bash
# 项目根目录；默认启动 HTTPS gateway，启动后不占用终端，无需再加 nohup 或 &
bash scripts/start-all.sh
bash scripts/status.sh
bash scripts/stop-all.sh
bash scripts/restart-all.sh

# 也可单独操作：backend / frontend 均有 start、stop、restart、status
bash scripts/start-backend.sh
bash scripts/stop-backend.sh
bash scripts/restart-frontend.sh

# 仅本机 Vite 前端：统一入口加 --local
bash scripts/start-frontend.sh --local
# 重启也需明确 --local；不带该参数的启动/重启默认是已批准的外部 HTTP 模式
bash scripts/restart-frontend.sh --local
```

浏览器打开 `.env` 中 `FASTONTO_PUBLIC_ORIGIN` 指定的地址。FastAPI 在 `127.0.0.1:8026`；匿名 `/docs` 和 `/openapi.json` 已关闭。前端 `/api` 由 Vite 代理。云安全组与主机防火墙必须允许你的来源访问 TCP 8025；不要对外开放 8026。本次没有修改防火墙。

首次切换到新脚本时，如果旧前台/nohup 进程仍占端口，请你先在原终端 Ctrl+C 或按原方式手工停止；新脚本不会按端口杀进程、接管未登记的旧服务。`start-frontend-dev.sh` 仅保留为 `start-frontend.sh --local` 的兼容别名，不再维护独立启动逻辑。

日志在 `logs/backend.log`、`logs/frontend.log`；PID/启动时刻/进程组状态在 `.runtime/services/`，均不提交 Git。启动检查端口和 HTTP 就绪，重复启动不创建第二份进程。停止默认等候 30 秒，超时返回失败并保留状态；确认可强制中断后用 `stop-*.sh --force`。重启严格先调用 stop，成功后才 start；整体停止前端→后端，整体启动后端→前端。

运行要求：Linux（支持 pidfd）、Conda fastonto、Node 和已安装的前端依赖；同一 Unix 用户操作。脚本不安装依赖、不迁移数据库、不变更防火墙或系统 Nginx；HTTPS Gateway 模式的详细参数、失败处理和运维边界见 `docs/service-lifecycle.md`。

## Git 提交与版本标签

```bash
bash scripts/commit-to-github.sh --dry-run
bash scripts/commit-to-github.sh -m "完善模型工作台" --no-push
bash scripts/commit-to-github.sh -m "提交并推送"
bash scripts/commit-to-github.sh --version 0.2.0
```

默认构建前端、提交全部非忽略变更并推送当前分支；版本模式额外创建附注标签。`--no-push` 只做本地操作；`--dry-run` 离线且不构建、不改变 Git 状态。先自行配置 Git 作者和远端 origin，不自动读取凭据或创建 GitHub 仓库。标签发布不会自动改写 CHANGELOG/包版本，也不等于创建 GitHub Release。详见 `docs/github-publish.md`。

## 测试

```bash
bash scripts/check.sh
```

后端自动测试使用无数据库配置、假仓储和内存认证存储；前端 Playwright 拦截全部请求，从 dist 加载页面和假 API。`test:config` 只加载 Vite 配置，验证监听、文件访问限制和转发头覆盖。生命周期测试在临时目录、随机回环端口启动短时假进程并清理，不使用 8025/8026、不启停真实前后端。另已完成一次真实 Oracle/ASGI 联调，临时测试用户和模型已清理；浏览器公网连通性仍需用户手工启动后验证。

Git 发布测试仅在临时仓库与本机 bare 远端中提交/打标签/推送，不访问 GitHub，也不修改本项目的 Git 提交记录。

部分受限执行沙箱会阻断 ASGI 测试线程或 Chromium IPC，需要经批准在沙箱外运行；不应为了让测试通过去启动真实服务。

## 目录

```text
backend/app/       FastAPI、LinkML 服务、Oracle 连接及仓储
backend/tests/     模型、API、安全边界和仓储单元测试
frontend/src/      React 工作台
frontend/tests/    浏览器行为与布局测试
models/           可编辑的 LinkML 示例（不自动保存到数据库）
db/migrations/    FASTONTO 平台与虚拟图迁移
db/verification/  SQL / SPARQL 一致性验证
docs/             架构、验证记录与防回归规则
```

## HTTPS Gateway 模式

在 `FASTONTO_PUBLIC_ORIGIN=https://主机或域名:8025`、证书路径和前端构建产物均配置正确时，可使用项目私有的 rootless Nginx 网关，不改动系统 Nginx 配置：

```bash
# 先由你确认 Vite 前端已停止，后端已运行；网关不会自动接管或终止占用 8025 的进程。
bash scripts/start-gateway.sh
bash scripts/status-gateway.sh
bash scripts/restart-gateway.sh
bash scripts/stop-gateway.sh
```

网关启动时会校验证书配置、生成 `.runtime/nginx/nginx.conf`，并以 `daemon off` 受项目生命周期管理。错误日志为 `.runtime/nginx/error.log`；其启动前错误日志路径也通过 Nginx `-e` 参数指向该项目私有文件，避免访问 `/var/log/nginx`。自签名证书仅供受控客户端场景；浏览器仍须显式信任证书或内部 CA。
