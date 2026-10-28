"""Lifecycle tests use temporary loopback ports, never 8025/8026 or real services."""
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts'
spec = importlib.util.spec_from_file_location('fastonto_service_manager', SCRIPTS / 'service_manager.py')
service = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = service
spec.loader.exec_module(service)

SERVER = '''
import json, os, signal, subprocess, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer
mode = sys.argv[2]
if mode == 'exit':
    print('synthetic startup failure', flush=True)
    sys.exit(7)
if mode == 'ignore':
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
if mode == 'child':
    child = subprocess.Popen([sys.executable, '-c', 'import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(120)'])
    time.sleep(.1)
print('synthetic server started', flush=True)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(503 if mode == 'unready' else 200)
        self.end_headers()
        self.wfile.write(json.dumps({'status':'ok'}).encode())
    def log_message(self, *args): pass
HTTPServer(('127.0.0.1', int(sys.argv[1])), Handler).serve_forever()
'''


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
        assert port not in {8025, 8026}, 'never use actual service ports'
        return port


@pytest.fixture
def managers(tmp_path):
    created = []
    def factory(mode='normal'):
        root = tmp_path / f'project with spaces {len(created)}'
        root.mkdir()
        server = root / 'synthetic_server.py'
        server.write_text(SERVER)
        port = free_port()
        config = service.Config('backend', root, (sys.executable, str(server), str(port), mode),
                                root, '127.0.0.1', port, '/api/health')
        manager = service.Manager(config)
        created.append(manager)
        return manager
    yield factory
    for manager in created:
        try:
            with manager.locked():
                state = manager.read_state()
                if state: manager.stop_state(state, timeout=.2, force=True)
        finally:
            if manager.child is not None:
                manager.child.wait(timeout=5)


def test_background_ready_idempotent_start_stop_and_private_files(managers):
    manager = managers()
    with manager.locked():
        manager.start(5)
        original = manager.read_state()
        pid = original['leader']['pid']
        assert pid != os.getpid()
        assert original['leader']['pgid'] == original['leader']['sid'] == pid
        assert original['leader']['sid'] != os.getsid(0)
        assert manager.status() == 0
        manager.start(5)
        assert manager.read_state()['leader']['pid'] == pid
        assert manager.log_path.stat().st_mode & 0o777 == 0o600
        assert manager.state_path.stat().st_mode & 0o777 == 0o600
        assert manager.log_path.read_text().count('synthetic server started') == 1
        manager.stop(2, False)
        assert not manager.state_path.exists()
        assert not service.process_identity(pid)
        manager.stop(2, False)
        assert manager.status() == 3


def test_start_and_stop_reject_unregistered_listener(managers, monkeypatch):
    manager = managers()
    monkeypatch.setattr(service, 'signal_verified', lambda *args: pytest.fail('must not signal unrelated listener'))
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', manager.config.port)); sock.listen()
        with manager.locked():
            with pytest.raises(service.ServiceError, match='未登记'): manager.start(1)
            with pytest.raises(service.ServiceError, match='其他进程'): manager.stop(1, False)
            assert manager.status() == 3
        assert sock.getsockname()[1] == manager.config.port


def test_service_survives_launcher_exit_without_inheriting_output_pipe(managers):
    manager = managers()
    driver = '''
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from service_manager import Config, Manager
root = Path(sys.argv[2])
port = int(sys.argv[3])
config = Config('backend', root, (sys.executable, str(root/'synthetic_server.py'), str(port), 'normal'), root, '127.0.0.1', port, '/api/health')
manager = Manager(config)
with manager.locked(): manager.start(5)
'''
    result = subprocess.run([sys.executable, '-c', driver, str(SCRIPTS), str(manager.config.root), str(manager.config.port)],
                            capture_output=True, text=True, timeout=8)
    assert result.returncode == 0, result.stderr
    with manager.locked():
        assert manager.status() == 0
        manager.stop(2, False)


