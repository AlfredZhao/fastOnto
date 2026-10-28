# Changelog

本文件遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 的记录方式，并使用[语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

后续变更先按 `Added`、`Changed`、`Deprecated`、`Removed`、`Fixed`、`Security` 分类记录在本节。发布时，将本节内容移至其下方新的 `## [X.Y.Z] - YYYY-MM-DD` 版本章节；**新版本始终插入在本节之后、已有版本之前**，保持倒序排列。版本标签、`pyproject.toml` 与 `frontend/package.json` 应在正式发布时保持一致。

### Security

- 移除文档、前端 Vite 配置和回归夹具中的部署公网 IP；部署地址仅在本机忽略的 `.env` 中配置。

## [0.1.0] - 2026-10-28

### Summary

首个可用基线：提供以 LinkML 为核心的本体建模、文档辅助建模、受认证保护的业务域治理，以及对 SH 和外部 Oracle 只读业务源的受控元数据与预览能力。FASTONTO 仅保存平台元数据、模型和治理草稿；不复制业务实例数据，也不执行用户定义的 SQL、SPARQL 或规则。

### Added

- 建立 fastOnto 工程、Conda 环境定义、Python/npm 依赖锁定、后端与无服务 Playwright 回归测试。
- 提供 LinkML 源码编辑、受限结构校验、类/属性/关系列表和生成产物；支持模型当前版本、历史记录及乐观并发保存。
- 提供独立模型创建、空白/销售/标准模板、YAML 导入和另存为；支持导出 OWL、SHACL Turtle，以及“标准—发布机构”教学模型和操作教程。
- 提供 XLSX、DOCX、Markdown、TXT 的有界本地解析和人工候选编辑，可生成受支持的 LinkML 草稿；不保存上传原文件，也不接入外部 AI。
- 提供 8 张 SH 白名单表的只读预览，保留十进制金额和源记录多重性；建立 schema-private RDF 网络 `FO_NET`、客户/产品 R2RML 虚拟图 `FO_SH_V1` 及验收脚本。
- 建立 `FO_USERS`、`FO_AUTH_SESSIONS` 和真实 Python/Oracle 登录联调：使用 Argon2id 密码哈希、首次改密、会话撤销、HttpOnly 会话、CSRF、锁定与限流保护。
- 建立工作空间、业务域、本体、映射草稿及规则/指标/操作资产的 FASTONTO 治理元数据；当前 UI/API 以业务域为顶层，工作空间是内部默认容器。
- 提供字段映射 MVP：可将已保存的 LinkML 模型关联至 SH 白名单源，或同一业务域内已登记的外部只读 Oracle 数据源的单个表/视图。
- 提供外部 Oracle 只读数据源登记、受控元数据探查、字段/主键浏览、有界实时预览和 LinkML 候选草稿下载；凭据以 AES-256-GCM 密文保存，主密钥只留在部署环境。
- 提供跨源“实体对齐”治理草稿，以 `IDENTITY` 表达同一本体下两个映射之间的对齐意图。
- 提供前后端服务生命周期脚本，以及本地 Git 提交、附注版本标签和原子推送辅助脚本与回归覆盖。
- 提供项目私有 HTTPS gateway 生命周期脚本：使用 Nginx 前台模式、私有错误日志和受管理 PID，不接管 Vite、未知端口进程或系统 Nginx。

### Changed

- 默认临时测试架构使用直接 Vite HTTP：前端监听 `0.0.0.0:8025` 并代理 `/api` 至后端 `127.0.0.1:8026`；默认启动不使用 Nginx。
- Vite 文件系统访问限制为前端目录并拒绝敏感文件；代理覆盖客户端伪造的转发 IP 头。
- 所有业务 API 均要求数据库支持的登录会话；匿名接口文档关闭，登录前不加载模型或业务数据，旧会话响应会被拒绝。
- 工作台完善深浅主题、桌面/移动布局、加载/空/错误/过期响应状态和未保存草稿保护；新建、另存为和导入流程不再依赖页面刷新。

### Fixed

- 初始化迁移避免在编译期引用尚未创建的元数据表。
- RDF term 查询显式启用 `PLUS_RDFT=T`。
- gateway 仅由受管理启动命令设置 `daemon off`，避免配置与命令行重复声明而导致 Nginx 退出。

### Security

- 映射及语义资产只接受有界、声明式 JSON 草稿，拒绝嵌套 SQL、SPARQL、脚本、命令和表达式；不提供任意 SQL/SPARQL、跨源 join、数据库链路、联邦查询或自动实体匹配。
- 不修改 SH 的表、记录、权限或索引，不将业务行复制到 FASTONTO，也不默认物化实例三元组。
- 外部数据源凭据写入和元数据探查要求 HTTPS；临时 Vite HTTP 仅用于显式允许的测试场景，不提供传输加密。
