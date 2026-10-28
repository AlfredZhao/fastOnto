# 防回归规则

- 不得在受版本控制的源码、文档、测试夹具或代理允许列表中写入部署公网 IP；外部访问地址只可存在于忽略的本机 `.env` 或运行环境变量。Vite 不得以 `allowedHosts=true` 规避主机校验。
- HTTPS gateway 与 Vite 前端互斥使用 8025。gateway 启动前必须通过 origin/证书/私钥/构建产物验证；使用项目私有错误日志与 `-e`，不得尝试写 `/var/log/nginx`，也不得接管或终止未知监听进程。
- Nginx 的 `daemon off` 只能由 gateway 受管启动命令提供，生成的配置不得重复声明；否则 Nginx 会在解析配置时立即退出。

## 2026-10-27：工作空间和语义资产只能治理，不能执行

- `FO_WORKSPACES → FO_DOMAINS → FO_ONTOLOGIES` 仅存在于 FASTONTO；当前单管理员 UI/API 只暴露业务域，工作空间是迁移 005 建立的内部容器。两者都不能授予、改变或越过 SH 的只读边界。
- 映射草稿只可引用当前 SH 白名单源，或同业务域内已登记的外部只读源及其单个表/视图；不得接收原始 SQL、SPARQL、脚本、命令或表达式字段（递归检查嵌套 JSON）。草稿不是已运行的 RDF 映射。
- 字段映射 MVP 必须先关联保存的 LinkML 当前版本；一个草稿只能映射一个类和一个 SH 源表或外部表/视图，主体 IRI 模板必须引用所选主体字段，属性不能重复且只能映射标量属性。不能用它隐式实现 join、转换或对象关系。
- 外部 Oracle 业务源的 DSN、用户名、密码可在 FASTONTO 以 AES-256-GCM 密文保存，但主密钥只能存在部署主机本机环境；任何 API、日志和列表响应不得返回密文、DSN、用户名或密码。凭据写入和元数据发现必须拒绝 HTTP。
- 编辑外部业务源必须完整替换凭据，不得将已存密码回填页面；解密失败、缺少/无效主密钥或外部库连接失败均不得泄露 DSN、用户名、SQL 或驱动原始错误。
- 外部业务数据浏览只可针对数据字典确认存在的 TABLE/VIEW，列名、对象名和 Schema 必须符合未加引号 Oracle 标识符限制；预览只允许服务端生成的有界单表 SELECT，不能接收排序、条件、join 或任意 SQL。
- RULE、METRIC、ACTION 与 LinkML 版本关联是治理元数据，不自动运行规则、计算指标、执行操作或修改源表。当前运行时仍只有迁移 002 的审阅 R2RML 图及固定查询模板。
- 迁移 004、005 必须由 FASTONTO/ORCLPDB1 手工执行；DDL 失败后如实检查对象状态，不能以 Oracle 自动提交为由宣称已经回滚。

## 2026-10-23：Git 提交与标签发布

- scripts/commit-to-github.sh 仅操作脚本所在根仓库，支持 unborn 分支；不自动 init/改作者/加远端/换分支。异常 GIT_DIR/GIT_INDEX_FILE 等覆盖环境、detached HEAD、进行中的 Git 操作须拒绝。
- dry-run 离线且不构建、不建仓库锁、不修改索引/提交/标签；无远端可预演。普通模式全项目暂存应明确告知，构建失败不能由本脚本暂存。
- .env、日志、运行状态、私钥、缓存等强行暂存也须拒绝；只显示路径，不输出敏感内容/带凭据的远端 URL。这是路径守护，不是历史或任意源码密钥扫描。
- --no-tag 与参数顺序无关；版本标签为附注标签。已有标签仅允许干净且同 HEAD 时复用，防止失败重试生成重复提交或移动标签。
- 显式选定远端/当前分支；禁用隐式 followTags，分支和指定标签 atomic 推送；失败保留本地状态，不自动 reset/强推/删除标签。CHANGELOG 不自动重排。
- 守护：backend/tests/test_git_publish_script.py；仅在临时仓库和本机 bare 远端提交/打标签/推送，不访问 GitHub，不对实际项目执行写 Git 操作。
- 验证：Git 脚本专项 35 项、完整后端 186 项通过；shell 语法检查与实际项目离线预演通过。实际项目仍无提交、无暂存文件、无远端；未执行真实 commit/tag/push。现有 Starlette/httpx 测试客户端弃用警告未在本次升级处理。

## 2026-10-23：后台启动、停止和重启

