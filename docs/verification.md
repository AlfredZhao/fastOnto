# 首轮验证记录

日期：2026-10-22。初始迁移与 RDF 验收使用 SQLcl；用户提供本机 .env 后补做 Python/Oracle 认证联调。未提取 SQLcl 保存密码，未输出 .env 凭据，未启动常驻服务。

## 已执行的数据库变更

仅 FASTONTO / ORCLPDB1：

- `FO_SCHEMA_MIGRATIONS`：记录迁移 1、2、3。
- `FO_USERS` / `FO_AUTH_SESSIONS`：应用用户及可撤销会话，默认 admin 已初始化为首次强制改密。
- `FO_MODELS` / `FO_MODEL_VERSIONS`：平台源码和版本表，未复制业务记录。
- `FO_NET`：schema-private RDF 网络；Oracle 自动生成内部表、索引、类型、触发器等对象。
- `FO_CUSTOMERS_SOURCE` / `FO_PRODUCTS_SOURCE`：引用 SH 的普通视图。
- `FO_SH_V1`：客户/产品的 R2RML 虚拟 RDF 图，目录 MODEL_TYPE=D。

SH 的表结构、业务记录、索引和已有权限在本轮构建中均未修改。

## 真实 Oracle 查询

| 检查 | 实测 |
|---|---|
| SH 客户记录数 / SPARQL Customer 实例数 | 55,500 / 55,500 |
| SH 产品记录数 / SPARQL Product 实例数 | 72 / 72 |
| 中文 RDF 标签 | 正常返回，如“投球机与击球笼组合” |
| RDF term 输出 | `PLUS_RDFT=T` 后正确返回带引号的字面量表示 |
| 网络物理三元组 | 50 条映射元数据，并非 55,500 客户和 72 产品的实例副本 |
| 产品 URI / 中文标签映射差异 | 0 |
| 物理业务主体 / 业务谓词 | 0 / 0 |
| 初始化脚本重跑 | 成功，迁移记录仍为 1、2，无重复图 |

50 条物理记录的谓词已检查：R2RML 描述、rdf:type，以及 Oracle 的 includesDomain/includesRange/includesDomainRange 元数据。不要误用“物理三元组必须为 0”作为虚拟图判断标准。

复验命令：`sql -S /nolog @db/verify.sql`。脚本另外检查产品 URI/标签映射和是否出现物理业务主体/谓词。

## 自动测试

- 加入认证后：后端 **72 passed**；前端 **27 passed**；TypeScript/Vite 构建通过。直接 Vite 模式另有监听、文件边界和代理头配置检查。
- 后端测试存在一条第三方 Starlette 对 httpx TestClient 适配器的弃用提示，不影响当前测试；后续升级时需跟踪。
- 后端：模型子集、非法 imports、继承环、重复 YAML 键、请求边界、无凭据 503、版本冲突、CLOB 绑定隔离、Decimal、源表白名单及不去重。
- 前端：1440/375/320/812 宽度、深浅主题、长 URI、草稿保留、过期报告、保存冲突、快速切换、错误重试、空状态、弹层与 Esc。
- 前端测试使用 HTTP 拦截和假 API，未访问真实数据库。
- 截图位于忽略的 `frontend/test-results/`；包含测试夹具，不是在线业务截图。

## 已完成的真实认证联调

使用隔离的临时应用账号，通过进程内 ASGI TestClient 与真实 Oracle 验证：

- 未登录拒绝访问，临时密码登录后不能读取业务接口。
- 改密必须携带 CSRF；改密后旧密码不再可登录。
- 登录后 SH 只读预览、虚拟 RDF 查询、模型保存/读取均成功。
- 退出后业务接口拒绝访问；数据库保存 Argon2id 哈希而非明文。
- 临时测试用户、会话和模型已清理，不影响默认 admin 或 SH。

默认 admin 的真实临时密码没有打印到工具输出或聊天。仍需用户手工启动服务，在本机 `.env` 的 `FASTONTO_PUBLIC_ORIGIN` 指定地址首次登录改密，并确认安全组/防火墙连通性。

## Nginx 方案状态

曾准备项目本地 Nginx 配置，但用户随后选择直接 Vite HTTP。默认启动脚本已移除 Nginx 调用；遗留辅助文件不参与启动。未启动、停止或重载 Nginx，也未修改系统 Nginx 配置。

未通过修改源表来演示“更新后立即可见”，因为业务源只读是明确边界。虚拟图已经实际查询源视图，但源数据更新前后的实验需另行安排。
