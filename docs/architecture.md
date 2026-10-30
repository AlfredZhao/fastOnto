# 架构决策：语义管理与业务实例解耦

## 数据归属

| 数据 | 权威来源 / 存储 |
|---|---|
| 业务记录 | SH 原表，平台仅有指定表 READ 权限 |
| 字段适配 | FASTONTO 普通视图，不是物化视图 |
| 语义映射 | 版本化 R2RML；当前在迁移 002 中定义 |
| 模型源码 | FASTONTO.FO_MODELS 与 FO_MODEL_VERSIONS |
| 模型示例 | 仓库 models/sales.yaml，明确未保存 |
| 虚拟业务 RDF | 查询时映射 SH；不复制实例三元组 |
| UI 偏好 | 浏览器持久化主题，以及按模型校验摘要区分的关系图卡片布局；不保存业务数据或模型正文 |

## 身份与重复记录

客户、产品使用源主键构建 URI。SH.SALES 当前没有主键，五维组合并不唯一；不要求源系统加字段，不用 DISTINCT 去重，不把哈希、ROW_NUMBER 或 ROWID 宣称为永久业务身份。

销售明细走 SQL，只在分页排序中使用 ROWID 作临时并列顺序。源数据变化、重组或跨页期间不保证同一快照。销售汇总事实与永久逐笔身份是后续需明确的业务设计，不在本次偷偷实现。

## 模型与映射互不冒充

编辑并保存 LinkML 只修改平台模型元数据，不自动变更 SQL View / R2RML / SH。虚拟图 `FO_SH_V1` 是显式固定映射，不会自动跟随未发布的模型草稿。需要后续发布流程管理“模型版本—映射版本—源结构”兼容性。

模型接口不接受任意生成器配置、远程 imports、本地文件 imports 或执行代码；受支持字段明确列在 modeling.py。导出产物不作为第二可编辑主源。

## 工作空间与语义治理（迁移 004）

物理表仍保留 `FO_WORKSPACES → FO_DOMAINS → FO_ONTOLOGIES`，以便未来多团队/多租户隔离；但当前是单管理员部署，迁移 005 建立一个内部默认工作空间，**业务域是唯一用户可见的顶层边界**。一个业务域可有多个独立本体。`FO_ONTOLOGIES` 可关联一个已保存的当前 LinkML 模型版本，但该关联不等于发布，也不会自动改写 R2RML、View 或 SH。

`FO_MAPPING_ASSETS` 保存面向 SH 白名单或已登记外部只读源的 R2RML / View+R2RML **草稿元数据**；`FO_SEMANTIC_ASSETS` 保存 RULE、METRIC、ACTION 的声明式草稿。首版 API 拒绝 `sql`、`sparql`、`script`、`command`、`expression` 字段（包括嵌套字段），不执行用户提供的代码或查询。它们也不会自动创建、变更或执行任何 DDL。

映射 MVP 仅允许“一个本体类 + 一个 SH 白名单表或同业务域外部 TABLE/VIEW + 一个主体字段/IRI 模板 + 多个标量属性字段”的直连定义。保存前服务端读取该本体关联的 LinkML 当前版本，验证类、属性、源字段、主体模板和重复属性；对象关系、跨表 join、表达式转换及生成/发布 R2RML 仍不支持。

当前已运行的 `FO_SH_V1` 仍是迁移 002 中审阅过的固定虚拟 RDF 图。治理草稿尚未具备“审核—发布—编译 R2RML—运行”链路；在该链路落实前，业务查询仍只使用原有白名单 SQL 和固定 SPARQL 模板。

## 外部 Oracle 只读数据源（迁移 006）

`FO_BUSINESS_SOURCES` 保存业务域下的 Oracle 数据源配置；DSN、用户名、密码被序列化后以 AES-256-GCM 密文保存，数据库只保存密文和密钥版本。`FASTONTO_SOURCE_MASTER_KEY` 是部署主机本地环境变量，必须是 base64url 编码的 32 字节密钥，绝不写入 FASTONTO、API 响应或日志。编辑数据源必须完整覆盖凭据，不能读取回显。

`FO_SOURCE_OBJECTS` 为后续允许用于映射的表/视图白名单预留。当前探查仅通过固定 `ALL_OBJECTS` 元数据查询读取配置 Schema 下最多 200 个 TABLE/VIEW，不读取业务行、不接受用户 SQL；凭据写入和探查均强制 HTTPS。

外部源浏览接口在 HTTPS 下可读取所选 TABLE/VIEW 的列元数据、主键元数据和有界分页预览。SQL 仅由服务端根据数据字典中已验证的 Oracle 标识符生成，最多 100 行、偏移最多 10000；不支持自定义 SQL、排序、过滤或跨表查询。可由列名、Oracle 类型和 NULLABLE 生成 LinkML 候选 YAML，但不会推断业务标识、对象关系、枚举、规则或业务语义。

