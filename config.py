"""Read local configuration once; secrets never appear in repr or errors."""
from dataclasses import dataclass, field
from pathlib import Path
import math
import os
import re

from dotenv import dotenv_values
from error_handler import Failure

ROOT = Path(__file__).resolve().parent


def valid_steamid(value):
    return isinstance(value, str) and bool(re.fullmatch(r"[0-9]{17}", value)) and (
        76561197960265728 <= int(value) <= 76561202255233023)


def valid_appid(value):
    return type(value) is int and 0 < value <= 2**32 - 1


@dataclass(frozen=True)
class Config:
    root: Path = ROOT
    api_key: str = field(default="", repr=False)
    steamid: str = ""
    family_token: str = field(default="", repr=False)
    language: str = "schinese"
    country: str = "CN"
    output_dir: Path = ROOT / "Outputs"
    concurrency: int = 4
    webapi_rps: float = 2
    store_rps: float = .5
    family_rps: float = .5
    connect_timeout: float = 10
    read_timeout: float = 20
    write_timeout: float = 10
    pool_timeout: float = 10
    deadline: float = 60
    max_attempts: int = 3
    backoff_base: float = 1
    backoff_cap: float = 30
    stop_grace: float = 5
    progress_interval: float = 5
    log_level: str = "INFO"

    @property
    def secrets(self):
        return tuple(v for v in (self.api_key, self.family_token) if v)


def load_config(root=ROOT, environ=None):
    values = {**dotenv_values(root / ".env", interpolate=False),
              **(os.environ if environ is None else environ)}
    def get(name, default=""):
        return str(values.get(name) or default).strip()
    def invalid(name):
        raise Failure("CONFIG_INVALID", f"Invalid configuration: {name}", source="config", scope="run")
    kwargs = {"root": root, "api_key": get("STEAM_API_KEY"), "steamid": get("STEAM_ID"),
              "family_token": get("STEAM_FAMILY_ACCESS_TOKEN"), "language": get("STEAM_LANGUAGE", "schinese"),
              "country": get("STEAM_STORE_COUNTRY", "CN").upper(), "log_level": get("LOG_LEVEL", "INFO").upper()}
    if kwargs["steamid"] and not valid_steamid(kwargs["steamid"]):
        invalid("STEAM_ID (public individual SteamID64 required)")
    if not re.fullmatch(r"[A-Z]{2}", kwargs["country"]):
        invalid("STEAM_STORE_COUNTRY")
    if not re.fullmatch(r"[a-zA-Z_-]{2,32}", kwargs["language"]):
        invalid("STEAM_LANGUAGE")
    if kwargs["log_level"] not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        invalid("LOG_LEVEL")
    numeric = {
        "concurrency": ("STEAM_MAX_CONCURRENCY", 4, int),
        "max_attempts": ("STEAM_MAX_ATTEMPTS", 3, int),
        "webapi_rps": ("STEAM_WEBAPI_RPS", 2, float),
        "store_rps": ("STEAM_STORE_RPS", .5, float),
        "family_rps": ("STEAM_FAMILY_RPS", .5, float),
        "deadline": ("STEAM_REQUEST_DEADLINE_SECONDS", 60, float),
        "backoff_base": ("STEAM_BACKOFF_BASE_SECONDS", 1, float),
        "backoff_cap": ("STEAM_BACKOFF_CAP_SECONDS", 30, float),
        "stop_grace": ("STEAM_STOP_GRACE_SECONDS", 5, float),
        "progress_interval": ("STEAM_PROGRESS_INTERVAL_SECONDS", 5, float),
    }
    numeric.update({f"{part}_timeout": (f"STEAM_{part.upper()}_TIMEOUT_SECONDS", default, float)
                    for part, default in (("connect", 10), ("read", 20), ("write", 10), ("pool", 10))})
    for attr, (name, default, convert) in numeric.items():
        try:
            value = convert(get(name, default))
            if not math.isfinite(value) or value <= 0:
                invalid(name)
            kwargs[attr] = value
        except (ValueError, OverflowError):
            invalid(name)
    kwargs["output_dir"] = (root / get("OUTPUT_DIR", "Outputs")).resolve()
    return Config(**kwargs)
