#!/usr/bin/env sh
# Create an isolated virtual environment and install devdoctor (+ test deps) into it.
set -eu
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
echo "Done. Activate with:  . .venv/bin/activate   then run:  devdoctor"