def test_stale_pid_never_signals_reused_process(managers, monkeypatch):
    manager = managers()
    fake = {'pid': os.getpid(), 'ticks': 1, 'pgid': os.getpid(), 'sid': os.getpid(), 'uid': os.geteuid()}
    state = {'version': 1, 'root': str(manager.config.root), 'service': 'backend', 'port': manager.config.port,
             'uid': os.geteuid(), 'boot': manager.boot, 'host': '127.0.0.1', 'leader': fake, 'members': [fake]}
    monkeypatch.setattr(service, 'signal_verified', lambda *args: pytest.fail('must not signal stale/reused PID'))
    with manager.locked():
        manager.write_state(state)
        manager.stop(1, False)
        assert not manager.state_path.exists()


def test_failed_start_cleans_only_its_own_process(managers):
    for mode in ['exit', 'unready']:
        manager = managers(mode)
        with manager.locked():
            with pytest.raises(service.ServiceError): manager.start(.5)
            assert not manager.state_path.exists()
            assert not service.listener_inodes(manager.config.port)
            assert manager.child.poll() is not None


def test_graceful_timeout_retains_state_force_stops(managers):
    manager = managers('ignore')
    with manager.locked():
        manager.start(5)
        with pytest.raises(service.ServiceError, match='优雅停止超时'): manager.stop(.2, False)
        assert manager.state_path.exists()
        assert manager.members(manager.read_state())
        manager.stop(.2, True)
        assert not manager.state_path.exists()


def test_stop_tracks_descendants_after_leader_exits(managers):
    manager = managers('child')
    with manager.locked():
        manager.start(5)
        members = manager.members(manager.read_state())
        assert len(members) >= 2
        with pytest.raises(service.ServiceError, match='优雅停止超时'): manager.stop(.2, False)
        state = manager.read_state()
        assert service.process_identity(state['leader']['pid']) is None
        assert manager.members(state)  # Child remains verified even after parent exit.
        manager.stop(.2, True)
        assert all(service.process_identity(m['pid']) is None for m in members)


def test_switching_frontend_host_requires_restart(managers):
    manager = managers()
    with manager.locked():
        manager.start(5)
        other = service.Manager(replace(manager.config, host='0.0.0.0'))
        with pytest.raises(service.ServiceError, match='另一监听模式'): other.start(5)


def test_gateway_config_uses_private_error_log_and_https_health():
    config = service.configuration('gateway', require_runtime=False)
    assert config.name == 'gateway' and config.scheme == 'https' and config.port == 8025
    assert '-e' in config.command and str(config.root / '.runtime' / 'nginx' / 'error.log') in config.command
    assert 'daemon off;' in config.command


def test_lock_prevents_concurrent_lifecycle(managers):
    manager = managers()
    with manager.locked():
        other = service.Manager(manager.config)
        with pytest.raises(service.ServiceError, match='正在执行'):
            with other.locked(): pytest.fail('lock should not be acquired')


def test_corrupt_state_and_log_symlinks_fail_closed(managers):
    manager = managers()
    with manager.locked():
        for content in ['{broken', '[]', '{"leader": "invalid", "members": []}']:
            manager.state_path.write_text(content)
            with pytest.raises(service.ServiceError, match='PID 状态文件无效'): manager.start(1)
        manager.state_path.unlink()
        target = manager.config.root / 'untouched.txt'
        target.write_text('unchanged')
        manager.log_path.symlink_to(target)
        with pytest.raises(OSError): manager.start(1)
        assert target.read_text() == 'unchanged'


def test_stop_configuration_does_not_require_node_or_vite(monkeypatch):
    monkeypatch.setattr(service.shutil, 'which', lambda *args: None)
    config = service.configuration('frontend', require_runtime=False)
    assert config.port == 8025
    with pytest.raises(service.ServiceError, match='Node'): service.configuration('frontend')


