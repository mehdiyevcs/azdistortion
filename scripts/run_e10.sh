#!/bin/bash
# E10 two-pass judge (prereg D16): Haiku, C2, literal and implicature prompts on the random and benchmark claims.
cd "$(dirname "$0")/.."
for s in random benchmark; do for p in literal implicature; do
  .venv/bin/python scripts/run_llm.py run --system haiku --condition C2 --claims runs/main_inputs/${s}_all.csv --src-root data/sources --prompt prompts/e10_${p}.txt --effort low --workers 4 --cost-cap 8 --run-id e10_haiku_${p}_${s}
done; done
echo E10_DONE
