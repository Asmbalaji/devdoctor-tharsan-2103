# devdoctor

A small, installable CLI that inspects a machine and produces a **deterministic**
developer-environment health report - human-readable or structured JSON - with
meaningful exit codes for use in scripts and CI.

## What it checks

| Check | ID | Fails when | Warns when |
|---|---|---|---|
| Python version | `python` | older than `python.min_version` | not in a venv (if `require_venv = true`) |
| Disk space | `disk` | free space < `min_free_gb`, or path unreadable | free space < `warn_free_gb` |
| Environment variables | `env` | a `required` variable is unset/empty | a `recommended` variable is unset |
| Developer tools | `tool:<name>` | required tool missing / too old | optional tool missing, too old, or version unreadable |

Environment variable **values are never printed** - only whether they are set.

## Install (isolated virtual environment)

```sh
./setup.sh                 # creates .venv, installs devdoctor + test deps
. .venv/bin/activate
devdoctor --help
```

Manual equivalent: `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[test]"`.
Windows: `py -m venv .venv`, `.venv\Scripts\activate`, `pip install -e ".[test]"`.

To distribute: `pip install build && python -m build` produces a wheel and sdist in `dist/`;
end users can `pipx install devdoctor-0.1.0-py3-none-any.whl`.

## Usage

```sh
devdoctor                              # text report; uses ./devdoctor.toml if present
devdoctor -c devdoctor.example.toml    # explicit config
devdoctor -f json                      # JSON on stdout
devdoctor -f both -o report.json       # text + JSON on stdout, JSON also saved to a file
devdoctor --fail-on fail               # warnings no longer produce a non-zero exit
python -m devdoctor                    # same as the console script
```

### Exit codes

| Code | Meaning |
|---|---|
| 0 | all checks passed (or only warnings with `--fail-on fail`) |
| 1 | warnings only |
| 2 | at least one check failed |
| 3 | configuration or usage error (bad/missing config, bad flag, unwritable `--output`) |

### Configuration (`devdoctor.toml`)

See [`devdoctor.example.toml`](devdoctor.example.toml). Validation is strict: unknown keys,
wrong types, negative thresholds, NUL bytes or empty strings in paths, tool names with
spaces or path separators, and duplicate tools are all rejected with exit code 3 and a
message naming the offending key.

### JSON schema (v1)

```json
{
  "schema_version": 1, "tool": "devdoctor", "tool_version": "0.1.0",
  "platform": {"system": "Linux", "machine": "x86_64", "python_implementation": "CPython"},
  "overall": "fail", "exit_code": 2,
  "summary": {"ok": 1, "warn": 1, "fail": 3},
  "checks": [{"id": "disk", "title": "Disk space", "status": "ok", "message": "...", "details": {}}]
}
```

### Determinism

Output contains no timestamps, checks are sorted by id, JSON keys are sorted, and free
space is rounded to 0.01 GB. Two runs against the same machine state are byte-identical.
All system access goes through a `Context` object, so tests inject fake machines.

## Tests

```sh
pytest
```

Covers: success, missing/old/crashing tools, old Python, low disk, missing env vars,
malformed config paths (missing, directory, empty, NUL byte, non-string), invalid TOML,
invalid values, CLI exit codes, and output-file errors.

## Samples

- `samples/live_machine_example.txt` - report from a real run
- `samples/failing_report.json` / `.txt` - a deliberately failing configuration (exit 2)
- `samples/malformed_config_error.txt` - config errors (exit 3)

## Layout

```
pyproject.toml          package metadata + `devdoctor` console entry point
src/devdoctor/          cli.py, checks.py, config.py, models.py, report.py
tests/                  pytest suite
samples/                example configs and reports
setup.sh                venv bootstrap
```