迁移 007 允许同一业务域下的本体映射草稿绑定一个外部数据源及一个经实时数据字典校验的 TABLE/VIEW；这与既有 SH 白名单单表映射并列。`FO_ENTITY_LINK_ASSETS` 可声明两个映射使用的字段具有 `IDENTITY` 实体对齐关系，用于表达例如 CRM 客户与 IAM 用户的统一语义意图。两者都是治理草稿：不创建数据库链路、不复制行、不自动匹配实体，也不执行跨源 join 或联邦查询。

## LLM 文档分析（迁移 008）

`FO_LLM_MODELS` 保存多个兼容 OpenAI Chat Completions 的模型配置。模型地址可使用 HTTP 或 HTTPS，地址和名称可列出；API Key 与外部 Oracle 源凭据共用 `FASTONTO_SOURCE_MASTER_KEY`，以 AES-256-GCM 密文保存；主密钥不返回浏览器或日志。平台内的配置、设为默认、连通性测试和文档分析接口仍要求 HTTPS。

文件继续先在平台内存中进行格式安全检查和有界预处理；非 YAML 文件由用户在页面明确选择默认或指定 LLM 后，才将预处理上下文发送给该服务。LLM 必须只返回受限的候选类/属性 JSON，服务端重新校验数量、字段和 LinkML 草稿生成约束。LLM 输出是待人工审核的候选，不运行其中的规则、SQL、SPARQL、脚本或映射。

## 运行隔离

- Python 只使用 FASTONTO 凭据；启动时不自动连接或迁移。
- 连接池 max=4、获取等待 5 秒、网络连接超时 5 秒、每次往返默认超时 10 秒。
- SQL 白名单限制源表、字段、排序；分页 limit<=100、offset<=10000，避免提供全库查询接口。
- 金额以 Decimal 获取并序列化为字符串；不把中文化默认为人民币。
- 模型保存事务锁定模型行，核对 expected_revision，写当前版本与历史版本后一起提交。
- 版本历史表用于留痕，当前不对外提供历史修改或删除接口；数据库所有者自身仍具有管理权限。
- 当前为数据库密码认证的单一可信管理员工作区，无公开注册、多租户隔离或细粒度业务授权。基本登录限流和账号锁定已实现，正式环境仍需 HTTPS、网络边界、SSO/MFA 等评估。

## 临时外部访问与认证

按用户要求：浏览器 → HTTP/Vite 0.0.0.0:8025 → /api 代理 → FastAPI 127.0.0.1:8026 → Oracle。默认不依赖 Nginx。

FO_USERS 保存 Argon2id 加盐哈希；FO_AUTH_SESSIONS 保存随机会话令牌的 SHA-256 摘要与 CSRF token。Cookie 为 HttpOnly、SameSite=Strict；临时 HTTP 下不能设置 Secure，HTTPS 配置下启用 Secure 和 __Host- 前缀。会话默认绝对有效期 8 小时，空闲超时 30 分钟。

首次登录必须改密，改密事务撤销全部旧会话并签发新会话；退出撤销当前会话。连续 5 次账号失败暂锁 15 分钟；单进程每 IP 每分钟 10 次认证尝试，全局每分钟 120 次，并限制并发 Argon2 计算。多实例部署需另行统一 IP 限流存储。

临时 HTTP 已由用户明确接受，但密码和会话在网络上传输仍可能被窃听。认证不能替代 TLS。代理必须覆盖外部传入的 X-Forwarded-For，避免伪造 IP 绕过限流。

## 官方接口依据

- Oracle 26ai Graph Developer's Guide：SEM_APIS.CREATE_RDF_NETWORK。
- Oracle 26ai Graph Developer's Guide：SEM_APIS.CREATE_RDFVIEW_GRAPH，r2rml_string / network_owner / network_name。
- Oracle 26ai SEM_MATCH：options PLUS_RDFT=T 才生成变量对应的 $RDFTERM 列。
- LinkML SchemaView：类与属性继承解析；只导入包内 linkml:types。


## 受控 SH 指标问答（迁移 009/010）

指标运行仅来自服务端审阅过的聚合模板；LLM 只能返回受限的指标、维度、年份和返回条数 JSON，服务端重新校验，绝不执行 LLM 生成 SQL。LLM 可在受限聚合结果上生成中文解读；结果不含凭据、SQL 或明细业务行。

“受限探索”使用同一组固定只读模板，但明确标识为非正式口径，不能替代已发布指标。`FO_ANALYTIC_PRESENTATIONS` 仅存可验证的维度展示元数据；当前客户支持姓/名顺序及绑定的分隔符，绝不保存表达式或 SQL。
