#!/bin/zsh
cd -- "$(dirname -- "$0")"
if [[ -x .venv/bin/python ]]; then
  .venv/bin/python voltscope.py "$@"
else
  python3 voltscope.py "$@"
fi
