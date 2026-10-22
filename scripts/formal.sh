#!/bin/zsh
# Formal evaluation on the frozen case set (see cases/CHANGELOG.md for the fingerprint).
# Needs ANTHROPIC_API_KEY in this shell. 3 runs each, cheapest first. Every run is logged in runs/.
set -e
cd "$(dirname "$0")/.."
.venv/bin/python run.py --system fixed --runs 3
for model in "${@:-claude-haiku-5-5}"; do
  .venv/bin/python run.py --system single_call --model "$model" --runs 3 --workers 4 --yes
  .venv/bin/python run.py --system agent       --model "$model" --runs 3 --workers 4 --yes
done
echo; tail -n 6 runs/ledger.csv
