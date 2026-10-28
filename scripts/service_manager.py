"""Linux lifecycle helper. Invoked only via conda run -n fastonto.

No database operations, environment dumps, shell command evaluation, or killing
by port/name. A PID is signalled through pidfd only after identity verification.
"""
import argparse
from contextlib import contextmanager
import ctypes
from dataclasses import dataclass
import fcntl
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import ssl
import stat
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.request import HTTPRedirectHandler, HTTPSHandler, ProxyHandler, build_opener


class ServiceError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_pidfd(pid):
    if hasattr(os, 'pidfd_open'):
        return os.pidfd_open(pid)
    # The shipped Conda Python lacks os.pidfd_open on this older glibc build,
    # although the Linux kernel supports it. Use the Linux ABI, not unsafe kill.
    # __NR_pidfd_open is 434 on both supported architectures (asm/unistd.h).
    if platform.machine() not in {'x86_64', 'aarch64'}:
        raise ServiceError('此架构需要 Python 自带 os.pidfd_open；不会降级为按 PID 盲杀。')
    libc = ctypes.CDLL(None, use_errno=True)
    syscall = libc.syscall
    syscall.argtypes = [ctypes.c_long, ctypes.c_int, ctypes.c_uint]
    syscall.restype = ctypes.c_long
    fd = syscall(434, pid, 0)
    if fd < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    return fd


@dataclass(frozen=True)
class Config:
    name: str
    root: Path
    command: tuple[str, ...]
    cwd: Path
    host: str
    port: int
    health_path: str
    scheme: str = 'http'


def process_identity(pid):
    """Read only process metadata, never environ or command-line credentials."""
    try:
        directory = Path(f"/proc/{pid}")
        values = (directory / "stat").read_text().rsplit(")", 1)[1].split()
        if values[0] in {"Z", "X"}:
            return None
        return {"pid": pid, "ticks": int(values[19]), "pgid": int(values[2]),
                "sid": int(values[3]), "uid": directory.stat().st_uid}
    except (FileNotFoundError, ProcessLookupError):
        return None


def signal_verified(identity, sig):
    """Verify after opening pidfd, eliminating the PID-reuse kill race."""
    try:
        fd = open_pidfd(identity["pid"])
    except ProcessLookupError:
        return
    try:
        if process_identity(identity["pid"]) == identity:
            try:
                signal.pidfd_send_signal(fd, sig)
            except ProcessLookupError:
                pass
    finally:
        os.close(fd)


def listener_inodes(port):
    found = set()
    for table in (Path('/proc/net/tcp'), Path('/proc/net/tcp6')):
        if not table.exists():
            continue
        for line in table.read_text().splitlines()[1:]:
            fields = line.split()
            if fields[3] == '0A' and int(fields[1].split(':')[1], 16) == port:
                found.add(fields[9])
    return found


def owns_listener(members, port):
    inodes = listener_inodes(port)
    if not inodes:
        return False
    for member in members:
        if process_identity(member['pid']) != member:
            continue
        try:
            for entry in Path(f"/proc/{member['pid']}/fd").iterdir():
                try:
                    target = os.readlink(entry)
                    if target.startswith('socket:[') and target[8:-1] in inodes:
                        return True
                except FileNotFoundError:
                    pass
        except (FileNotFoundError, ProcessLookupError):
            pass
    return False


def private_file(path, flags):
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
        os.close(fd)
        raise ServiceError(f"拒绝不安全文件：{path.name}")
    os.fchmod(fd, 0o600)
    return fd


