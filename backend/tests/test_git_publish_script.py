"""Real Git operations, but only disposable repositories and local bare remotes.

Never stages/commits/tags/pushes the project repository or contacts GitHub.
"""
import os
import fcntl
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]


class Project:
    def __init__(self, directory):
        self.base = directory
        self.root = directory / 'project with spaces'
        self.root.mkdir()
        (self.root / 'scripts').mkdir()
        self.script = self.root / 'scripts/commit-to-github.sh'
        shutil.copyfile(ROOT / 'scripts/commit-to-github.sh', self.script)
        shutil.copyfile(ROOT / '.gitignore', self.root / '.gitignore')
        self.write('README.md', '# Synthetic test project\n')
        self.env = {key: value for key, value in os.environ.items() if not key.startswith('GIT_')}
        self.env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM='1', GIT_TERMINAL_PROMPT='0')
        self.git('init', '-q')
        self.git('symbolic-ref', 'HEAD', 'refs/heads/main')
        self.git('config', 'user.name', 'Synthetic Tester')
        self.git('config', 'user.email', 'synthetic@example.invalid')

    def write(self, name, content):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def git(self, *args, check=True, cwd=None):
        result = subprocess.run(['git', *args], cwd=cwd or self.root, env=self.env,
                                text=True, capture_output=True, timeout=15)
        if check: assert result.returncode == 0, result.stderr
        return result.stdout.strip() if check else result

    def run(self, *args, check=True):
        result = subprocess.run(['bash', str(self.script), *args], cwd=self.base, env=self.env,
                                text=True, capture_output=True, timeout=20)
        if check: assert result.returncode == 0, result.stdout + result.stderr
        return result

    def remote(self, name='origin'):
        path = self.base / f'{name}.git'
        self.git('init', '--bare', '-q', str(path))
        self.git('remote', 'add', name, str(path))
        return path

    def initial(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'Synthetic initial')

    def fake_build(self, exit_code=0):
        self.write('frontend/package.json', '{"scripts":{"build":"test fixture"}}\n')
        binary = self.base / 'bin'
        binary.mkdir(exist_ok=True)
        npm = binary / 'npm'
        npm.write_text(f'#!/bin/sh\nprintf "built\\n" >> "{self.base}/build-calls"\nexit {exit_code}\n')
        npm.chmod(0o755)
        self.env['PATH'] = str(binary) + os.pathsep + self.env['PATH']


@pytest.fixture
def project(tmp_path):
    return Project(tmp_path)


def test_unborn_first_commit_offline_and_ignore_generated_files(project):
    for path in ['.env', 'nohup.out', 'logs/backend.log', '.runtime/state.json', 'scripts/__pycache__/x.pyc']:
        project.write(path, 'SYNTHETIC-SECRET-NOT-FOR-PUBLISH\n')
    project.write('.env.example', 'DB_PASSWORD=placeholder\n')
    project.run('-m', 'first local commit', '--no-push', '--skip-build')
    assert project.git('log', '-1', '--format=%s') == 'first local commit'
    files = project.git('ls-tree', '-r', '--name-only', 'HEAD').splitlines()
    assert '.env.example' in files
    assert not any(name in files for name in ['.env', 'nohup.out', 'logs/backend.log', '.runtime/state.json'])
    assert project.git('tag', '--list') == ''
    assert project.git('remote') == ''


def test_dry_run_offline_does_not_build_touch_index_or_write_refs(project):
    project.initial()
    project.fake_build()
    project.write('README.md', '# staged edit\n')
    project.git('add', 'README.md')
    project.write('README.md', '# unstaged edit\n')
    index = project.root / '.git/index'
    before = index.read_bytes()
    head = project.git('rev-parse', 'HEAD')
    result = project.run('--version', '0.2.0', '--dry-run')
    assert '尚未配置远端' in result.stdout
    assert index.read_bytes() == before
    assert head == project.git('rev-parse', 'HEAD')
    assert project.git('tag', '--list') == ''
    assert not (project.base / 'build-calls').exists()
    assert not (project.root / '.git/fastonto-publish.lock').exists()


def test_first_commit_push_sets_explicit_branch_upstream(project):
    remote = project.remote()
    project.run('first push', '--skip-build')
    head = project.git('rev-parse', 'HEAD')
    assert project.git('--git-dir', str(remote), 'rev-parse', 'refs/heads/main') == head
    assert project.git('rev-parse', '--abbrev-ref', '@{upstream}') == 'origin/main'


def test_annotated_tag_only_on_requested_remote_no_changelog_rewrite(project):
    remote = project.remote()
    changelog = project.write('CHANGELOG.md', '# Changelog\n\n## 自定义当前记录\n\n- Synthetic change\n')
    original = changelog.read_bytes()
    project.run('--version', 'v0.2.0', '--skip-build')
    assert project.git('cat-file', '-t', 'refs/tags/v0.2.0') == 'tag'
    assert project.git('--git-dir', str(remote), 'rev-parse', 'refs/tags/v0.2.0') == project.git('rev-parse', 'refs/tags/v0.2.0')
    assert changelog.read_bytes() == original
    assert project.git('status', '--porcelain') == ''


