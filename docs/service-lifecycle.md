# 服务生命周期脚本

## 原先为何有两个前端脚本？

原 `start-frontend.sh` 调用 `npm run dev`，监听 `0.0.0.0:8025`；`start-frontend-dev.sh` 调用 `npm run dev:local`，监听 `127.0.0.1:8025`。两者都是 Vite 开发服务，差别只是监听范围，不是生产版与开发版，也不应同时运行。

现在统一到 `start-frontend.sh`：默认保留用户批准的外部 HTTP；`--local` 仅本机。旧 `start-frontend-dev.sh` 只提示弃用并转发至统一入口 `--local`，共享同一 PID 状态与锁。`npm run dev`/`dev:local` 仍可用于开发者有意进行的前台调试，但不受后台管理脚本接管。

## 常用命令

从项目根目录运行，或使用脚本绝对路径；不依赖调用者工作目录。全部入口均可 `bash scripts/xxx.sh` 或直接执行。

| 操作 | 后端 | 前端 | 整体 |
|---|---|---|---|
| 后台启动 | start-backend.sh | start-frontend.sh | start-all.sh |
| 停止 | stop-backend.sh | stop-frontend.sh | stop-all.sh |
| 重启 | restart-backend.sh | restart-frontend.sh | restart-all.sh |
| 状态 | status-backend.sh | status-frontend.sh | status.sh |

```bash
bash scripts/start-all.sh
bash scripts/status.sh
bash scripts/restart-all.sh
bash scripts/stop-all.sh

# 仅本机前端（后端始终仅本机）
bash scripts/start-all.sh --local
bash scripts/restart-frontend.sh --local

# 显式等待与强制中断选项
bash scripts/start-backend.sh --timeout 60
bash scripts/stop-backend.sh --timeout 30
# 仅确认可以中断时使用：先 TERM，超时后才 KILL
bash scripts/stop-backend.sh --timeout 10 --force
bash scripts/restart-all.sh --timeout 30 --force
```

`--timeout` 默认 30 秒，允许 1–300；编排脚本使用整数秒。`--force` 仅用于 stop/restart；`--local` 仅用于包含前端的 start/restart。**重启不会记忆上次的 `--local` 参数**，要继续仅本机运行必须再次指定；不带该参数按默认外部 HTTP 启动。

不要再加 `nohup` 或 `&`：启动程序创建独立 session，输入接 `/dev/null`，输出接日志文件，检查就绪后返回。后端直接运行 fastonto 环境中的 Uvicorn，前端直接运行 Node + Vite CLI，避免把 npm/Conda 包装进程误当作服务 PID。Python 管理入口仍通过 `conda run --no-capture-output -n fastonto` 执行。

## 顺序与失败语义

- 每个 restart 脚本先调用对应 stop 脚本；只有 stop 返回 0 才调用 start。不是 reload，也不是零停机发布。
- `start-all`：后端→前端。`stop-all`：前端→后端，即使前端停止失败也会尝试停止后端，并返回失败。`restart-all` 调用 stop-all，再调用 start-all；任一停止失败都不进入启动阶段。
- 后端成功、前端启动失败：整体命令返回失败，保留后端，不擅自关闭可能原本已存在的后端。请用 status 查看实际部分成功状态。
- 同一服务单次操作使用排他文件锁；并发操作会明确失败，避免重复启动。整组或 restart 的多步操作不是事务，请不要并行发起多个编排命令。
- 已登记且就绪的服务重复 start 成功返回，不产生第二份进程；另一监听模式运行时拒绝 start，需 stop/restart 切换。
- start 发现端口由未登记的旧进程占用时拒绝启动，不按端口或进程名杀进程，也不自动把旧进程登记为自己的服务。
- start 仅在本次服务进程拥有目标监听端口、HTTP 检查通过后报告成功。后端检查 `/api/health`，**只证明 HTTP 存活，不证明数据库、业务权限或 RDF 已可用**；前端检查 Vite HTML，不要求已登录或后端数据库可用。
- 本次新启动失败/超时时只清理本次产生的已验证进程。日志留存；清理失败保留状态并报错。
- stop 先发 SIGTERM 并等待；默认超时失败、保留状态供排查。`--force` 只在超时后对已验证进程发 SIGKILL，不会扩大到其他端口占用者。
- status 单服务返回 0=已就绪、1=未就绪/操作错误、3=未运行/状态失效；整体 status 任一不就绪则非零。

