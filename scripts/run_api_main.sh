#!/bin/zsh
# Main LLM test runs for one API system (haiku | sonnet | gpt55), run in sequence; re-running skips cached claims.
# Order: E1 random (C0, C1, C2 on the claims with a T2, then merge), E1 benchmark (GPT-5.5: C2 only, prereg D9),
# then E3 and E4 (Haiku only), then the stability re-runs (Haiku, Sonnet).
# Each run gets --cost-cap = min(1.2 x the system's budget line, room left on the account) minus what other runs have spent.
# Usage: scripts/run_api_main.sh <system>. Per-run outputs: runs/<run_id>/.
SYS=$1
cd "$(dirname "$0")/.."
PY=.venv/bin/python
cap() { $PY scripts/main_runs.py cap $SYS $1; }
go() {  # run_id condition claims [extra args]
  local rid=$1 cond=$2 claims=$3; shift 3
  local c=$(cap $rid)
  echo "$(date '+%F %T') start $rid (cap \$$c)"
  for attempt in 1 2; do  # second pass retries claims that ended in an API error (not cached)
    $PY scripts/run_llm.py run --system $SYS --condition $cond --claims runs/main_inputs/$claims --src-root data/sources \
        --prompt ${PROMPT:-prompts/main.txt} --run-id $rid --workers 4 --cost-cap $c "$@" 2>&1 | grep -v "Fetching"
  done
  $PY scripts/main_runs.py reparse $rid | tail -1
  $PY scripts/main_runs.py log > /dev/null
  if grep -q "STOPPED at the cost cap" logs/main_runs/$SYS.log; then echo "$(date '+%F %T') COST CAP HIT: $SYS stopped"; exit 3; fi
  echo "$(date '+%F %T') end $rid"
}
for s in random benchmark; do
  if [ $SYS = gpt55 ] && [ $s = benchmark ]; then go e1_gpt55_C2_benchmark C2 benchmark_all.csv; continue; fi
  [ $s = random ] && go e1_${SYS}_C0_random C0 random_all.csv
  go e1_${SYS}_C1_$s C1 ${s}_all.csv
  go e1_${SYS}_C2t2_$s C2 ${s}_t2.csv
  $PY scripts/main_runs.py merge $SYS $s
done
if [ $SYS = haiku ]; then
  until [ -s runs/main_inputs/e3_retrieval_meta.json ]; do sleep 30; done
  for m in bm25 e5; do for k in 1 3 5; do
    go e3_haiku_${m}_k$k C2 e3_claims.csv --retrieval runs/main_inputs/e3_$m.jsonl --k $k
  done; done
  for v in 1 2 3 4 5; do PROMPT=prompts/e4_v$v.txt go e4t_haiku_C2_v${v}_random C2 random_all.csv; done
fi
if [ $SYS != gpt55 ]; then
  for r in 1 2; do go stab_${SYS}_C2_r$r C2 stab200.csv; done
fi
$PY scripts/main_runs.py log > /dev/null
echo "$(date '+%F %T') $SYS ALL DONE"