@pytest.mark.parametrize('options', [('--no-tag', '--version', '0.3.0'), ('--version', '0.3.0', '--no-tag')])
def test_no_tag_independent_of_option_order(project, options):
    project.run(*options, '--no-push', '--skip-build')
    assert project.git('tag', '--list') == ''
    assert project.git('log', '-1', '--format=%s') == 'Release 0.3.0'


def test_clean_tree_can_tag_and_push_existing_unpublished_commit(project):
    project.run('--no-push', '--skip-build')
    head = project.git('rev-parse', 'HEAD')
    remote = project.remote()
    project.run('--tag', '0.2.0', '--skip-build')
    assert project.git('rev-parse', 'HEAD') == head
    assert project.git('--git-dir', str(remote), 'rev-parse', 'refs/heads/main') == head
    assert project.git('rev-list', '--count', 'HEAD') == '1'


def test_clean_normal_invocation_retries_push_without_new_commit(project):
    project.run('--no-push', '--skip-build')
    remote = project.remote()
    project.run('--skip-build')
    assert project.git('rev-list', '--count', 'HEAD') == '1'
    assert project.git('--git-dir', str(remote), 'rev-parse', 'refs/heads/main') == project.git('rev-parse', 'HEAD')


def test_existing_tag_dirty_tree_rejected_before_staging(project):
    project.run('--version', '0.2.0', '--no-push', '--skip-build')
    head = project.git('rev-parse', 'HEAD')
    index = (project.root / '.git/index').read_bytes()
    project.write('README.md', '# new unpublished change\n')
    result = project.run('--version', '0.2.0', '--no-push', '--skip-build', check=False)
    assert result.returncode != 0 and '标签 v0.2.0 已存在' in result.stderr
    assert project.git('rev-parse', 'HEAD') == head
    assert (project.root / '.git/index').read_bytes() == index


def test_atomic_rejection_retains_local_commit_and_tag_can_retry(project):
    remote = project.remote()
    hook = remote / 'hooks/pre-receive'
    hook.write_text('#!/bin/sh\nexit 1\n'); hook.chmod(0o755)
    result = project.run('--version', '0.2.0', '--skip-build', check=False)
    assert result.returncode != 0 and '本地提交/标签保留' in result.stderr
    assert project.git('rev-list', '--count', 'HEAD') == '1'
    assert project.git('tag', '--list') == 'v0.2.0'
    assert project.git('--git-dir', str(remote), 'show-ref', check=False).returncode != 0
    hook.unlink()
    project.run('--version', '0.2.0', '--skip-build')
    assert project.git('rev-list', '--count', 'HEAD') == '1'
    assert project.git('--git-dir', str(remote), 'rev-parse', 'refs/heads/main') == project.git('rev-parse', 'HEAD')


def test_explicit_remote_overrides_existing_upstream(project):
    origin = project.remote()
    backup = project.remote('backup')
    project.run('--skip-build')
    original_head = project.git('rev-parse', 'HEAD')
    project.write('README.md', '# changed\n')
    project.run('--remote', 'backup', '--skip-build')
    assert project.git('--git-dir', str(origin), 'rev-parse', 'refs/heads/main') == original_head
    assert project.git('--git-dir', str(backup), 'rev-parse', 'refs/heads/main') == project.git('rev-parse', 'HEAD')


def test_no_unrelated_tags_pushed_even_with_followtags_config(project):
    remote = project.remote()
    project.run('--no-push', '--skip-build')
    project.git('tag', '-a', 'private-test-tag', '-m', 'not for remote')
    project.git('config', 'push.followTags', 'true')
    project.run('--version', '0.2.0', '--skip-build')
    assert project.git('--git-dir', str(remote), 'tag', '--list') == 'v0.2.0'


@pytest.mark.parametrize('path', ['.env', '.env.production', 'logs/error.log', '.runtime/initial-admin.txt',
                                  'scripts/__pycache__/x.pyc', 'secret.key', '.aws/credentials', 'nohup.out'])
def test_forced_staged_sensitive_paths_fail_closed_without_printing_contents(project, path):
    project.write(path, 'SYNTHETIC-SENSITIVE-VALUE\n')
    project.git('add', '-f', path)
    before = (project.root / '.git/index').read_bytes()
    result = project.run('--no-push', '--skip-build', check=False)
    assert result.returncode != 0 and '禁止提交' in result.stderr
    assert 'SYNTHETIC-SENSITIVE-VALUE' not in result.stdout + result.stderr
    assert (project.root / '.git/index').read_bytes() == before
    assert project.git('rev-parse', '--verify', 'HEAD', check=False).returncode != 0