- 所有 Python 启停入口使用 Conda fastonto；前端默认仍 0.0.0.0:8025，后端固定 127.0.0.1:8026，不启动 Nginx、不改防火墙、不自动迁移。
- 子进程必须独立 session、stdin=/dev/null、日志文件重定向、关闭继承的锁 fd；调用者退出后继续运行，不能只后台化包装 shell。
- 只管理本项目、当前用户、匹配 boot ID/PID/启动时刻/session 的进程，用 pidfd 发信号；不能 pkill、按端口杀未知进程、接管遗留服务或把普通 PID 复用当成自己的服务。
- start 等 HTTP 就绪后成功，端口必须属于登记进程；同模式重复启动幂等，不同模式要求显式重启。后台端口健康不等于数据库验收。
- stop 默认 TERM 超时返回失败并保留状态，只有显式 --force 才升级 KILL。restart 只在 stop 成功后 start；整体 stop 前端→后端，整体 start 后端→前端，部分失败如实报告。
- 守护：`backend/tests/test_service_scripts.py`；临时目录/随机回环端口的假 HTTP 进程，验证后台存活、真实子进程清理、PID 失效、未知占用、锁、权限、超时及 shell 编排顺序。绝不使用实际 8025/8026 或真实前后端做启停测试。
- 说明：`docs/service-lifecycle.md`。旧 frontend-dev 脚本只是 --local 别名；日志和状态都忽略提交，仍需用户手工将未登记旧服务切换到新脚本。
- 验证：生命周期专项 29 项通过；完整后端 151 项通过；全部 shell 语法检查及帮助入口通过。测试因沙箱禁止回环套接字，获准在沙箱外使用临时假服务验证并清理；未调用真实服务的 start/stop/restart，未连接数据库。现有 Starlette/httpx 弃用警告未在本次升级处理。

## 2026-10-23：独立模型与文档导入

- 新建/模板/YAML 导入必须清空平台 record、savedSource 和旧校验快照；另存为必须提交 `id: null, expected_revision: 0`，不能更新旧模型。
- 创建结果异步返回时检查**最新**工作台草稿状态，而非请求发出时的闭包；覆盖前确认。取消向导后递增请求代次并 abort，旧响应不得覆盖新稿。
- 向导跨工作区路由保留，刷新/退出提示未保存；修改候选撤销审核勾选；重复名称/失效引用由服务端拒绝。
- 原文件只在内存解析。XLSX/DOCX/Markdown 普通表格仅提取表头，不把记录写入源码；数据字典仅作为模型定义。正文不假装 AI 理解，无候选明确提示。
- 导入专用 3 MiB 请求上限、2 MiB 文件上限；普通业务接口仍 128 KiB。Office 条目/解压大小/压缩比/深度/节点限制；DTD、实体、宏、路径穿越、重复条目、外部工作簿链接必须拒绝。
- 守护：`backend/tests/test_document_import.py`、`test_auth.py`；`frontend/tests/workspace.spec.ts` 覆盖新建、另存为、YAML、候选审核、关系修改、桌面/320/375px 深浅色、长 IRI、空/错/忙、取消迟到请求、导航保留及导出。
- 操作说明：`docs/document-import.md`；无需数据库迁移或新依赖。浏览器测试拦截全部 HTTP，不运行真实业务服务。
- 2026-10-23 验证：后端 122 项通过（含生成模型的 JSON Schema/OWL/SHACL 导出）；浏览器 45 项通过；TypeScript/Vite 构建、Vite 安全配置测试、`pip check` 通过。人工查看桌面深色与手机浅色导入截图。沙箱阻断 TestClient/Chromium，已获准在沙箱外重跑；测试未连接真实数据库、未启动/重启常驻服务。仍有现有 Starlette/httpx 测试客户端弃用警告，未在本次顺带升级依赖。

## 教学模型与操作说明

- 示例：`models/standards-tutorial.yaml`，教程：`docs/tutorial-standards.md`。保持 2 个类、1 条对象关系，标准 7 个属性、机构 2 个属性；支持现有三种导出。
- 守护：`backend/tests/test_tutorial.py` 检查基线、未知类型拒绝、对象关系改字符串后的关系消失，以及导出可解析性。这不等于标准符合性或实例验证测试。
- 2026-10-22 验证：教学示例与现有建模测试共 31 项通过；有一条已有测试客户端依赖弃用警告。沙箱内 TestClient 启动阻塞，获准在沙箱外重跑后通过；未连接数据库、未启动常驻服务，未进行浏览器手工验收。
- 已补齐“新建／另存为／导入”，教程通过这些入口建立独立草稿；“当前草稿”下拉选项禁用，不能作为新建命令。实例只用于概念讲解，不可粘贴到模型源码区。

