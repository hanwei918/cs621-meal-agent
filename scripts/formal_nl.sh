#!/bin/zsh
# Formal runs on the frozen NL sets (nl, nl_events): 3 runs each, cheapest first. Needs ANTHROPIC_API_KEY.
set -e
cd "$(dirname "$0")/.."
for s in nl nl_events; do
  .venv/bin/python run.py --system fixed --set $s --runs 3
  for model in "${@:-claude-haiku-5-5}"; do
    .venv/bin/python run.py --system single_call --model "$model" --set $s --runs 3 --workers 4 --yes
    .venv/bin/python run.py --system agent       --model "$model" --set $s --runs 3 --workers 4 --yes
  done
done
echo; tail -n 8 runs/ledger.csv
