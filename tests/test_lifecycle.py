"""Real subprocess locks/signals with HTTP mocked by child-only sitecustomize."""
import argparse
import asyncio
from dataclasses import replace
import fcntl
import json
import os
from pathlib import Path
import pty
import shutil
import signal
import subprocess
import sys
import time

import httpx
import pytest

from config import Config, ROOT
from error_handler import Failure
import main
from scripts.persistence import new_run, save
from scripts.runtime_debug import Runtime


@pytest.fixture
def project(tmp_path):
    project = tmp_path / 'project'
    project.mkdir()
    for name in ('main.py', 'config.py', 'error_handler.py', 'start', 'stop'):
        shutil.copy2(ROOT / name, project / name)
    for name in ('Ports', 'scripts'):
        shutil.copytree(ROOT / name, project / name, ignore=shutil.ignore_patterns('__pycache__'))
    # Use the interpreter running the suite; tests have no fixed developer env path.
    (project / '.conda').symlink_to(Path(sys.prefix), target_is_directory=True)
    support = tmp_path / 'support'
    support.mkdir()
    (support / 'sitecustomize.py').write_text('''
import asyncio, os
import httpx
original = httpx.AsyncClient
async def respond(request):
    if "GetWishlistItemCount" in request.url.path:
        return httpx.Response(200, json={"response": {"count": 2}})
    if "GetWishlist" in request.url.path:
        return httpx.Response(200, json={"response": {"items": [{"appid": 1}, {"appid": 2}]}})
    if os.environ.get("FIXTURE_COOLDOWN"):
        return httpx.Response(429, headers={"Retry-After": "100"})
    appid = int(request.url.params.get("appids", "1"))
    if appid == 2 or os.environ.get("FIXTURE_SLOW"):
        await asyncio.sleep(30)
    return httpx.Response(200, json={str(appid): {"success": True, "data": {"steam_appid": appid, "name": "Synthetic"}}})
class Client(original):
    def __init__(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(respond)
        super().__init__(*args, **kwargs)
httpx.AsyncClient = Client
''')
    env = {k: v for k, v in os.environ.items() if not k.startswith('STEAM_') and k not in {'OUTPUT_DIR', 'CONDA_PREFIX', 'CONDA_DEFAULT_ENV'}}
    env.update(PYTHONPATH=str(support), STEAM_STORE_RPS='1000', STEAM_WEBAPI_RPS='1000', STEAM_STOP_GRACE_SECONDS='.05', STEAM_PROGRESS_INTERVAL_SECONDS='.05')
    return project, env


def wait_for(predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.02)
    raise AssertionError('Child process did not reach the expected state')


def has_event(project, event, appid=None):
    for path in (project / 'Outputs').glob('*.runtime.jsonl'):
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row['event'] == event and (appid is None or row.get('appid') == appid):
                return True
    return False


def test_start_help_no_stdin_and_doctor(project):
    root, env = project
    for args in (['--help'], []):
        result = subprocess.run([str(root / 'start'), *args], env=env, cwd='/tmp', stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5)
        assert result.returncode == 0 and 'game' in result.stdout
    assert not (root / 'Outputs').exists()
    result = subprocess.run([str(root / 'start'), 'doctor'], env=env, cwd='/tmp', capture_output=True, text=True, timeout=5)
    assert result.returncode == 2
    data = json.loads(result.stdout)
    assert data['data']['diagnostics']['api_key_configured'] is False
    assert data['coverage']['public_probe']['state'] == 'ok'
    assert not (root / '.runtime/instance.json').exists()