## 认证与首次改密不能只靠 UI

- 安全模式：所有业务路由统一会话依赖，临时密码用户只允许 me/logout/password；密码变更撤销旧会话，源查询不可匿名访问。
- 守护：`test_auth.py` 和 `auth.spec.ts`，包含 CSRF、账号锁定、会话过期、首次改密与旧响应隔离。

## Vite 外部代理不可透传伪造的客户端 IP

- 背景：后端只信任 loopback 的代理头；若 Vite 原样转发外部 X-Forwarded-For，会绕过按 IP 的限流。
- 安全模式：从真实 socket.remoteAddress 覆盖转发 IP 与协议，保留 Origin；fs.allow 仅 frontend，拒绝 .env/.runtime/密钥文件；不设置 allowedHosts=true 或 cors=true。
- 守护：`npm run test:config`。仅配置加载测试，不启动服务；实际公网连通性另行验收。

## 业务边界

- 症状：把平台接入误写成源数据迁移或导入副本。
- 安全模式：只读 SH；只在 FASTONTO 管理元数据和虚拟映射。源查询不使用 DISTINCT，保留销售重复记录。
- 守护：`test_sql_boundaries.py`、`test_repository.py::test_no_user_sql_or_dedup`，以及真实 SQL/SPARQL 对账。

## Oracle 初始化的编译期可见性

- 症状：同一 PL/SQL 块动态建表后静态 INSERT，编译阶段报 ORA-00942，整个块未执行。
- 安全模式：引用本块新建对象的语句也用受控动态 SQL，或拆分块。不得把此错误当成数据已回滚的证据。
- 守护：新空 schema 初始化；同一脚本重跑；检查 FO_SCHEMA_MIGRATIONS。

## RDF term 元数据列

- 症状：SEM_MATCH 直接选择 `label$rdfterm` 报 ORA-00904。
- 安全模式：显式传 `PLUS_RDFT=T`；不能把普通值列等同于完整 RDF term。
- 守护：`db/verification/001_virtual_rdf.sql` 返回中文 label 及完整 term。

## 深浅主题、长 URI 与窄屏

- 来源：trustedKnowledge 的浅色对比度补丁、320px 卡片撑宽、桌面工具栏溢出记录。
- 安全模式：语义色 token、所有网格子项 min-width:0；工具栏换行；表格仅局部滚动；长 URI 断行。
- 守护：Playwright 的 1440/375/320/812 宽度 × 深浅主题布局测试。

## 异步结果与草稿

- 来源：trustedKnowledge 任务切换串写、缓存覆盖草稿、旧持久状态白屏。
- 安全模式：请求编号/AbortController、校验绑定源码快照、过期报告显式提示；保存成功仅标记提交快照，不能覆盖之后的编辑；路由切换保留父级草稿状态。
- 守护：Playwright 的 late validation、save conflict、route navigation、stale source response 用例。只持久化经白名单检查的主题值。

## SQL 绑定与精度

- 来源：trustedKnowledge CLOB setinputsizes 与业务 binds 泄漏至 SELECT FOR UPDATE。
- 安全模式：读锁、写当前版本、写历史版本各用独立游标和绑定字典。NUMBER 以 Decimal 获取，金额输出字符串。
- 守护：`test_update_binds_and_clob_sizes_isolated`、`test_source_preview_bound_exact_binds`。

## 极端日期

- SH 无促销值的日期为 0001-01-01 至 9999-12-31。
- 结束日包含判断使用日期粒度比较，不对 9999-12-31 加一天。
- 守护：`test_serialization_preserves_edges`；不得把前端 JS 日期构造器作为原始日期字符串保真的前提。

## 2026-10-28：多数据源只进入治理层，不能越过查询边界

- 一个业务域可登记多个 `FO_BUSINESS_SOURCES`；外部映射必须将本体、数据源和 TABLE/VIEW 绑定到同一业务域。不得用另一业务域的数据源给本体建映射。
- 映射仍只能是单个表/视图到单个本体类的字段直连。外部表/视图字段只通过受控 `ALL_*` 数据字典查询验证；不接受源端 SQL、join、筛选、转换或对象关系。
- `FO_ENTITY_LINK_ASSETS` 只记录两个映射之间的 `IDENTITY` 对齐声明，且键字段必须已经出现在各自映射定义中。它不读取业务行、不自动匹配用户/客户、不创建同一实体实例、更不执行跨源查询。
- 迁移 007 必须由 FASTONTO/ORCLPDB1 手工执行；Oracle DDL 自动提交，失败时检查列和表是否部分建立后再处理。不得宣称已回滚。
