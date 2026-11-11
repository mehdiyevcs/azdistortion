#!/bin/zsh
# E5 (edit set) runs for one system (haiku | sonnet | gpt55 | qwen), run in sequence; re-running skips cached claims.
# Same settings as E1 (scripts/run_api_main.sh, scripts/run_qwen_main.sh): prompts/main.txt, data/sources, 4 workers and
# a cost cap for the API systems. C0 and C1 run on all 300 edits (runs/main_inputs/e5_edits.csv), C2 on the edits with a T2
# (e5_edits_t2.csv); the merge step then fills the other C2 rows from C1.
# Usage: scripts/run_e5.sh <system>
SYS=$1
cd "$(dirname "$0")/.."
PY=.venv/bin/python
L=logs/main_runs/e5_$SYS.log
go() {  # run_id condition claims
  local rid=$1 cond=$2 claims=$3
  echo "$(date '+%F %T') start $rid"
  if [ $SYS = qwen ]; then
    $PY scripts/run_llm.py run --system qwen --condition $cond --claims runs/main_inputs/$claims --src-root data/sources --prompt prompts/main.txt --run-id $rid
  else
    local c
    for attempt in 1 2; do  # second pass retries claims that ended in an API error (not cached)
      c=$($PY scripts/main_runs.py cap $SYS $rid); echo "cap \$$c"
      $PY scripts/run_llm.py run --system $SYS --condition $cond --claims runs/main_inputs/$claims --src-root data/sources \
          --prompt prompts/main.txt --run-id $rid --workers 4 --cost-cap $c 2>&1 | grep -v "Fetching"
    done
  fi
  $PY scripts/main_runs.py reparse $rid | tail -1
  $PY scripts/main_runs.py log > /dev/null
  if grep -q "STOPPED at the cost cap" $L; then echo "$(date '+%F %T') COST CAP HIT: $SYS stopped"; exit 3; fi
  echo "$(date '+%F %T') end $rid"
}
go e5_${SYS}_C0_edit C0 e5_edits.csv
go e5_${SYS}_C1_edit C1 e5_edits.csv
go e5_${SYS}_C2t2_edit C2 e5_edits_t2.csv
$PY scripts/main_runs.py merge $SYS edit
$PY scripts/main_runs.py log > /dev/null
echo "$(date '+%F %T') E5 $SYS ALL DONE"