def test_stop_preserves_completed_items_and_single_instance(project):
    root, env = project
    env['STEAM_ID'] = '76561198000000000'
    child = subprocess.Popen([str(root / 'start'), 'wishlist'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for(lambda: has_event(root, 'request_succeeded', 1) and has_event(root, 'request_started', 2))
        duplicate = subprocess.run([str(root / 'start'), 'game', '--appid', '1'], env=env, capture_output=True, text=True, timeout=5)
        assert duplicate.returncode == 1 and 'already has' in duplicate.stderr
        stopped = subprocess.run([str(root / 'stop')], env=env, capture_output=True, text=True, timeout=5)
        assert stopped.returncode == 0, stopped.stderr
        stdout, stderr = child.communicate(timeout=5)
        assert child.returncode == 130, stderr
        document = json.loads(Path(stdout.strip()).read_text())
        assert document['status'] == 'cancelled'
        assert [i['appid'] for i in document['data']['items']] == [1, 2]
        assert document['data']['items'][0]['store']['state'] == 'ok'
        assert has_event(root, 'stop_requested') and has_event(root, 'run_cancelled')
        repeated = subprocess.run([str(root / 'stop')], env=env, capture_output=True, text=True, timeout=5)
        assert repeated.returncode == 0
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def test_stop_during_shared_cooldown(project):
    root, env = project
    env['FIXTURE_COOLDOWN'] = '1'
    # A small deadline yields a finished result rather than a long wait, so use 200 here.
    env['STEAM_REQUEST_DEADLINE_SECONDS'] = '200'
    child = subprocess.Popen([str(root / 'start'), 'game', '--appid', '1'], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        wait_for(lambda: has_event(root, 'cooldown_started'))
        stop = subprocess.run([str(root / 'stop')], env=env, capture_output=True, text=True, timeout=5)
        assert stop.returncode == 0
        stdout, _ = child.communicate(timeout=5)
        assert child.returncode == 130
        assert json.loads(Path(stdout.strip()).read_text())['status'] == 'cancelled'
    finally:
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def test_stale_or_reused_pid_is_not_signaled(tmp_path, monkeypatch):
    directory = tmp_path / '.runtime'
    directory.mkdir()
    info = dict(pid=os.getpid(), project=str(tmp_path), instance_id='fake', **main.process_identity(os.getpid()))
    info['start_ticks'] = 'wrong'
    (directory / 'instance.json').write_text(json.dumps(info))
    signaled = []
    monkeypatch.setattr(main, 'send_pidfd_signal', lambda *a: signaled.append(a))
    with (directory / 'instance.lock').open('w+') as lock:
        lock.write('fake')
        lock.flush()
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert main.stop_instance(tmp_path, wait_seconds=.1) == 1
    assert signaled == []
    assert main.stop_instance(tmp_path) == 0


def test_pidfd_works_when_python_wrappers_are_absent(monkeypatch):
    monkeypatch.delattr(os, 'pidfd_open', raising=False)
    monkeypatch.delattr(signal, 'pidfd_send_signal', raising=False)
    descriptor = main.open_pidfd(os.getpid())
    try:
        # Signal 0 checks our own live process; it does not terminate it.
        main.send_pidfd_signal(descriptor, 0)
    finally:
        os.close(descriptor)


def test_menu_multiple_runs_and_exit(project):
    root, env = project
    master, slave = pty.openpty()
    child = subprocess.Popen([str(root / 'start')], env=env, stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    os.close(slave)
    try:
        wait_for(lambda: (root / '.runtime/instance.json').exists())
        os.write(master, b'3\n1\n3\n1\n0\n')
        child.communicate(timeout=5)
        assert child.returncode == 0
        results = list((root / 'Outputs').glob('*.json'))
        assert len(results) == 2
        assert len({json.loads(p.read_text())['meta']['run_id'] for p in results}) == 2
    finally:
        os.close(master)
        if child.poll() is None:
            child.kill()
        child.communicate(timeout=5)


def test_log_initialization_failure_sends_no_requests(tmp_path, monkeypatch):
    calls = []
    class BrokenRuntime:
        def __init__(self, *a, **k):
            raise Failure('LOG_WRITE_FAILED', 'synthetic unwritable log', source='runtime')
    monkeypatch.setattr(main, 'Runtime', BrokenRuntime)
    config = replace(Config(), root=tmp_path, output_dir=tmp_path)
    args = argparse.Namespace(feature='game', query=None, appid=1)
    code = asyncio.run(main.execute(args, config, transport=httpx.MockTransport(lambda r: calls.append(r))))
    assert code == 1 and calls == []
    assert json.loads(next(tmp_path.glob('*.json')).read_text())['status'] == 'failed'


def test_runtime_log_failure_saves_failed_document(tmp_path, monkeypatch):
    class BreakOnExport(Runtime):
        def event(self, event, **kwargs):
            if event == 'export_saved':
                self.failed = True
                raise Failure('LOG_WRITE_FAILED', 'synthetic late log failure', source='runtime')
            return super().event(event, **kwargs)
    monkeypatch.setattr(main, 'Runtime', BreakOnExport)
    config = replace(Config(), root=tmp_path, output_dir=tmp_path)
    response = httpx.MockTransport(lambda r: httpx.Response(200, json={'1': {'success': True, 'data': {'steam_appid': 1, 'name': 'synthetic'}}}))
    args = argparse.Namespace(feature='game', query=None, appid=1)
    assert asyncio.run(main.execute(args, config, transport=response)) == 1
    document = json.loads(next(tmp_path.glob('*.json')).read_text())
    assert document['status'] == 'failed' and document['errors'][-1]['code'] == 'LOG_WRITE_FAILED'


def test_atomic_failure_does_not_damage_old_result(tmp_path, monkeypatch):
    file = tmp_path / 'old.json'
    save({'old': True}, file)
    def broken(*args):
        raise OSError('synthetic full disk')
    monkeypatch.setattr(os, 'fsync', broken)
    with pytest.raises(Failure):
        save({'new': True}, tmp_path / 'new.json')
    assert json.loads(file.read_text()) == {'old': True}
    assert not list(tmp_path.glob('.export-*'))
