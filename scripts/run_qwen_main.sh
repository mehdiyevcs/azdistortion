#!/bin/zsh
# E1 runs for Qwen (local model), one process, run in sequence: C0/C1/C2 on the random sample, C1/C2 on the benchmark.
cd "$(dirname "$0")/.."
PY=.venv/bin/python
for spec in "C0 random all" "C1 random all" "C2 random t2" "C1 benchmark all" "C2 benchmark t2"; do
  set -- ${=spec}
  c=$1; s=$2; f=$3; rid=e1_qwen_${c}_${s}; [ $f = t2 ] && rid=e1_qwen_C2t2_${s}
  echo "$(date '+%F %T') start $rid"
  $PY scripts/run_llm.py run --system qwen --condition $c --claims runs/main_inputs/${s}_${f}.csv --src-root data/sources --prompt prompts/main.txt --run-id $rid
  echo "$(date '+%F %T') end $rid rc=$?"
  $PY scripts/main_runs.py reparse $rid | tail -1
  [ $f = t2 ] && $PY scripts/main_runs.py merge qwen $s
  $PY scripts/main_runs.py log > /dev/null
done
echo "$(date '+%F %T') QWEN ALL DONE"
