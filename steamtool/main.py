"""CLI, single-instance identity, cancellation, diagnostics and result lifecycle."""
import argparse
import asyncio
import ctypes
import fcntl
import json
import os
from importlib.resources import files
from pathlib import Path
import signal
import sys
import sysconfig
import tempfile
import time
import uuid

from steamtool import __version__
from steamtool.config import config_home, load_config
from steamtool.error_handler import Failure
from steamtool.contracts import build_result
from steamtool.input_parser import GamesInput, InputState, parse_names
from steamtool.Ports.registry import build_registry
from steamtool.Ports.request_executor import Executor
from steamtool.scripts import game, library, wishlist
from steamtool.scripts.persistence import new_run, save
from steamtool.scripts.runtime_debug import Redactor, Runtime, timestamp_now


def process_identity(pid):
    proc = Path('/proc') / str(pid)
    stat = (proc / 'stat').read_text()
    return dict(start_ticks=stat.rsplit(')', 1)[1].split()[19],
                boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
                uid=proc.stat().st_uid,
                argv=[s.decode() for s in (proc / 'cmdline').read_bytes().split(b'\0') if s])


class InstanceLock:
    def __init__(self, root=None):
        root = config_home() if root is None else root
        self.root = root.resolve()
        self.directory = self.root / '.runtime'
        self.file = None
        self.identity = uuid.uuid4().hex

    def __enter__(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        self.file = (self.directory / 'instance.lock').open('a+')
        try:
            fcntl.flock(self.file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.file.close()
            self.file = None
            raise Failure('CONFIG_INVALID', 'This project already has a running instance', source='lifecycle') from None
        try:
            info = dict(application='steamtool', pid=os.getpid(), project=str(self.root), instance_id=self.identity,
                        started_at=timestamp_now(), **process_identity(os.getpid()))
            self.file.seek(0)
            self.file.truncate()
            self.file.write(self.identity)
            self.file.flush()
            temporary = self.directory / ('instance-' + self.identity + '.tmp')
            temporary.write_text(json.dumps(info), encoding='utf-8')
            os.replace(temporary, self.directory / 'instance.json')
        except BaseException:
            self.__exit__(None, None, None)
            raise
        return self

    def __exit__(self, *_):
        if self.file is not None:
            try:
                path = self.directory / 'instance.json'
                if path.exists() and json.loads(path.read_text()).get('instance_id') == self.identity:
                    path.unlink()
            except (OSError, ValueError):
                pass
            finally:
                fcntl.flock(self.file, fcntl.LOCK_UN)
                self.file.close()
                self.file = None


def open_pidfd(pid):
    if hasattr(os, 'pidfd_open'):
        return os.pidfd_open(pid)
    # Some Conda Python builds omit the wrapper despite kernel/libc support.
    native = ctypes.CDLL(None, use_errno=True).pidfd_open
    native.argtypes = [ctypes.c_int, ctypes.c_uint]
    native.restype = ctypes.c_int
    descriptor = native(pid, 0)
    if descriptor < 0:
        raise OSError(ctypes.get_errno(), 'pidfd_open failed')
    return descriptor


def send_pidfd_signal(descriptor, sig):
    if hasattr(signal, 'pidfd_send_signal'):
        signal.pidfd_send_signal(descriptor, sig)
        return
    native = ctypes.CDLL(None, use_errno=True).pidfd_send_signal
    native.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint]
    native.restype = ctypes.c_int
    if native(descriptor, sig, None, 0) < 0:
        raise OSError(ctypes.get_errno(), 'pidfd_send_signal failed')


def is_steamtool_command(argv):
    if not argv or not os.path.samefile(argv[0], sys.executable):
        return False
    entries = {str(Path(sysconfig.get_path('scripts')) / name)
               for name in ('steamtool', 'teamtool', 'Steamtool')}
    entries.add(str(Path(__file__).resolve().parents[1] / 'main.py'))
    return (len(argv) >= 2 and str(Path(argv[1]).resolve()) in entries) or argv[1:3] in (
        ['-m', 'steamtool'], ['-m', 'steamtool.main'])


def stop_instance(root=None, *, wait_seconds=15):
    root = config_home() if root is None else root
    root = root.resolve()
    lock_path, metadata = root / '.runtime/instance.lock', root / '.runtime/instance.json'
    if not lock_path.exists():
        print('没有运行中的本项目实例。')
        return 0
    with lock_path.open('r+') as probe:
        try:
            fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            pass
        else:
            print('没有运行中的本项目实例（锁已释放）。')
            return 0
        pidfd = None
        try:
            info = json.loads(metadata.read_text())
            pid = info['pid']
            if type(pid) is not int or pid <= 1:
                raise ValueError('invalid PID')
            # A pidfd pins the kernel process identity before /proc validation and signaling.
            pidfd = open_pidfd(pid)
            current = process_identity(pid)
            probe.seek(0)
            if (info.get('application') != 'steamtool'
                    or info.get('project') != str(root) or info.get('instance_id') != probe.read().strip()
                    or any(current[key] != info.get(key) for key in ('start_ticks', 'boot_id', 'uid'))
                    or current['uid'] != os.getuid()
                    or not is_steamtool_command(current['argv'])
                    or current['argv'] != info.get('argv')):
                raise ValueError('identity mismatch')
            send_pidfd_signal(pidfd, signal.SIGTERM)
        except (OSError, ValueError, KeyError, AttributeError, TypeError):
            print('拒绝发送信号：无法确认锁、PID 启动身份与项目。请检查 .runtime。', file=sys.stderr)
            return 1
        finally:
            if pidfd is not None:
                os.close(pidfd)
        deadline = time.monotonic() + wait_seconds
        while time.monotonic() < deadline:
            try:
                fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                time.sleep(.05)
            else:
                print('本项目实例已停止。')
                return 0
    print('已发送停止信号，但未在等待期限内确认收尾；未执行强杀。', file=sys.stderr)
    return 1


def parser():
    cli = argparse.ArgumentParser(prog='steamtool', description='只读 Steam 本地数据工具')
    cli.add_argument('--version', action='version', version=f'steamtool {__version__}')
    sub = cli.add_subparsers(dest='feature')
    target = sub.add_parser('game', help='按名称、AppID 或官方 app URL 查询')
    target.add_argument('query', nargs='?')
    target.add_argument('--appid', type=int)
    games = sub.add_parser('games', help='按带 ASCII 双引号的名称批量查询；无参数时逐行收集')
    games.add_argument('query', nargs='?', help='例如：\'"Hades","Noita"\'，保留名称两侧双引号')
    games.add_argument('--achievements', action='store_true', help='查询逐项成就明细')
    library_cli = sub.add_parser('library', help='导出本人库及家庭候选')
    library_cli.add_argument('--achievements', action='store_true', help='查询逐项成就明细')
    def ranking_limit(value):
        number = int(value)
        if number < 0:
            raise argparse.ArgumentTypeError('排行榜数量必须为非负整数')
        return number
    library_cli.add_argument('--ranking-limit', type=ranking_limit, help='本次排行榜 Top-N（默认读取 STEAM_RANKING_LIMIT）')
    sub.add_parser('wishlist', help='导出愿望单')
    sub.add_parser('doctor', help='配置、注册、输出及少量只读网络诊断，输出 JSON')
    sub.add_parser('stop', help='安全停止使用同一配置目录的运行实例')
    configuration = sub.add_parser('config', help='初始化、导入或定位本地配置')
    actions = configuration.add_subparsers(dest='config_action', required=True)
    actions.add_parser('path', help='显示配置文件路径')
    actions.add_parser('init', help='创建空白配置模板；不覆盖已有文件')
    importing = actions.add_parser('import', help='复制已有 .env；不覆盖目标、不显示内容')
    importing.add_argument('source', type=Path)
    return cli


def configure(args):
    root = config_home()
    destination = root / '.env'
    if args.config_action == 'path':
        print(destination)
        return 0
    if destination.exists() or destination.is_symlink():
        raise Failure('CONFIG_INVALID', 'Configuration already exists; edit the existing file', source='config')
    content = (args.source.read_bytes() if args.config_action == 'import'
               else files('steamtool').joinpath('resources/env.example').read_bytes())
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation prevents accidental overwrites, including concurrent imports.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, 'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        destination.unlink(missing_ok=True)
        raise
    print(destination)
    return 0


async def doctor(registry, config, document):
    checks = dict(env_file_exists=(config.root / '.env').is_file(), api_key_configured=bool(config.api_key),
                  steamid_configured=bool(config.steamid), family_token_configured=bool(config.family_token),
                  output_writable=False, tools=[dict(name=t.name, auth_kind=t.auth_kind, rate_scope=t.rate_scope,
                      read_only=t.read_only, capability_status=t.capability_status) for t in registry.tools.values()])
    document['data']['diagnostics'] = checks
    try:
        with tempfile.TemporaryFile(dir=config.output_dir) as file:
            file.write(b'output-check')
            file.flush()
        checks['output_writable'] = True
    except OSError:
        raise Failure('OUTPUT_WRITE_FAILED', 'Output directory is not writable', source='doctor') from None
    store = await registry.call('get_app_details', {'appid': 292030, 'language': config.language, 'country': config.country})
    game.add_result(document, 'public_probe', store)
    if config.api_key and config.steamid:
        profile = await registry.call('get_player_summaries', {'steamid': config.steamid})
        game.add_result(document, 'profile_probe', profile)
    if config.family_token and config.steamid:
        family = await registry.call('get_family_group_for_user', {'steamid': config.steamid})
        game.add_result(document, 'family_probe', family)
    checks['account_capability'] = 'configured_unverified' if config.api_key and config.steamid else 'unavailable'
    checks['family_capability'] = 'experimental' if config.family_token and config.steamid else 'unavailable'
    document['status'] = 'ok' if all(checks[k] for k in ('api_key_configured', 'steamid_configured', 'family_token_configured')) and not document['errors'] else 'partial'


def unwrap_failure(exc):
    if isinstance(exc, BaseExceptionGroup):
        failures = [unwrap_failure(child) for child in exc.exceptions]
        return next((f for f in failures if f.code == 'LOG_WRITE_FAILED'), failures[0])
    if isinstance(exc, Failure):
        return exc
    return Failure('INTERNAL_ERROR', 'Unexpected workflow error', scope='feature', exception_type=type(exc).__name__)


async def execute(args, config, stop_event=None, *, transport=None):
    stop_event = stop_event or asyncio.Event()
    if args.feature == 'games' and not hasattr(args, 'names'):
        parsed = parse_names(getattr(args, 'query', None) or '')
        for item in parsed:
            if item.error:
                print(str(item.error), file=sys.stderr)
        if not parsed or any(item.error for item in parsed):
            return 2
        args.names = [item.name for item in parsed]
    stem, document = new_run(args.feature, config)
    output = config.output_dir / (stem + '.json')
    redact = Redactor(config.secrets)
    runtime = executor = registry = None
    progress = work = stopper = None
    published = False
    try:
        runtime = Runtime(config.output_dir / (stem + '.runtime.jsonl'), document['meta']['run_id'], args.feature, config.secrets, config.log_level)
        executor = Executor(config, runtime.event, transport=transport)
        registry = build_registry(executor)
        async def workflow():
            phase_start = time.monotonic()
            runtime.event("phase_started", phase=args.feature)
            if args.feature == 'game':
                await game.run(registry, config, document, runtime, query=args.query, appid=args.appid)
            elif args.feature == 'games':
                await game.run_games(registry, config, document, runtime, names=args.names,
                                     achievements_detail=getattr(args, 'achievements', False))
            elif args.feature == 'doctor':
                await doctor(registry, config, document)
            elif args.feature == 'library':
                await library.run(registry, config, document, runtime,
                                  achievements_detail=getattr(args, 'achievements', False))
            else:
                await wishlist.run(registry, config, document, runtime)
            elapsed = (time.monotonic() - phase_start) * 1000
            runtime.phases[args.feature] = elapsed
            runtime.event("phase_finished", phase=args.feature, duration_ms=elapsed)
        work = asyncio.create_task(workflow())
        progress = asyncio.create_task(runtime.progress(config.progress_interval))
        stopper = asyncio.create_task(stop_event.wait())
        done, _ = await asyncio.wait({work, progress, stopper}, return_when=asyncio.FIRST_COMPLETED)
        if progress in done:
            await progress  # A broken log stops the workflow and all new requests.
        if stop_event.is_set():
            runtime.event('stop_requested')
            executor.stop()
            await asyncio.wait({work}, timeout=config.stop_grace)
            if not work.done():
                work.cancel()
            await asyncio.gather(work, return_exceptions=True)
            document['status'] = 'cancelled'
            runtime.event('run_cancelled')
        else:
            await work
    except asyncio.CancelledError:
        document['status'] = 'cancelled'
        if executor:
            executor.stop()
    except Exception as exc:
        failure = unwrap_failure(exc)
        document['errors'].append(failure.info)
        document['status'] = 'failed'
        if runtime and not runtime.failed:
            try:
                runtime.event('workflow_failed', level='ERROR', error_code=failure.code, error_id=failure.info['error_id'], **runtime.diagnostic(exc))
            except Failure:
                pass
    finally:
        if executor:
            executor.stop()
        for task in (progress, stopper, work):
            if task and not task.done():
                task.cancel()
        await asyncio.gather(*(t for t in (progress, stopper, work) if t), return_exceptions=True)
        if registry:
            await registry.close()
        if executor:
            await executor.close()
    if document['status'] == 'cancelled' and runtime and not runtime.failed:
        for item in document['data']['items']:
            runtime.task(f"app-{item['appid']}", 'cancelled', appid=item['appid'])
    document['meta']['finished_at'] = timestamp_now()
    document['data']['items'].sort(key=lambda item: item['appid'])
    if runtime:
        document['meta']['runtime_summary'] = runtime.summary()
    def export_document():
        if args.feature in {'games', 'library', 'wishlist'}:
            result = build_result(document, config, ranking_limit=getattr(args, 'ranking_limit', None)).to_dict()
            document['status'] = result['run']['status']
            return result
        return document
    try:
        if runtime and not runtime.failed:
            runtime.event('export_started')
        path = save(export_document(), output, redact)
        published = True
        if runtime and not runtime.failed:
            runtime.event('export_saved', message=str(path))
            runtime.event('run_finished', status=document['status'], summary=runtime.summary())
    except Failure as exc:
        if not any(e['code'] == exc.code for e in document['errors']):
            document['errors'].append(exc.info)
        document['status'] = 'failed'
        print(redact(f"{exc.code}: {exc.info['message']}"), file=sys.stderr)
        if exc.code == 'LOG_WRITE_FAILED':
            # Only amend the file just published by this run; never overwrite another run.
            try:
                save(export_document(), output, redact, amend_current=published)
                published = True
            except Failure:
                print('OUTPUT_WRITE_FAILED: failed to save after log failure', file=sys.stderr)
        elif runtime and not runtime.failed:
            try:
                runtime.event('export_failed', level='ERROR', error_code=exc.code)
            except Failure:
                pass
    finally:
        if runtime:
            runtime.close()
    if args.feature == 'doctor':
        print(json.dumps(redact(document), ensure_ascii=False, indent=2, allow_nan=False))
    elif published:
        print(redact(str(output)))
    return {'ok': 0, 'partial': 2, 'needs_selection': 2, 'failed': 1, 'cancelled': 130}[document['status']]


async def read_line(prompt, stop_event):
    print(prompt, end='', flush=True, file=sys.stderr)
    loop = asyncio.get_running_loop()
    ready = loop.create_future()
    def readable():
        if not ready.done():
            ready.set_result(sys.stdin.readline())
    try:
        loop.add_reader(sys.stdin.fileno(), readable)
    except PermissionError:
        # Regular redirected files and /dev/null cannot be registered with epoll.
        return sys.stdin.readline().strip()
    stopper = asyncio.create_task(stop_event.wait())
    try:
        done, _ = await asyncio.wait({ready, stopper}, return_when=asyncio.FIRST_COMPLETED)
        return None if stopper in done else ready.result().strip()
    finally:
        loop.remove_reader(sys.stdin.fileno())
        stopper.cancel()
        await asyncio.gather(stopper, return_exceptions=True)


async def collect_game_names(stop_event, initial=None):
    collected = GamesInput()
    if initial is not None:
        collected.feed(initial)
    while not collected.done and not stop_event.is_set():
        if initial is not None and collected.state == InputState.COLLECTING_INPUT:
            collected.feed('')
            break
        if collected.state == InputState.CORRECTING_ITEM:
            print(str(collected.error), file=sys.stderr)
            prompt = f'请重新输入第 {collected.error.item_index} 项（直接回车表示放弃该项） > '
        else:
            prompt = '游戏名称（ASCII 双引号；空行结束输入） > '
        line = await read_line(prompt, stop_event)
        if line is None:
            return None
        collected.feed(line)
    return None if stop_event.is_set() else collected.names


async def session(args, config):
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)
    try:
        if args.feature:
            if args.feature == 'games':
                names = await collect_game_names(stop_event, args.query)
                if names is None:
                    return 130
                if not names:
                    return 0
                args.names = names
            return await execute(args, config, stop_event)
        while not stop_event.is_set():
            choice = await read_line('\n1 愿望单 / 2 游戏库 / 3 游戏查询 / 4 诊断 / 0 退出 > ', stop_event)
            if choice in {None, '', '0'}:
                break
            feature = {'1': 'wishlist', '2': 'library', '3': 'games', '4': 'doctor'}.get(choice)
            if not feature:
                print('请输入 0–4。')
                continue
            names = await collect_game_names(stop_event) if feature == 'games' else None
            if stop_event.is_set():
                break
            if feature == 'games' and not names:
                continue
            await execute(argparse.Namespace(feature=feature, query=None, appid=None, names=names), config, stop_event)
        return 130 if stop_event.is_set() else 0
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


def main():
    cli = parser()
    args = cli.parse_args(['stop'] if sys.argv[1:] == ['--stop-instance'] else None)
    if not args.feature and not sys.stdin.isatty():
        cli.print_help()
        return 0
    try:
        if args.feature == 'stop':
            return stop_instance()
        if args.feature == 'config':
            return configure(args)
        config = load_config()
        with InstanceLock(config.root):
            return asyncio.run(session(args, config))
    except Failure as exc:
        print(f"{exc.code}: {exc.info['message']}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f'CONFIG_INVALID: local lifecycle I/O failed ({type(exc).__name__})', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"INTERNAL_ERROR: {type(exc).__name__}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