def test_build_failure_does_not_stage_or_commit(project):
    project.fake_build(exit_code=7)
    result = project.run('--no-push', check=False)
    assert result.returncode != 0 and '构建失败' in result.stderr
    assert not (project.root / '.git/index').exists()
    assert (project.base / 'build-calls').exists()
    assert project.git('rev-parse', '--verify', 'HEAD', check=False).returncode != 0


def test_successful_build_runs_and_skip_build_really_skips(project):
    project.fake_build()
    project.run('--no-push')
    marker = project.base / 'build-calls'
    assert marker.read_text() == 'built\n'
    project.run('--no-push', '--skip-build')
    assert marker.read_text() == 'built\n'


def test_missing_remote_fails_before_staging(project):
    result = project.run('--skip-build', check=False)
    assert result.returncode != 0 and '未配置远端' in result.stderr
    assert not (project.root / '.git/index').exists()


def test_remote_url_credentials_never_echoed(project):
    project.git('remote', 'add', 'origin', 'https://test:SYNTHETIC-TOKEN@github.invalid/team/repo.git')
    result = project.run('--skip-build', check=False)
    assert result.returncode != 0 and 'URL' in result.stderr
    assert 'SYNTHETIC-TOKEN' not in result.stdout + result.stderr
    assert not (project.root / '.git/index').exists()


@pytest.mark.parametrize('args', [('--version', '01.2.3'), ('--version', 'wrong'), ('--version',),
                                 ('--remote', '--all'), ('--unknown',), ('-m',)])
def test_invalid_arguments_no_git_mutations(project, args):
    result = project.run(*args, check=False)
    assert result.returncode == 2
    assert not (project.root / '.git/index').exists()
    assert not (project.root / '.git/fastonto-publish.lock').exists()


def test_detached_head_and_incomplete_merge_refused(project):
    project.initial()
    project.git('checkout', '-q', '--detach')
    result = project.run('--no-push', '--skip-build', check=False)
    assert result.returncode != 0 and 'detached HEAD' in result.stderr
    project.git('checkout', '-q', 'main')
    (project.root / '.git/MERGE_HEAD').write_text(project.git('rev-parse', 'HEAD') + '\n')
    result = project.run('--no-push', '--skip-build', check=False)
    assert result.returncode != 0 and '未完成' in result.stderr


def test_inherited_index_override_rejected(project):
    project.env['GIT_INDEX_FILE'] = str(project.base / 'alternate-index')
    result = project.run('--no-push', '--skip-build', check=False)
    assert result.returncode != 0 and 'GIT_INDEX_FILE' in result.stderr
    assert not (project.base / 'alternate-index').exists()


def test_publish_lock_rejects_concurrent_execution(project):
    with (project.root / '.git/fastonto-publish.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = project.run('--no-push', '--skip-build', check=False)
        assert result.returncode != 0
        assert '已有提交/发布脚本' in result.stderr
        assert not (project.root / '.git/index').exists()


def test_branch_switch_during_build_aborts_before_commit(project):
    project.initial()
    project.fake_build()
    npm = project.base / 'bin/npm'
    npm.write_text(f'#!/bin/sh\ngit -C "{project.root}" checkout -qb unexpected\n')
    npm.chmod(0o755)
    result = project.run('--no-push', check=False)
    assert result.returncode != 0 and 'HEAD 已变化' in result.stderr
    assert project.git('rev-list', '--count', 'HEAD') == '1'


def test_diverged_remote_is_not_force_pushed_and_tag_not_partially_published(project):
    remote = project.remote()
    project.run('--skip-build')
    clone = project.base / 'other clone'
    project.git('clone', '-q', '--branch', 'main', str(remote), str(clone))
    project.git('config', 'user.name', 'Other Synthetic Tester', cwd=clone)
    project.git('config', 'user.email', 'other@example.invalid', cwd=clone)
    (clone / 'remote-only.txt').write_text('remote change\n')
    project.git('add', '-A', cwd=clone)
    project.git('commit', '-qm', 'remote change', cwd=clone)
    project.git('push', '-q', 'origin', 'main', cwd=clone)
    remote_head = project.git('--git-dir', str(remote), 'rev-parse', 'refs/heads/main')
    project.write('README.md', '# conflicting local history\n')
    result = project.run('--version', '0.3.0', '--skip-build', check=False)
    assert result.returncode != 0
    assert project.git('--git-dir', str(remote), 'rev-parse', 'refs/heads/main') == remote_head
    assert project.git('--git-dir', str(remote), 'tag', '--list') == ''
    assert project.git('tag', '--list') == 'v0.3.0'
    assert project.git('rev-list', '--count', 'HEAD') == '2'
