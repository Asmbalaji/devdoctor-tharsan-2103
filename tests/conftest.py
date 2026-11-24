import pytest

from devdoctor.checks import Context
from devdoctor.config import Config, ToolSpec

GIB = 1024 ** 3


def make_ctx(**over):
    base = dict(
        environ={"PATH": "/usr/bin", "HOME": "/home/dev"},
        which=lambda n: f"/usr/bin/{n}" if n in {"git", "pip"} else None,
        run=lambda cmd, t: (0, "git version 2.43.0" if "git" in cmd[0] else "pip 24.0 from /x (python 3.12)"),
        disk_usage=lambda p: (500 * GIB, 100 * GIB, 400 * GIB),
        python_version=(3, 12, 1),
        in_venv=True,
        platform_info={"system": "Linux", "machine": "x86_64", "python_implementation": "CPython"},
    )
    base.update(over)
    return Context(**base)


@pytest.fixture
def ctx():
    return make_ctx()


@pytest.fixture
def cfg():
    return Config(tools=(ToolSpec("git", required=True, min_version="2.30"), ToolSpec("pip")))
