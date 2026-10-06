"""Install the wheel outside the checkout and exercise the real public command."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile

import pytest

from steamtool.config import config_home, load_config
from steamtool.error_handler import Failure
from tests.test_lifecycle import has_event, wait_for, project

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def installed(tmp_path_factory):
    directory = tmp_path_factory.mktemp('installed-cli')
    source = directory / 'source'
    source.mkdir()
    for name in ('pyproject.toml', 'MANIFEST.in', 'README.md', 'requirements.txt', '.env.example'):
        shutil.copy2(ROOT / name, source / name)
    for package in ('steamtool', 'schema'):
        shutil.copytree(ROOT / package, source / package, ignore=shutil.ignore_patterns('__pycache__'))
    wheels = directory / 'wheels'
    built = subprocess.run([sys.executable, '-m', 'pip', 'wheel', str(source), '--no-deps', '--no-build-isolation', '--no-index', '-w', str(wheels)], capture_output=True, text=True, timeout=30)
    assert built.returncode == 0, built.stderr
    wheel = next(wheels.glob('*.whl'))
    # A throwaway environment tests installation isolation; runtime remains Conda-managed.
    environment = directory / 'environment'
    subprocess.run([sys.executable, '-m', 'venv', '--system-site-packages', str(environment)], check=True, capture_output=True, timeout=30)
    python = environment / 'bin/python'
    result = subprocess.run([str(python), '-m', 'pip', 'install', '--no-index', '--no-deps', '--ignore-installed', str(wheel)], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    return environment / 'bin/steamtool', wheel


def isolated_env(home):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('STEAM_', 'STEAMTOOL_')) and k not in {'OUTPUT_DIR', 'PYTHONPATH'}}
    env['STEAMTOOL_HOME'] = str(home)
    return env


def invoke(command, *args, env, cwd):
    return subprocess.run([str(command), *args], env=env, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=10)


def test_wheel_is_namespaced_and_has_no_local_data(installed):
    _, wheel = installed
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert 'steamtool/resources/env.example' in names
        assert 'steamtool/main.py' in names
        assert 'schema/base.py' in names and 'schema/feature.py' in names
        assert all(n.startswith(('steamtool/', 'schema/', 'steamtool_cli-1.1.0.dist-info/')) for n in names)
        assert not any(n.endswith('/.env') or 'Outputs/' in n or '.runtime/' in n for n in names)
        template = archive.read('steamtool/resources/env.example').decode()
        assert 'STEAM_API_KEY=\n' in template and 'STEAM_FAMILY_ACCESS_TOKEN=\n' in template
        assert 'Steamtool = steamtool.main:main' in archive.read('steamtool_cli-1.1.0.dist-info/entry_points.txt').decode()


def test_installed_command_configuration_and_cwd_independence(installed, tmp_path):
    command, _ = installed
    home = tmp_path / 'home'
    env = isolated_env(home)
    for name in ('steamtool', 'teamtool', 'Steamtool'):
        assert invoke(command.with_name(name), '--version', env=env, cwd=tmp_path).stdout.strip() == 'steamtool 1.1.0'
    assert invoke(command, '--help', env=env, cwd=tmp_path).returncode == 0
    assert not home.exists()
    path = invoke(command, 'config', 'path', env=env, cwd=tmp_path)
    assert path.stdout.strip() == str(home / '.env')
    assert not home.exists()
    initialized = invoke(command, 'config', 'init', env=env, cwd=tmp_path)
    assert initialized.returncode == 0, initialized.stderr
    config = home / '.env'
    assert config.stat().st_mode & 0o777 == 0o600
    config.write_text('STEAM_STORE_COUNTRY=US\n')
    second = invoke(command, 'config', 'init', env=env, cwd='/tmp')
    assert second.returncode == 1 and config.read_text() == 'STEAM_STORE_COUNTRY=US\n'
    assert invoke(command, 'config', 'path', env=env, cwd='/tmp').stdout == path.stdout
    assert invoke(command, 'stop', env=env, cwd='/tmp').returncode == 0
    assert load_config(environ=env).country == 'US'


def test_config_import_is_private_and_never_overwrites(installed, tmp_path):
    command, _ = installed
    source = tmp_path / 'existing.env'
    source.write_text('STEAM_API_KEY=synthetic-key\nSTEAM_FAMILY_ACCESS_TOKEN=synthetic-token\n')
    env = isolated_env(tmp_path / 'home')
    imported = invoke(command, 'config', 'import', str(source), env=env, cwd='/tmp')
    assert imported.returncode == 0
    assert 'synthetic' not in imported.stdout + imported.stderr
    destination = tmp_path / 'home/.env'
    assert destination.read_bytes() == source.read_bytes()
    assert destination.stat().st_mode & 0o777 == 0o600
    source.write_text('different')
    assert invoke(command, 'config', 'import', str(source), env=env, cwd='/tmp').returncode == 1
    assert 'synthetic-key' in destination.read_text()


def test_config_home_rejects_relative_paths():
    with pytest.raises(Failure, match='absolute path'):
        config_home({'STEAMTOOL_HOME': 'relative'})


def test_installed_console_stop_saves_partial_result(installed, project):
    command, _ = installed
    root, env = project
    alias = root.parent / 'teamtool'
    alias.symlink_to(command)
    command = alias
    home = root.parent / 'cli-home'
    env.update(STEAMTOOL_HOME=str(home), STEAM_ID='76561198000000000')
    child = subprocess.Popen([str(command), 'wishlist'], env=env, cwd='/tmp', stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for(lambda: has_event(home, 'request_succeeded', 1) and has_event(home, 'request_started', 2))
        duplicate = invoke(command, 'game', '--appid', '1', env=env, cwd='/tmp')
        assert duplicate.returncode == 1 and 'already has' in duplicate.stderr
        stopped = invoke(command, 'stop', env=env, cwd='/tmp')
        assert stopped.returncode == 0, stopped.stderr
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 130, stderr
        result = json.loads(Path(stdout.strip()).read_text())
        assert result['status'] == 'cancelled'
        assert result['data']['items'][0]['store']['state'] == 'ok'
        assert not (home / '.runtime/instance.json').exists()
        assert not (root / 'Outputs').exists()
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)
