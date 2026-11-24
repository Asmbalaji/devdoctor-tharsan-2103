from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .checks import Context, run_all
from .config import ConfigError, load_config
from .models import EXIT_CONFIG, Report
from .report import to_json, to_text

EPILOG = """exit codes:
  0  all checks passed
  1  warnings only (use --fail-on fail to treat as 0)
  2  at least one check failed
  3  configuration or usage error
"""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):  # argparse defaults to exit 2, which we reserve for FAIL
        self.print_usage(sys.stderr)
        self.exit(EXIT_CONFIG, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    p = _Parser(prog="devdoctor", description="Inspect this machine and report developer-environment health.",
                epilog=EPILOG, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("-c", "--config", help="path to a TOML config (default: ./devdoctor.toml if present)")
    p.add_argument("-f", "--format", choices=["text", "json", "both"], default="text",
                   help="output format (default: text)")
    p.add_argument("-o", "--output", help="write the JSON report to this file (in addition to stdout output)")
    p.add_argument("--fail-on", choices=["warn", "fail"], default="warn",
                   help="minimum severity that yields a non-zero exit code (default: warn)")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: Optional[List[str]] = None, ctx: Optional[Context] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config(args.config)
    except ConfigError as e:
        print(f"devdoctor: config error: {e}", file=sys.stderr)
        return EXIT_CONFIG

    ctx = ctx or Context.system()
    report = Report(checks=run_all(ctx, cfg), platform=dict(ctx.platform_info),
                    tool_version=__version__, fail_on=args.fail_on)

    if args.output:
        try:
            Path(args.output).write_text(to_json(report), encoding="utf-8")
        except OSError as e:
            print(f"devdoctor: cannot write {args.output!r}: {e.strerror or e}", file=sys.stderr)
            return EXIT_CONFIG

    if args.format in ("text", "both"):
        sys.stdout.write(to_text(report))
    if args.format in ("json", "both"):
        sys.stdout.write(to_json(report))
    return report.exit_code


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
