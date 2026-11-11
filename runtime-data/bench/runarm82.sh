#!/bin/bash
# runarm82.sh LABEL [extra launch args...] — card-#82 arm driver.
# Same skeleton as card-#68 /tmp/runarm.sh (clean stop, stale-supervisor kill,
# frozen launch line) but benches with scripts/bench_strata_027.py (adds
# TTFT@32K) and captures a per-arm greedy reference.
set -u
export PATH="$HOME/.local/bin:$PATH"
LABEL="$1"; shift
LOG=~/.local/state/strata/launch/iq3_s-256k.engine.log
cd /home/dylan/Hestia-runtime

strata launch --stop --preset "IQ3_S 256K" >/dev/null 2>&1
# context arms run under different launch names (iq3_s-384k, -512k): stop any
# serving model, not just the 256K preset (card-#96 lesson: the 512K arm
# benched the still-live 384K server because the preset stop missed it).
strata launch --stop >/dev/null 2>&1 || true
sleep 6
# card-#67 lesson: kill stale owner supervisors if they survived --stop
STALE=$(pgrep -f "strata_control.runtime" || true)
[ -n "$STALE" ] && kill $STALE 2>/dev/null && sleep 3
# hard fail if 8080 is still held — benching the wrong server is worse than
# no bench (this exact trap produced a bogus arm on 2026-11-11).
for i in $(seq 1 12); do curl -sf -m 2 http://127.0.0.1:8080/v1/models >/dev/null 2>&1 || break; sleep 5; done
curl -sf -m 2 http://127.0.0.1:8080/v1/models >/dev/null 2>&1 && { echo "ARM $LABEL: port 8080 still held; refusing to bench a stale server" >&2; exit 1; }

strata launch --model iq3_s --context 256k --vision cpu --tune skip \
  --access local --port 8080 --gpu 0,1 --no-tui \
  --set vram-reserve-mib=1800 --set vram-reserve-later-mib=700 \
  --set layer-split=27 --set kv-resident=8192 \
  --set trim-stage-weights=1 --set STRATA_SPLIT_MTP_BATCH=1 \
  --set STRATA_ROUTE_TAIL_SKIP=0 \
  "$@" > /tmp/strata-arm-$LABEL.log 2>&1

for i in $(seq 1 30); do
  curl -sf -m 3 http://127.0.0.1:8080/v1/models >/dev/null 2>&1 && break
  if grep -q "could not start\|did not become ready\|server_exited" /tmp/strata-arm-$LABEL.log 2>/dev/null; then
    echo "ARM $LABEL: LAUNCH FAILED"; tail -5 /tmp/strata-arm-$LABEL.log; exit 1
  fi
  sleep 10
done
curl -sf -m 3 http://127.0.0.1:8080/v1/models >/dev/null 2>&1 || { echo "ARM $LABEL: TIMEOUT"; exit 1; }
echo "ARM $LABEL: serving, n_ctx=$(curl -sf -m 3 http://127.0.0.1:8080/v1/models | grep -oE '"n_ctx": [0-9]+' | grep -oE '[0-9]+')"
echo "--- startup facts ($LABEL):"
grep -E "layer split:|expert cache [0-9]+ slots|VRAM free with everything|layer-major|route|ROUTE|TAIL|EXCHANGE|kv-resident|engine.*0\.1\." "$LOG" | tail -12
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader
.venv/bin/python scripts/bench_strata_027.py arm "$LABEL"
.venv/bin/python scripts/bench_strata_027.py greedy "runtime-data/bench/quality-ref-$LABEL.txt"
