"""Result envelopes and exclusive, atomic local JSON publication."""
import json
import os
from pathlib import Path
import tempfile
import unicodedata
import uuid

from steamtool.error_handler import Failure
from steamtool.scripts.runtime_debug import output_now
from schema.version import LEGACY_SCHEMA_VERSION


def normalize(name):
    return " ".join(unicodedata.normalize("NFKC", name).casefold().split())


def new_run(feature, config):
    run_id = uuid.uuid4().hex[:12]
    started = output_now()
    stem = started.strftime("%Y%m%dT%H%M%S%f") + f"_北京时间_{feature}_{run_id}"
    result = dict(schema_version=LEGACY_SCHEMA_VERSION, meta=dict(run_id=run_id, feature=feature,
                  started_at=started.isoformat(), finished_at=None, subject_steamid=config.steamid or None,
                  output_timezone="北京时间",
                  language=config.language, store_country=config.country), status="ok",
                  data=dict(items=[], resolution=None, summary={}), id_map={}, name_index={}, coverage={}, errors=[])
    return stem, result


def index_app(result, appid, name=None, source=None):
    key = str(appid)
    old = result["id_map"].get(key, {})
    name = name or old.get("canonical_name")
    result["id_map"][key] = dict(canonical_name=name, state="ok" if name else "unavailable", source=source or old.get("source"))
    if name:
        ids = result["name_index"].setdefault(normalize(name), [])
        if appid not in ids:
            ids.append(appid)
            ids.sort()


def save(result, path, redact=lambda x: x, *, amend_current=False):
    path = Path(path)
    temporary = None
    try:
        payload = json.dumps(redact(result), ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False, prefix=".export-") as file:
            temporary = file.name
            file.write(payload)
            file.flush()
            os.fsync(file.fileno())
        # link is atomic and refuses to clobber an existing run, unlike replace.
        if amend_current:
            existing = json.loads(path.read_text(encoding="utf-8"))
            existing_id = existing.get("run", existing.get("meta", {})).get("run_id")
            result_id = result.get("run", result.get("meta", {})).get("run_id")
            if not result_id or existing_id != result_id:
                raise ValueError("Refusing to amend a different run")
            os.replace(temporary, path)
            temporary = None
        else:
            os.link(temporary, path)
        return path
    except (OSError, ValueError, TypeError) as exc:
        raise Failure("OUTPUT_WRITE_FAILED", "Cannot save business JSON", source="persistence", scope="run", exception_type=type(exc).__name__) from None
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
