"""Individual health checks. All system access goes through Context so tests can fake it."""
from __future__ import annotations

import platform
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, List, Mapping, Optional, Tuple

from .config import Config, ToolSpec
from .models import CheckResult, Status

GIB = 1024 ** 3
_VERSION_RE = re.compile(r"(\d+(?:\.\d+)+)")


def parse_version(text: str) -> Optional[Tuple[int, ...]]:
    m = _VERSION_RE.search(text or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else None


def _tuple(v: str) -> Tuple[int, ...]:
    return tuple(int(x) for x in v.split("."))


def _at_least(found: Tuple[int, ...], minimum: Tuple[int, ...]) -> bool:
    n = max(len(found), len(minimum))
    pad = lambda t: t + (0,) * (n - len(t))  # noqa: E731
    return pad(found) >= pad(minimum)


def _default_run(cmd: List[str], timeout: float) -> Tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or p.stderr or "").strip()


@dataclass
class Context:
    environ: Mapping[str, str]
    which: Callable[[str], Optional[str]]
    run: Callable[[List[str], float], Tuple[int, str]]
    disk_usage: Callable[[str], Tuple[int, int, int]]  # total, used, free (bytes)
    python_version: Tuple[int, int, int]
    in_venv: bool
    platform_info: Mapping[str, str]

    @classmethod
    def system(cls) -> "Context":
        import os

        return cls(
            environ=os.environ,
            which=shutil.which,
            run=_default_run,
            disk_usage=lambda p: tuple(shutil.disk_usage(p)),  # type: ignore[arg-type]
            python_version=tuple(sys.version_info[:3]),  # type: ignore[arg-type]
            in_venv=sys.prefix != getattr(sys, "base_prefix", sys.prefix),
            platform_info={
                "system": platform.system(),
                "machine": platform.machine(),
                "python_implementation": platform.python_implementation(),
            },
        )


def check_python(ctx: Context, cfg: Config) -> CheckResult:
    cur = ctx.python_version
    cur_s = ".".join(map(str, cur))
    details = {"version": cur_s, "minimum": cfg.python_min, "in_virtualenv": ctx.in_venv}
    if not _at_least(cur, _tuple(cfg.python_min)):
        return CheckResult("python", "Python version", Status.FAIL,
                           f"Python {cur_s} is older than required {cfg.python_min}", details)
    if cfg.require_venv and not ctx.in_venv:
        return CheckResult("python", "Python version", Status.WARN,
                           f"Python {cur_s} OK, but not running inside a virtual environment", details)
    return CheckResult("python", "Python version", Status.OK,
                       f"Python {cur_s} (>= {cfg.python_min})", details)


def check_disk(ctx: Context, cfg: Config) -> CheckResult:
    details = {"path": cfg.disk_path, "min_free_gb": cfg.disk_min_free_gb,
               "warn_free_gb": cfg.disk_warn_free_gb}
    try:
        total, _used, free = ctx.disk_usage(cfg.disk_path)
    except (OSError, ValueError) as e:
        reason = getattr(e, "strerror", None) or str(e)
        return CheckResult("disk", "Disk space", Status.FAIL,
                           f"cannot inspect {cfg.disk_path!r}: {reason}", details)
    free_gb = round(free / GIB, 2)
    details.update(free_gb=free_gb, total_gb=round(total / GIB, 2))
    if free_gb < cfg.disk_min_free_gb:
        return CheckResult("disk", "Disk space", Status.FAIL,
                           f"{free_gb} GB free is below the {cfg.disk_min_free_gb} GB minimum", details)
    if free_gb < cfg.disk_warn_free_gb:
        return CheckResult("disk", "Disk space", Status.WARN,
                           f"{free_gb} GB free is below the {cfg.disk_warn_free_gb} GB comfort threshold", details)
    return CheckResult("disk", "Disk space", Status.OK, f"{free_gb} GB free", details)


def check_env(ctx: Context, cfg: Config) -> CheckResult:
    """Reports which variables are set. Values are never included (they may be secrets)."""
    missing_req = sorted(v for v in cfg.env_required if not ctx.environ.get(v))
    missing_rec = sorted(v for v in cfg.env_recommended if not ctx.environ.get(v))
    details = {"required": sorted(cfg.env_required), "recommended": sorted(cfg.env_recommended),
               "missing_required": missing_req, "missing_recommended": missing_rec}
    if missing_req:
        return CheckResult("env", "Environment variables", Status.FAIL,
                           "missing required: " + ", ".join(missing_req), details)
    if missing_rec:
        return CheckResult("env", "Environment variables", Status.WARN,
                           "missing recommended: " + ", ".join(missing_rec), details)
    return CheckResult("env", "Environment variables", Status.OK, "all expected variables are set", details)


def check_tool(ctx: Context, spec: ToolSpec) -> CheckResult:
    cid, title = f"tool:{spec.name}", f"Tool: {spec.name}"
    details: dict[str, Any] = {"required": spec.required, "min_version": spec.min_version}
    missing_status = Status.FAIL if spec.required else Status.WARN
    path = ctx.which(spec.name)
    if not path:
        details["found"] = False
        kind = "required" if spec.required else "optional"
        return CheckResult(cid, title, missing_status, f"{kind} tool not found on PATH", details)
    details["found"] = True
    details["path"] = path
    try:
        code, out = ctx.run([path, *spec.version_args], 10.0)
    except (OSError, subprocess.SubprocessError) as e:
        return CheckResult(cid, title, Status.WARN, f"found but could not run: {type(e).__name__}", details)
    ver = parse_version(out) if code == 0 else None
    if ver is None:
        return CheckResult(cid, title, Status.WARN, "found but version could not be determined", details)
    ver_s = ".".join(map(str, ver))
    details["version"] = ver_s
    if spec.min_version and not _at_least(ver, _tuple(spec.min_version)):
        return CheckResult(cid, title, missing_status, f"version {ver_s} is older than {spec.min_version}", details)
    return CheckResult(cid, title, Status.OK, f"version {ver_s}", details)


def run_all(ctx: Context, cfg: Config) -> List[CheckResult]:
    results = [check_python(ctx, cfg), check_disk(ctx, cfg), check_env(ctx, cfg)]
    results += [check_tool(ctx, t) for t in sorted(cfg.tools, key=lambda t: t.name)]
    return sorted(results, key=lambda r: r.id)  # stable, deterministic order
