"""Configuration loading and strict validation.

Anything malformed (missing file, bad TOML, wrong types, bad paths) raises
ConfigError, which the CLI maps to exit code 3.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

DEFAULT_CONFIG_NAME = "devdoctor.toml"


class ConfigError(Exception):
    """Raised for unreadable or malformed configuration."""


@dataclass(frozen=True)
class ToolSpec:
    name: str
    required: bool = False
    min_version: Optional[str] = None
    version_args: tuple = ("--version",)


@dataclass(frozen=True)
class Config:
    python_min: str = "3.9"
    require_venv: bool = False
    disk_path: str = "."
    disk_min_free_gb: float = 1.0
    disk_warn_free_gb: float = 5.0
    env_required: tuple = ("PATH",)
    env_recommended: tuple = ()
    tools: tuple = field(default_factory=lambda: (
        ToolSpec("git", required=True),
        ToolSpec("pip", required=False),
    ))


_ALLOWED = {
    "python": {"min_version", "require_venv"},
    "disk": {"path", "min_free_gb", "warn_free_gb"},
    "env": {"required", "recommended"},
    "tools": set(),
}
_TOOL_KEYS = {"name", "required", "min_version", "version_args"}


def _bad(msg: str) -> ConfigError:
    return ConfigError(msg)


def _version_ok(v: Any, where: str) -> str:
    if not isinstance(v, str) or not v or not all(p.isdigit() for p in v.split(".")):
        raise _bad(f"{where}: expected a dotted version like \"3.10\", got {v!r}")
    return v


def _path_ok(v: Any, where: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise _bad(f"{where}: expected a non-empty path string, got {v!r}")
    if "\x00" in v:
        raise _bad(f"{where}: path contains a NUL byte")
    return v


def _num(v: Any, where: str) -> float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise _bad(f"{where}: expected a non-negative number, got {v!r}")
    return float(v)


def _str_list(v: Any, where: str) -> tuple:
    if not isinstance(v, list) or not all(isinstance(x, str) and x.strip() for x in v):
        raise _bad(f"{where}: expected a list of non-empty strings")
    return tuple(v)


def _tool(raw: Any, i: int) -> ToolSpec:
    where = f"tools[{i}]"
    if not isinstance(raw, dict):
        raise _bad(f"{where}: expected a table")
    unknown = set(raw) - _TOOL_KEYS
    if unknown:
        raise _bad(f"{where}: unknown key(s): {', '.join(sorted(unknown))}")
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip() or any(c in name for c in " \t\n/\\\x00"):
        raise _bad(f"{where}.name: must be a bare executable name (no spaces or path separators), got {name!r}")
    req = raw.get("required", False)
    if not isinstance(req, bool):
        raise _bad(f"{where}.required: expected true/false")
    minv = raw.get("min_version")
    if minv is not None:
        _version_ok(minv, f"{where}.min_version")
    va = raw.get("version_args", ["--version"])
    if not isinstance(va, list) or not all(isinstance(x, str) for x in va):
        raise _bad(f"{where}.version_args: expected a list of strings")
    return ToolSpec(name, req, minv, tuple(va))


def parse_config(data: Dict[str, Any]) -> Config:
    unknown = set(data) - set(_ALLOWED)
    if unknown:
        raise _bad(f"unknown top-level section(s): {', '.join(sorted(unknown))}")
    base = Config()
    kw: Dict[str, Any] = {}

    py = data.get("python", {})
    if not isinstance(py, dict):
        raise _bad("[python]: expected a table")
    _check_keys("python", py)
    if "min_version" in py:
        kw["python_min"] = _version_ok(py["min_version"], "python.min_version")
    if "require_venv" in py:
        if not isinstance(py["require_venv"], bool):
            raise _bad("python.require_venv: expected true/false")
        kw["require_venv"] = py["require_venv"]

    disk = data.get("disk", {})
    if not isinstance(disk, dict):
        raise _bad("[disk]: expected a table")
    _check_keys("disk", disk)
    if "path" in disk:
        kw["disk_path"] = _path_ok(disk["path"], "disk.path")
    if "min_free_gb" in disk:
        kw["disk_min_free_gb"] = _num(disk["min_free_gb"], "disk.min_free_gb")
    if "warn_free_gb" in disk:
        kw["disk_warn_free_gb"] = _num(disk["warn_free_gb"], "disk.warn_free_gb")
    lo = kw.get("disk_min_free_gb", base.disk_min_free_gb)
    hi = kw.get("disk_warn_free_gb", base.disk_warn_free_gb)
    if lo > hi:
        raise _bad("disk: min_free_gb must be <= warn_free_gb")

    env = data.get("env", {})
    if not isinstance(env, dict):
        raise _bad("[env]: expected a table")
    _check_keys("env", env)
    if "required" in env:
        kw["env_required"] = _str_list(env["required"], "env.required")
    if "recommended" in env:
        kw["env_recommended"] = _str_list(env["recommended"], "env.recommended")

    if "tools" in data:
        if not isinstance(data["tools"], list):
            raise _bad("tools: expected an array of tables ([[tools]])")
        kw["tools"] = tuple(_tool(t, i) for i, t in enumerate(data["tools"]))
        names = [t.name for t in kw["tools"]]
        if len(set(names)) != len(names):
            raise _bad("tools: duplicate tool names")
    return Config(**{**base.__dict__, **kw})


def _check_keys(section: str, table: Dict[str, Any]) -> None:
    unknown = set(table) - _ALLOWED[section]
    if unknown:
        raise _bad(f"[{section}]: unknown key(s): {', '.join(sorted(unknown))}")


def load_config(path: Optional[str], cwd: Optional[Path] = None) -> Config:
    """Load config from `path`, or ./devdoctor.toml if present, else defaults."""
    if path is None:
        candidate = (cwd or Path.cwd()) / DEFAULT_CONFIG_NAME
        if not candidate.is_file():
            return Config()
        p = candidate
    else:
        if "\x00" in path or not path.strip():
            raise _bad(f"--config: malformed path {path!r}")
        p = Path(path).expanduser()
        if not p.exists():
            raise _bad(f"config file not found: {p}")
        if not p.is_file():
            raise _bad(f"config path is not a file: {p}")
    try:
        with open(p, "rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as e:
        raise _bad(f"{p}: invalid TOML: {e}") from None
    except OSError as e:
        raise _bad(f"{p}: cannot read: {e.strerror or e}") from None
    return parse_config(data)
