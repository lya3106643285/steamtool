"""CLI composition and one-run lifecycle."""
import argparse
import asyncio
import sys

from config import load_config
from error_handler import Failure
from Ports.registry import build_registry
from Ports.request_executor import Executor
from scripts import game
from scripts.persistence import new_run, save
from scripts.runtime_debug import Runtime, utcnow


def parser():
    cli = argparse.ArgumentParser(description="只读 Steam 本地数据工具")
    sub = cli.add_subparsers(dest="feature")
    target = sub.add_parser("game", help="按名称、AppID 或官方 app URL 查询")
    target.add_argument("query", nargs="?")
    target.add_argument("--appid", type=int)
    return cli


async def execute(args, config):
    stem, document = new_run(args.feature, config)
    runtime = Runtime(config.output_dir / (stem + ".runtime.jsonl"), document["meta"]["run_id"], args.feature, config.secrets, config.log_level)
    executor = Executor(config, runtime.event)
    registry = build_registry(executor)
    try:
        await game.run(registry, config, document, runtime, query=args.query, appid=args.appid)
    except Failure as exc:
        document["errors"].append(exc.info)
        document["status"] = "failed"
    except Exception as exc:
        failure = Failure("INTERNAL_ERROR", "Unexpected workflow error", scope="feature", exception_type=type(exc).__name__)
        document["errors"].append(failure.info)
        document["status"] = "failed"
        runtime.event("workflow_failed", level="ERROR", **runtime.diagnostic(exc))
    finally:
        await registry.close()
        await executor.close()
    document["meta"]["finished_at"] = utcnow()
    try:
        runtime.event("export_started")
        path = save(document, config.output_dir / (stem + ".json"), runtime.redact)
        runtime.event("export_saved", message=str(path))
        runtime.event("run_finished", status=document["status"], summary=runtime.summary())
        print(runtime.redact(str(path)))
    finally:
        runtime.close()
    return {"ok": 0, "partial": 2, "needs_selection": 2, "failed": 1, "cancelled": 130}[document["status"]]


def main():
    cli = parser()
    args = cli.parse_args()
    if not args.feature:
        cli.print_help()
        return 0
    try:
        return asyncio.run(execute(args, load_config()))
    except Failure as exc:
        print(f"{exc.code}: {exc.info['message']}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