## PID、权限与日志

```text
.runtime/services/backend.pid.json
.runtime/services/frontend.pid.json
.runtime/services/backend.lock
.runtime/services/frontend.lock
logs/backend.log
logs/frontend.log
```

状态记录服务名、项目路径、Unix UID、系统 boot ID、PID、进程启动时刻、session/进程组及已发现的子进程。发送信号前再次核对身份，并使用 pidfd 定位进程，避免失效 PID 杀到后来复用该编号的进程。不读取 `/proc/.../environ`，不输出凭据、DSN 或完整环境。

Linux 内核须支持 pidfd（通常 5.3+），且允许访问当前用户进程的 `/proc` 信息。当前 Conda Python 构建缺少 `os.pidfd_open`，x86_64/aarch64 使用相同的 Linux pidfd_open 系统调用封装；仍用 pidfd 发信号，不降级成普通 PID 盲杀。其他架构须有 Python 原生封装。

运行目录必须属于当前 Unix 用户、不可供其他用户写入；新目录 700，状态/锁/日志 600，拒绝文件符号链接和异常状态文件。用同一账号管理，不要混用 sudo 或手工编辑 PID 文件。状态丢失或主进程及所有已记录成员都消失后，不猜测接管可能残留的未知进程；端口仍占用则报告冲突，需人工核查。

日志追加写入，重新启动不会覆盖旧日志；不自动打印日志尾部，避免意外把敏感错误内容带到终端。旧 `scripts/frontend.log`/`nohup.out` 不迁移、不读取、不删除。持续运行须另外配置日志轮转与磁盘监控，本次不修改系统 logrotate。

## 从旧启动方式切换

1. 保存工作台草稿。
2. 用户自行在原终端 Ctrl+C，或按此前 nohup 的管理方式停止旧服务。若无法确认进程归属，请先人工核查，不执行批量 kill。
3. 使用 `start-all.sh` 启动，再检查 `status.sh`；脚本从此建立自己的 PID 状态。
4. 后续使用对应 stop/restart；不删除仍在运行服务的 PID 状态来强行重启。

本次修改没有替用户启动、停止或重启已有前后端，没有迁移数据库、修改 SH、防火墙或 Nginx。

## 与完整生产部署的区别

此次满足后台启停、重启和基本操作保护，但仍遵守既有临时 Vite HTTP 架构。HTTP 未加密；脚本不是故障守护器，不提供崩溃自动拉起、开机自启、多实例调度、TLS 或零停机发布。正式生产仍需另行确定构建产物部署、HTTPS、进程监督、日志轮转及监控方案，不能把后台运行等同于已完成这些工作。

## HTTPS Gateway（自签名或受信任证书）

`start-gateway.sh`、`stop-gateway.sh`、`restart-gateway.sh`、`status-gateway.sh` 管理项目私有 Nginx 网关。它与 `start-frontend.sh` 的 Vite 前端互斥，因为两者均使用 8025；网关遇到 Vite 或其他未登记占用时会失败，绝不会按端口杀进程。

启动时网关会通过 `app.frontend_gateway` 检查 HTTPS origin、证书、私钥和 `frontend/dist`，生成项目私有配置，然后以 `nginx -e <项目日志> ... -g 'daemon off;'` 运行。生命周期检查仅对本机 HTTPS 使用不校验证书的 TLS 上下文来验证响应；这不改变浏览器或外部客户端的证书信任要求。
