#!/bin/bash
# Linking chain for one link set (scripts/link_news.py): keys, cands, fetch, then verification by Claude
# (every candidate) and Codex (seeded 20%) in parallel. Usage: scripts/link_chain.sh <link_set_X.csv>
set -u; L=$1; S=$(basename "$L" .csv | sed 's/link_set_//')
cd "$(dirname "$0")/.."
for step in keys cands fetch; do python3 -P -E scripts/link_news.py $step "$L" > "logs/link_${step}_$S.log" 2>&1 || { echo "FAIL $step"; exit 1; }; done
python3 -P -E scripts/link_news.py verify_codex "$L" > "logs/link_verify_codex_$S.log" 2>&1 &
python3 -P -E scripts/link_news.py verify "$L" > "logs/link_verify_claude_$S.log" 2>&1
wait; echo "chain done $S"
