import json

from conftest import GIB, make_ctx
from devdoctor.checks import parse_version, run_all
from devdoctor.config import Config, ToolSpec
from devdoctor.models import EXIT_FAIL, EXIT_OK, EXIT_WARN, Report, Status
from devdoctor.report import to_json, to_text


def report_for(ctx, cfg, **kw):
    return Report(run_all(ctx, cfg), dict(ctx.platform_info), "0.0.0", **kw)


# ---- success ---------------------------------------------------------------
def test_healthy_machine_is_ok(ctx, cfg):
    r = report_for(ctx, cfg)
    assert r.overall is Status.OK
    assert r.exit_code == EXIT_OK
    assert r.summary() == {"ok": 5, "warn": 0, "fail": 0}


def test_report_is_deterministic(ctx, cfg):
    a, b = to_json(report_for(ctx, cfg)), to_json(report_for(make_ctx(), cfg))
    assert a == b
    data = json.loads(a)
    assert [c["id"] for c in data["checks"]] == sorted(c["id"] for c in data["checks"])


def test_env_values_never_leak(cfg):
    ctx = make_ctx(environ={"PATH": "/p", "API_KEY": "s3cret-value"})
    out = to_json(report_for(ctx, Config(env_required=("PATH", "API_KEY"), tools=())))
    assert "s3cret-value" not in out


def test_text_report_has_summary(ctx, cfg):
    text = to_text(report_for(ctx, cfg))
    assert "[ OK ] Python version" in text and "exit code 0" in text


# ---- missing dependency ----------------------------------------------------
def test_missing_required_tool_fails(ctx):
    cfg = Config(tools=(ToolSpec("docker", required=True),))
    r = report_for(ctx, cfg)
    tool = next(c for c in r.checks if c.id == "tool:docker")
    assert tool.status is Status.FAIL and tool.details["found"] is False
    assert r.exit_code == EXIT_FAIL


def test_missing_optional_tool_warns(ctx):
    r = report_for(ctx, Config(tools=(ToolSpec("node"),)))
    assert r.overall is Status.WARN and r.exit_code == EXIT_WARN


def test_fail_on_fail_ignores_warnings(ctx):
    r = report_for(ctx, Config(tools=(ToolSpec("node"),)), fail_on="fail")
    assert r.overall is Status.WARN and r.exit_code == EXIT_OK


def test_old_tool_version_is_flagged(ctx):
    cfg = Config(tools=(ToolSpec("git", required=True, min_version="3.0"),))
    git = next(c for c in report_for(ctx, cfg).checks if c.id == "tool:git")
    assert git.status is Status.FAIL and "older" in git.message


def test_unparseable_version_warns():
    ctx = make_ctx(run=lambda c, t: (0, "no numbers here"))
    git = next(c for c in report_for(ctx, Config(tools=(ToolSpec("git"),))).checks if c.id == "tool:git")
    assert git.status is Status.WARN


def test_tool_that_crashes_warns():
    def boom(cmd, t):
        raise OSError("exec format error")
    git = next(c for c in report_for(make_ctx(run=boom), Config(tools=(ToolSpec("git"),))).checks
               if c.id == "tool:git")
    assert git.status is Status.WARN


# ---- python / disk / env ---------------------------------------------------
def test_old_python_fails(cfg):
    r = report_for(make_ctx(python_version=(3, 8, 10)), Config(python_min="3.9", tools=()))
    assert next(c for c in r.checks if c.id == "python").status is Status.FAIL


def test_not_in_venv_warns_when_required():
    r = report_for(make_ctx(in_venv=False), Config(require_venv=True, tools=()))
    assert next(c for c in r.checks if c.id == "python").status is Status.WARN


def test_low_disk_levels():
    cfg = Config(disk_min_free_gb=1, disk_warn_free_gb=5, tools=())
    for free, expected in [(0.5, Status.FAIL), (3, Status.WARN), (50, Status.OK)]:
        ctx = make_ctx(disk_usage=lambda p, f=free: (100 * GIB, 0, int(f * GIB)))
        assert next(c for c in report_for(ctx, cfg).checks if c.id == "disk").status is expected


def test_unreadable_disk_path_fails():
    def nope(p):
        raise FileNotFoundError(2, "No such file or directory")
    r = report_for(make_ctx(disk_usage=nope), Config(disk_path="/nope", tools=()))
    assert next(c for c in r.checks if c.id == "disk").status is Status.FAIL


def test_missing_required_env_fails():
    r = report_for(make_ctx(environ={}), Config(env_required=("PATH",), tools=()))
    assert next(c for c in r.checks if c.id == "env").status is Status.FAIL


def test_parse_version():
    assert parse_version("git version 2.43.0.windows.1") == (2, 43, 0, 1) or parse_version("x 2.43.0") == (2, 43, 0)
    assert parse_version("nothing") is None
