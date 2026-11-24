import json

import pytest

from conftest import make_ctx
from devdoctor.cli import main
from devdoctor.config import Config, ConfigError, load_config, parse_config


def write(tmp_path, text, name="devdoctor.toml"):
    p = tmp_path / name
    p.write_text(text)
    return str(p)


# ---- malformed configuration paths ----------------------------------------
def test_config_file_not_found(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(str(tmp_path / "missing.toml"))


def test_config_path_is_directory(tmp_path):
    with pytest.raises(ConfigError, match="not a file"):
        load_config(str(tmp_path))


@pytest.mark.parametrize("bad", ["", "   ", "a\x00b.toml"])
def test_config_path_malformed(bad):
    with pytest.raises(ConfigError, match="malformed path"):
        load_config(bad)


def test_invalid_toml(tmp_path):
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(write(tmp_path, "[disk\npath = "))


@pytest.mark.parametrize("bad_path", ["", "a\x00b", 42, True])
def test_disk_path_malformed(bad_path):
    with pytest.raises(ConfigError, match="disk.path"):
        parse_config({"disk": {"path": bad_path}})


@pytest.mark.parametrize("name", ["usr/bin/git", "my tool", "..\\git", ""])
def test_tool_name_must_be_bare(name):
    with pytest.raises(ConfigError, match="bare executable"):
        parse_config({"tools": [{"name": name}]})


@pytest.mark.parametrize("data,match", [
    ({"bogus": {}}, "unknown top-level"),
    ({"disk": {"min_free_gb": -1}}, "non-negative"),
    ({"disk": {"min_free_gb": 9, "warn_free_gb": 2}}, "<="),
    ({"python": {"min_version": "three"}}, "dotted version"),
    ({"env": {"required": "PATH"}}, "list of non-empty strings"),
    ({"tools": [{"name": "git"}, {"name": "git"}]}, "duplicate"),
])
def test_invalid_values(data, match):
    with pytest.raises(ConfigError, match=match):
        parse_config(data)


def test_autodiscovery_and_defaults(tmp_path):
    assert load_config(None, cwd=tmp_path) == Config()
    write(tmp_path, '[python]\nmin_version = "3.11"\n')
    assert load_config(None, cwd=tmp_path).python_min == "3.11"


# ---- CLI exit codes and output --------------------------------------------
GOOD = '[env]\nrequired=["PATH"]\n[[tools]]\nname="git"\nrequired=true\n'


def test_cli_success_json(tmp_path, capsys):
    code = main(["-c", write(tmp_path, GOOD), "-f", "json"], ctx=make_ctx())
    data = json.loads(capsys.readouterr().out)
    assert code == 0 and data["overall"] == "ok" and data["exit_code"] == 0


def test_cli_missing_dependency_exit_2(tmp_path, capsys):
    cfg = write(tmp_path, '[[tools]]\nname="docker"\nrequired=true\n')
    assert main(["-c", cfg], ctx=make_ctx()) == 2
    assert "[FAIL] Tool: docker" in capsys.readouterr().out


def test_cli_bad_config_exit_3(tmp_path, capsys):
    assert main(["-c", str(tmp_path / "nope.toml")], ctx=make_ctx()) == 3
    assert "config error" in capsys.readouterr().err


def test_cli_usage_error_exit_3(capsys):
    with pytest.raises(SystemExit) as e:
        main(["--format", "xml"], ctx=make_ctx())
    assert e.value.code == 3


def test_cli_writes_output_file(tmp_path):
    out = tmp_path / "r.json"
    main(["-c", write(tmp_path, GOOD), "-o", str(out)], ctx=make_ctx())
    assert json.loads(out.read_text())["schema_version"] == 1


def test_cli_unwritable_output_exit_3(tmp_path, capsys):
    assert main(["-c", write(tmp_path, GOOD), "-o", str(tmp_path / "no" / "r.json")], ctx=make_ctx()) == 3