class Manager:
    def __init__(self, config):
        self.config = config
        self.directory = config.root / '.runtime' / 'services'
        self.state_path = self.directory / f'{config.name}.pid.json'
        self.log_path = config.root / 'logs' / f'{config.name}.log'
        self.boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        self.child = None

    @contextmanager
    def locked(self):
        if not hasattr(signal, 'pidfd_send_signal'):
            raise ServiceError('需要支持 pidfd 的 Linux 与 fastonto Python 环境。')
        # Check kernel support before spawning anything.
        fd = open_pidfd(os.getpid())
        os.close(fd)
        for directory in (self.config.root / '.runtime', self.directory, self.log_path.parent):
            if directory.is_symlink():
                raise ServiceError(f'运行目录不能是符号链接：{directory.name}')
            directory.mkdir(mode=0o700, exist_ok=True)
            if directory.stat().st_uid != os.geteuid():
                raise ServiceError('运行目录必须属于当前操作用户。')
            if directory.stat().st_mode & 0o022:
                raise ServiceError('运行目录不能允许其他用户写入。')
        fd = private_file(self.directory / f'{self.config.name}.lock', os.O_RDWR | os.O_CREAT)
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise ServiceError('已有同一服务的生命周期操作正在执行，请稍后重试。') from exc
            yield
        finally:
            os.close(fd)

    def read_state(self):
        try:
            fd = private_file(self.state_path, os.O_RDONLY)
        except FileNotFoundError:
            return None
        try:
            with os.fdopen(fd) as stream:
                raw = stream.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ValueError()
                state = json.loads(raw)
            if not isinstance(state, dict) or not isinstance(state.get('leader'), dict) or not isinstance(state.get('members'), list):
                raise ValueError()
            root = state['leader']
            identities = [root, *state['members']]
            valid = (state['version'] == 1 and state['root'] == str(self.config.root)
                     and state['service'] == self.config.name and state['port'] == self.config.port
                     and state['uid'] == os.geteuid() and isinstance(state['boot'], str)
                     and state['host'] in {'127.0.0.1', '0.0.0.0'}
                     and len(identities) <= 512)
            for item in identities:
                if not isinstance(item, dict):
                    raise ValueError()
                valid = valid and set(item) == {'pid', 'ticks', 'pgid', 'sid', 'uid'}
                valid = valid and all(type(value) is int for value in item.values())
                valid = valid and item['pid'] > 1 and item['ticks'] > 0 and item['uid'] == os.geteuid()
                valid = valid and item['pgid'] == root['pid'] and item['sid'] == root['pid']
            if not valid:
                raise ValueError()
            return state
        except (ValueError, KeyError, TypeError) as exc:
            raise ServiceError('PID 状态文件无效或不属于本项目；拒绝启动/发送信号，请人工核查。') from exc

    def write_state(self, state):
        fd, filename = tempfile.mkstemp(prefix=f'.{self.config.name}-', dir=self.directory)
        try:
            with os.fdopen(fd, 'w') as stream:
                json.dump(state, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(filename, self.state_path)
        finally:
            Path(filename).unlink(missing_ok=True)

    def members(self, state):
        if not state or state['boot'] != self.boot:
            return []
        known = {item['pid']: item for item in [state['leader'], *state['members']]}
        live = {pid: item for pid, item in known.items() if process_identity(pid) == item}
        leader = state['leader']
        # Only discover descendants while a verified member still anchors the
        # original session. Never adopt processes just because a PID/port matches.
        if live:
            for entry in Path('/proc').iterdir():
                if not entry.name.isdecimal():
                    continue
                try:
                    item = process_identity(int(entry.name))
                except PermissionError:
                    continue
                if (item and item['uid'] == os.geteuid() and item['pgid'] == leader['pid']
                        and item['sid'] == leader['pid'] and item['ticks'] >= leader['ticks']):
                    live[item['pid']] = item
        return list(live.values())

    def ready(self, members):
        if not owns_listener(members, self.config.port):
            return False
        try:
            handlers = [ProxyHandler({}), NoRedirect()]  # Stay local; ignore HTTP_PROXY.
            if self.config.scheme == 'https':
                # Local readiness only. The browser still validates/trusts the configured certificate.
                handlers.append(HTTPSHandler(context=ssl._create_unverified_context()))
            opener = build_opener(*handlers)
            with opener.open(f'{self.config.scheme}://127.0.0.1:{self.config.port}{self.config.health_path}', timeout=1) as response:
                body = response.read(4096)
                if self.config.name == 'backend':
                    return response.status == 200 and json.loads(body) == {'status': 'ok'}
                if self.config.name == 'gateway':
                    return response.status == 200 and b'<div id="root">' in body
                return response.status == 200 and b'@vite/client' in body
        except (OSError, URLError, ValueError):
            return False

    def start(self, timeout):
        state = self.read_state()
        live = self.members(state)
        if live:
            if state['host'] != self.config.host:
                raise ServiceError('服务已使用另一监听模式运行；请使用 restart 切换，不能并行启动。')
            if process_identity(state['leader']['pid']) == state['leader'] and self.ready(live):
                print(f"{self.config.name} 已运行，PID={state['leader']['pid']}（未重复启动）。")
                return
            raise ServiceError('已登记进程仍在运行但未就绪；请检查 status/日志，必要时先 stop。')
        if listener_inodes(self.config.port):
            raise ServiceError(f'端口 {self.config.port} 已被未登记的服务占用；不会自动接管或杀进程。')
        if state:
            print('清理已失效的 PID 状态（未向任何进程发送信号）。')
            self.state_path.unlink()
        if not Path(self.config.command[0]).is_file():
            raise ServiceError('找不到服务运行程序，请检查 fastonto 环境和 Node 安装。')
        fd = private_file(self.log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
        with os.fdopen(fd, 'ab', buffering=0) as log:
            log.write(f'\n--- {time.strftime("%Y-%m-%d %H:%M:%S %z")} start {self.config.name} ---\n'.encode())
            self.child = subprocess.Popen(self.config.command, cwd=self.config.cwd,
                                          stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                          start_new_session=True, close_fds=True, umask=0o077)
        leader = process_identity(self.child.pid)
        if not leader:
            self.child.wait()
            raise ServiceError(f'启动进程立即退出，请查看 {self.log_path}。')
        state = {'version': 1, 'root': str(self.config.root), 'service': self.config.name,
                 'uid': os.geteuid(), 'boot': self.boot, 'host': self.config.host, 'port': self.config.port,
                 'leader': leader, 'members': [leader]}
        try:
            self.write_state(state)
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                live = self.members(state)
                state['members'] = live
                self.write_state(state)
                if self.child.poll() is not None:
                    raise ServiceError('服务在启动期间退出。')
                if self.ready(live) and self.child.poll() is None:
                    print(f'{self.config.name} 后台启动成功，PID={leader["pid"]}，监听 {self.config.host}:{self.config.port}')
                    print(f'日志：{self.log_path}\nPID 状态：{self.state_path}')
                    return
                time.sleep(0.15)
            raise ServiceError('等待 HTTP 就绪超时。')
        except BaseException:
            # Roll back only processes belonging to this failed launch. Never a
            # pre-existing backend if a later frontend launch fails.
            try:
                self.stop_state(state, timeout=3, force=True)
            finally:
                print(f'启动未完成，请在本机检查日志：{self.log_path}', file=sys.stderr)
            raise

    def stop_state(self, state, timeout, force):
        sent = set()
        deadline = time.monotonic() + timeout
        while True:
            live = self.members(state)
            if not live:
                self.state_path.unlink(missing_ok=True)
                if self.child:
                    self.child.poll()
                return
            state['members'] = live
            self.write_state(state)
            for member in live:
                identity = (member['pid'], member['ticks'])
                if identity not in sent:
                    signal_verified(member, signal.SIGTERM)
                    sent.add(identity)
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        if not force:
            raise ServiceError('优雅停止超时；保留 PID 状态。检查日志，确认可中断后用 stop --force。')
        for member in self.members(state):
            signal_verified(member, signal.SIGKILL)
        deadline = time.monotonic() + 3
        while self.members(state) and time.monotonic() < deadline:
            time.sleep(0.1)
        if self.members(state):
            raise ServiceError('仍有登记进程未退出，保留 PID 状态；不会报告停止成功。')
        self.state_path.unlink(missing_ok=True)
        if self.child:
            self.child.poll()

    def stop(self, timeout, force):
        state = self.read_state()
        if state:
            self.stop_state(state, timeout, force)
        if listener_inodes(self.config.port):
            raise ServiceError(f'登记进程已不在运行，但端口 {self.config.port} 仍被其他进程占用；未对其发送信号。')
        print(f'{self.config.name} 已停止（重复 stop 安全）。')

    def status(self):
        state = self.read_state()
        live = self.members(state)
        if not live:
            suffix = '；端口被未登记进程占用' if listener_inodes(self.config.port) else ''
            print(f'{self.config.name} 未运行或 PID 状态已失效{suffix}。')
            return 3
        healthy = process_identity(state['leader']['pid']) == state['leader'] and self.ready(live)
        print(f"{self.config.name} {'运行就绪' if healthy else '进程存在但未就绪'}，PID={state['leader']['pid']}，监听 {state['host']}:{state['port']}")
        print(f'日志：{self.log_path}')
        return 0 if healthy else 1


def configuration(name, local=False, require_runtime=True):
    root = Path(__file__).resolve().parent.parent
    if name == 'backend':
        return Config(name, root, (sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1',
                                  '--port', '8026', '--proxy-headers', '--forwarded-allow-ips', '127.0.0.1', '--no-access-log'),
                      root, '127.0.0.1', 8026, '/api/health')
    if name == 'gateway':
        runtime = root / '.runtime' / 'nginx'
        nginx = shutil.which('nginx')
        if require_runtime:
            if not nginx:
                raise ServiceError('找不到 nginx；请先由运维安装 Nginx 二进制。')
            try:
                sys.path.insert(0, str(root / 'backend'))
                from app.config import Settings
                from app.frontend_gateway import render
                config_path = render(Settings())
            except Exception as exc:
                raise ServiceError('HTTPS 网关配置生成失败；检查 HTTPS 来源、前端构建产物和证书路径。') from exc
        else:
            config_path = runtime / 'nginx.conf'
            nginx = nginx or '/missing-nginx'
        return Config(name, root, (nginx, '-e', str(runtime / 'error.log'), '-c', str(config_path),
                                   '-p', str(runtime), '-g', 'daemon off;'), root, '0.0.0.0', 8025, '/', 'https')
    host = '127.0.0.1' if local else '0.0.0.0'
    node = shutil.which('node')
    if not node and require_runtime:
        raise ServiceError('找不到 Node；请先加载 Node 运行环境。')
    vite = root / 'frontend/node_modules/vite/bin/vite.js'
    if not vite.is_file() and require_runtime:
        raise ServiceError('未安装前端依赖；请在 frontend 中手工执行 npm ci。')
    return Config(name, root, (node or '/missing-node', str(vite), '--host', host, '--port', '8025', '--strictPort'),
                  root / 'frontend', host, 8025, '/')


def main():
    parser = argparse.ArgumentParser(description='fastOnto 后台服务管理；不会迁移数据库或修改防火墙/Nginx。')
    parser.add_argument('service', choices=['backend', 'frontend', 'gateway'])
    parser.add_argument('action', choices=['start', 'stop', 'status'])
    parser.add_argument('--local', action='store_true', help='frontend start 仅监听 127.0.0.1')
    parser.add_argument('--timeout', type=float, default=30, help='启动/优雅停止等待秒数（1–300，默认 30）')
    parser.add_argument('--force', action='store_true', help='仅 stop：优雅停止超时后 SIGKILL 已验证进程')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 300:
        parser.error('--timeout 必须在 1–300 秒之间')
    if args.local and (args.service, args.action) != ('frontend', 'start'):
        parser.error('--local 仅用于 frontend start')
    if args.force and args.action != 'stop':
        parser.error('--force 仅用于 stop')
    try:
        manager = Manager(configuration(args.service, args.local, require_runtime=args.action == 'start'))
        with manager.locked():
            if args.action == 'start':
                manager.start(args.timeout)
            elif args.action == 'stop':
                manager.stop(args.timeout, args.force)
            else:
                return manager.status()
        return 0
    except (ServiceError, OSError) as exc:
        print(f'操作失败：{exc}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('操作已取消；请使用 status 检查状态。', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