@pytest.fixture
def orchestration(tmp_path):
    directory = tmp_path / 'scripts with spaces'
    directory.mkdir()
    for name in ['_lifecycle.sh', 'restart-backend.sh', 'restart-frontend.sh', 'restart-all.sh',
                 'start-all.sh', 'stop-all.sh', 'start-frontend-dev.sh']:
        shutil.copyfile(SCRIPTS / name, directory / name)
    calls = directory / 'calls.txt'
    for name in ['start-backend', 'stop-backend', 'start-frontend', 'stop-frontend']:
        (directory / f'{name}.sh').write_text(
            '#!/usr/bin/env bash\nset -eu\n'
            f'printf \'%s\\n\' "{name} $*" >> "$(dirname "$0")/calls.txt"\n'
            f'if [[ "${{FAIL_OPERATION:-}}" == "{name}" ]]; then exit 9; fi\n')
    def run(name, *args, fail=''):
        env = dict(os.environ, FAIL_OPERATION=fail)
        result = subprocess.run(['bash', str(directory / name), *args], cwd=tmp_path,
                                env=env, text=True, capture_output=True, timeout=5)
        return result, calls.read_text().splitlines() if calls.exists() else []
    return run


@pytest.mark.parametrize('name,expected', [
    ('restart-backend.sh', ['stop-backend', 'start-backend']),
    ('restart-frontend.sh', ['stop-frontend', 'start-frontend']),
    ('restart-all.sh', ['stop-frontend', 'stop-backend', 'start-backend', 'start-frontend']),
    ('start-all.sh', ['start-backend', 'start-frontend']),
    ('stop-all.sh', ['stop-frontend', 'stop-backend']),
])
def test_script_order(orchestration, name, expected):
    result, calls = orchestration(name)
    assert result.returncode == 0, result.stderr
    assert [call.strip() for call in calls] == expected


@pytest.mark.parametrize('name,fail,expected', [
    ('restart-backend.sh', 'stop-backend', ['stop-backend']),
    ('restart-frontend.sh', 'stop-frontend', ['stop-frontend']),
    ('restart-all.sh', 'stop-frontend', ['stop-frontend', 'stop-backend']),
    ('start-all.sh', 'start-backend', ['start-backend']),
    ('start-all.sh', 'start-frontend', ['start-backend', 'start-frontend']),
])
def test_failed_stop_never_restarts_and_start_failure_is_honest(orchestration, name, fail, expected):
    result, calls = orchestration(name, fail=fail)
    assert result.returncode != 0
    assert [call.strip() for call in calls] == expected


def test_restart_options_route_to_correct_scripts(orchestration):
    result, calls = orchestration('restart-all.sh', '--local', '--force', '--timeout', '7')
    assert result.returncode == 0, result.stderr
    assert calls == ['stop-frontend --force --timeout 7', 'stop-backend --force --timeout 7',
                     'start-backend --timeout 7', 'start-frontend --timeout 7 --local']


@pytest.mark.parametrize('args', [('--wrong',), ('--timeout',), ('--timeout', '0'), ('--timeout', '301'), ('--timeout', '1;echo unsafe')])
def test_bad_orchestration_arguments_have_no_side_effects(orchestration, args):
    result, calls = orchestration('restart-all.sh', *args)
    assert result.returncode == 2 and calls == []


def test_legacy_frontend_script_is_only_local_alias(orchestration):
    result, calls = orchestration('start-frontend-dev.sh')
    assert result.returncode == 0 and calls == ['start-frontend --local']
    assert '兼容入口' in result.stderr


def test_shell_syntax_and_conda_only_launcher():
    for script in SCRIPTS.glob('*.sh'):
        subprocess.run(['bash', '-n', str(script)], check=True)
    launcher = (SCRIPTS / '_service.sh').read_text()
    assert 'conda run --no-capture-output -n fastonto python' in launcher
    assert 'pkill' not in (SCRIPTS / 'service_manager.py').read_text()
