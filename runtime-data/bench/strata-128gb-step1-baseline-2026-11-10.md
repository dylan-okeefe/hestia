# Strata 128GB sweep — Step 1 re-baseline (banked TAIL_SKIP=0)

Card #96 (Dylan's "card #83" sweep spec, 2026-11-10). Arm: `step1-baseline`.
Driver: runtime-data/bench/runarm82.sh (frozen line + `--set STRATA_ROUTE_TAIL_SKIP=0`).

## Memory header (session start)

- RAM: 128 GB kit @ **3600 MT/s** (Dylan-confirmed 2026-11-10; dmidecode needs
  root, waived). `free -g`: total 125, used 64, buff/cache 67, available 61.
- MCE/EDAC: rasdaemon NOT installed (Dylan waived monitoring mid bring-up —
  documented gap). `edac_mce_amd` module loaded; no mc* sysfs counters
  registered on this board; `journalctl -k --since today` clean (no mce/ecc/
  edac lines). Any greedy-ref divergence on this card cannot be attributed to
  memory with instrumentation — re-run is the fallback.
- Engine: strata 0.2.7 / engine 0.1.52, model IQ3_S 256K, port 8080.
- GPU state before arm: GPU0 free 1452 MiB (target >=1536 — note, not changed;
  reserve changes out of scope), GPU1 free 228 MiB at idle-serving.

## Arm results

(pending)

## Step 1 results (banked STRATA_ROUTE_TAIL_SKIP=0)

Battery (median of 2, bench_strata_027.py): **pp_short 520.6 t/s (3049 tok),
tg 64.47 t/s, pp_16k 1289.4 t/s (24501 tok), TTFT@32K 23.64 s (31901 tok)**.
Quality ref: runtime-data/bench/quality-ref-step1-baseline.txt (1805 chars).
vs card-#82 freeze (565/66.1/1381/22.3, tail-skip ON): decode -2.5%, pp -7% —
consistent with the 11/10 A/B (tail-skip OFF penalty ~1 t/s at 3600).

Startup facts: layer split K=27 (CUDA0 0-26, CUDA1 27-47 + head); expert cache
3887 slots CUDA0 / 3513 CUDA1 (7.05/7.08 GiB); token-graph resident 7400;
GPU0 free 1561 MiB (target MET), GPU1 free 333 MiB — engine LOW warning, says
add --vram-reserve-later-mib 1135 (NOT applied; reserves out of scope);
CPU pool 11 workers (LPs 1-11) + host on LP0; aux CPUs on LP12 off-at-start;
prompt chunk auto 8192; pcie_frac auto 0.17 (probe 6.3 GB/s host->device).

Diagnostics:
- mpstat over a 256-tok decode: physical cores 0-11 each ~12-17% usr, SMT
  12-23 idle (~99%); total CPU ~7% of 24 threads. Large headroom for the
  audio/bot coexistence plan (~0.6 threads used while decoding).
- /metrics after warmup: pcie_frac 0.17, drafts 584/890 accepted (65.6%),
  expert_slots 7400, arena 47962 MiB, ram_used ~69 GiB of 125 GiB free.
- File tier idle after warmup: KV streaming 98-99.5% VRAM hit, RAM reads
  2-80 MiB per request, no expert-arena file reads post-load (page cache
  absorbs; the 128 GB dividend confirmed).
- Decode expert-cache hit rate 98-99.5% with warmup (86.9% cold).
- Adaptive tier: "adaptive overlap: off: not on a layer split" — the engine
  self-reports ADAPT_OVERLAP cannot run here (doc agrees) -> Phase B Step 6
  is diagnostic-only, recorded.
- EXCHANGE_ROTATE: no "exchange buffer rotation enabled" line in the startup
  log (doc: "never reached READY on the RTX 3060") -> Step 3.3 diagnostic-only.
- Layer-major prefill ON globally but "off for this prompt: layers 27..48: no
  VRAM for a super-chunk (231 MiB free)" on long prompts — GPU1 headroom,
  noted; reserve changes out of scope per card.

Engine env this run: TAIL_SKIP=0 confirmed (no "TAIL_SKIP=7 is ON" line);
ROUTE_PRIOR=1.5 default live; PF_FUSED default (#136); sm_86 exact set on.

## Step 2 arms (vs step1-baseline 520.6/64.47/1289.4/23.64)

| arm | flags | pp_short | tg | pp_16k | TTFT@32K | verdict |
|---|---|---|---|---|---|---|
| step2-splitattn | STRATA_QSA_SPLIT_ATTN=1 | 522.0 | 64.64 | 1283.4 | 23.59 | FLAT (+0.3% tg, expected +2.8% not reproduced) — NOT kept |
| step2-emb-reuse | STRATA_EMB_REUSE_ACCOUNT=1 | 523.5 | 65.76 | 1288.1 | 23.64 | tg +2.0% — borderline; repro arm decides |
| step2-hc-req8 | STRATA_HC_REQ8=1 | 521.0 | 62.31 | 1285.5 | 23.88 | REVERTED: -3.3% decode (kill criterion; A4000 gain doesn't transfer) |

Quality refs: all three same-class coherent full answers (wording differs,
no truncation) — same standard as October gate. Skipped as engine-0.1.52
defaults (no arm burned): QSA_ROWS, ATTN_DAILY, B6_MMVQ_ROWS (sm_86 exact
set), DEQUANT_WIDE (sm_86 default), PROMPT_ATTN_IMMA (default since 0.2.7).

## Step 3 arms (vs step1-baseline 520.6/64.47/1289.4/23.64)

| arm | flags | pp_short | tg | pp_16k | TTFT@32K | verdict |
|---|---|---|---|---|---|---|
| step2-emb-reuse-repro | EMB_REUSE_ACCOUNT=1 | 520.7 | 65.93 | 1289.8 | 23.80 | KEPT: tg +2.3% reproduced (first arm 65.76) |
| step3-kvprefetch | KV_PREFETCH=1 | 522.3 | 62.71 | 1355.9 | 22.23 | pp_16k +5.2%, TTFT -6.0%, TTFT@64K 40.66s; decode -2.7% -> repro decides |
| step3-kvprefetch-repro | KV_PREFETCH=1 | (pending) | | | | |
| step3-cpu-share | PREFILL_CPU_SHARE=1 MAX=3072 | 555.7 | 64.60 | 1288.1 | 23.67 | KEPT: pp_short +6.7%, decode flat |
| step3-prefill-help | PREFILL_HELP=1 | 550.3 | 66.71 | 1304.7 | 23.60 | KEPT pending stack: peer GPU engaged ("layer-major off for this prompt: a peer GPU"), pp_short +5.7%, tg +3.5%, quality same-class |
| step3-exchange-rotate | EXCHANGE_ROTATE=1 | 520.5 | 65.73 | 1283.9 | 23.64 | DIAGNOSTIC: log SILENT (no rotation line) — not engaged on 3060, matches DETAILS.md "never reached READY on the RTX 3060". +2% tg was band noise. Upstream nit. |
| step3-aux-cpus | AUX_CPUS=auto | 521.0 | 63.73 | 1281.2 | 23.81 | NOT kept: decode -1.2% (noise-to-negative) |
| step3-pool8 | pool-workers=8 | 522.2 | 65.87 | 1288.7 | 23.57 | within noise vs default 11; default stands |
| step3-pool12 | pool-workers=12 | 520.7 | 63.11 | 1289.4 | 23.78 | NOT kept: -2.1% decode |
| step2-stack1 | EMB_REUSE+CPU_SHARE+PREFILL_HELP | (pending) | | | | |

KV prefetch engaged ("strata KV prefetch: ... single existing staging pool").
Decode noise band observed across 12 launches: ~62.3-66.7 t/s, so single-arm
decode deltas under ~2% are not trustworthy; stack-level Phase C battery is
the arbiter (per card Step 9).
| step3-kvprefetch-repro | KV_PREFETCH=1 | 521.8 | 64.18 | 1370.0 | 22.13 | KEPT: decode back in band (62.7 was noise); pp_16k +6.2%, TTFT -6.4% |
| step2-stack1 | EMB_REUSE+CPU_SHARE+PREFILL_HELP | 559.5 | 66.41 | 1304.3 | 23.65 | STACK WINS: pp_short +7.5%, tg +3.0%; quality ref coherent (1189 chars, complete) |

Phase A settled base for Phase B = frozen + TAIL_SKIP=0 + EMB_REUSE_ACCOUNT=1
+ PREFILL_CPU_SHARE=1/MAX=3072 + PREFILL_HELP=1 + KV_PREFETCH=1.

## Phase B arms (reference: Phase A stack 559.5/66.41/1304.3/23.65)

| arm | flags | pp_short | tg | pp_16k | TTFT@32K | verdict |
|---|---|---|---|---|---|---|
| stepb-pf10 | pcie-frac 0.10 | 557.1 | 64.30 | 1382.8 | 21.96 | none >= +3% decode -> AUTO 0.17 STANDS |
| stepb-pf20 | pcie-frac 0.20 | 560.4 | 61.98 | 1383.4 | 22.09 | rejected (lowest decode of the sweep) |
| stepb-pf30 | pcie-frac 0.30 | 559.2 | 64.50 | 1374.6 | 22.31 | rejected |
| stepb-pf40 | pcie-frac 0.40 | 558.9 | 64.57 | 1384.0 | 22.15 | rejected |
| stepb-prefill1024 | --prefill 1024 | 466.9 | 70.09 | 535.2 | 60.20 | REJECTED: tg +5.5% but pp_short -17%, pp_16k -59%, TTFT +154% |
| stepb-prefill2048 | --prefill 2048 | 538.7 | 72.45 | 774.8 | 40.67 | REJECTED: tg +9.1% but pp_16k -41%, TTFT@32K +72% — long-prompt/agent turns are hestia's pain point; boring-wins rule |

Note: pp_16k across pf arms (1374-1384) vs stack1 (1304) shows run-to-run
prefill variance with KV_PREFETCH warm; Phase C freeze battery is the arbiter.
ADAPT_OVERLAP: engine self-reports "off: not on a layer split" (diagnostic).

## Phase C — final freeze battery (final stacked config, one launch, median of 2)

**pp_short 557.8 (3048 tok) · tg 68.01 · pp_16k 1374.6 (24500 tok) ·
TTFT@32K 22.09 s (31900 tok) · TTFT@64K 40.32 s (63723 tok)**
Quality ref: quality-ref-final-freeze.txt (957 chars — ends at the 400-token
cap mid-sentence; content coherent, quality gate PASS by the October
same-class standard).

Stack vs Step-1 baseline (520.6/64.47/1289.4/23.64): pp_short +7.1%,
tg +5.5%, pp_16k +6.6%, TTFT@32K -6.6%.
Stack vs Oct #82 freeze (565/66.1/1381/22.3, tail-skip ON): pp_short -1.3%,
tg +2.9%, pp_16k -0.5%, TTFT -0.9% — prompt-path parity within noise,
decode ahead, plus tail-skip fidelity (KL 0.056->0.086 upstream) fixed.

Step 7 (calibrate) running: `strata engine calibrate --measure --profile
launch-iq3_s-256k --exclusive` -> runtime-data/bench/calibrate-2026-11-10.json

## Step 7 — strata engine calibrate (report: calibrate-2026-11-10.json, 1104 s)

Decode sweep, exclusive access. Current settings confirmed best everywhere;
NO >3% winner -> nothing applied (per card rule).

| param | candidates (tok/s) | verdict |
|---|---|---|
| expert tier default (pcie .17/workers 11/min_p .5) | 78.3/74.1 | reference 76.2 |
| adapt-every/swaps/decay | default 78.3/74.1 > 1/80/0.97 (71.9/75.0) > 1/160/0.97 (72.1/73.0) | keep default |
| pcie-frac sweep 0..1.0 | 0.17 ~73.9 avg best of sweep | keep auto 0.17 (matches Phase B) |
| spec-min-p | 0.5 vs 0.7 contradictory across rounds (78.0 vs 76.1 confirm) | keep 0.5 |
| pool-workers | 11 (75.5/71.9) best | keep 11 |
| prefill-pipe | 0 vs 1 within noise (868 vs 869 prompt tok/s) | keep 0 |

## Frozen config (card #96 close-out)

strata launch --model iq3_s --context 256k --vision cpu --tune skip \
  --access local --port 8080 --gpu 0,1 --no-tui --yes --restart \
  --set vram-reserve-mib=1800 --set vram-reserve-later-mib=700 \
  --set layer-split=27 --set kv-resident=8192 --set trim-stage-weights=1 \
  --set STRATA_SPLIT_MTP_BATCH=1 --set STRATA_ROUTE_TAIL_SKIP=0 \
  --set STRATA_EMB_REUSE_ACCOUNT=1 --set STRATA_PREFILL_CPU_SHARE=1 \
  --set STRATA_PREFILL_CPU_SHARE_MAX=3072 --set STRATA_PREFILL_HELP=1 \
  --set STRATA_KV_PREFETCH=1

Freeze numbers (median of 2): pp_short 557.8 · tg 68.0 · pp_16k 1374.6 ·
TTFT@32K 22.1s · TTFT@64K 40.3s.

Memory-health summary: RAM 128GB @3600 MT/s (Dylan-stated; dmidecode needs
root, waived) used for all arms; MCE/EDAC monitoring WAIVED by Dylan
(rasdaemon never installed; edac_mce_amd loaded, no sysfs counters, kernel
log clean all session). No UE/CE incidents observable. Quality refs: 20
captured, all same-class coherent (greedy length varies 947-1889 chars from
the stochastic decode path; final-freeze ref hits the 400-token cap
mid-sentence = cap, not degeneration).

Upstream nits for the issues card: (1) EXCHANGE_ROTATE=1 log-silent on
RTX 3060 (DETAILS.md says "never reached READY on the RTX 3060" — engine
prints no reason); (2) layer-major prefill disables itself on long prompts
"layers 27..48: no VRAM for a super-chunk (231 MiB free)" — GPU1 headroom;
(3) engine persistently warns CUDA1 333 MiB free LOW, suggests
--vram-reserve-later-mib 1135 (left at 700 per card scope).

## Step 3.7 — context-size arms (2026-11-11; base = frozen line + TAIL_SKIP=0)

Memory header: free 125 total / 60 used / 65 avail pre-arm; EDAC not exposed;
kernel log clean; RAM 3600 per Dylan. sudo unavailable (non-interactive).

| arm | pp_short | tg | pp_16k | TTFT@32K | slots | verdict |
|---|---|---|---|---|---|---|
| step37-ctx384k (--context 393216) | 514.95 | 71.67 | 1283.2 | 23.85 | 3887 (unchanged) | NEUTRAL vs matched Step-1 base (520.6/64.5/1289.4/23.6): pp -1.1%, pp16k -0.5%, TTFT +0.9% all noise; tg +11% is a high noise draw, not a context effect |

decode @256K context (384K arm, prompt 255389 tok, median 2): tg 58.8
(60.4/57.2), pp 1398 — the streamed-KV tax: everything past the 20480-cell
resident window reads from DDR4; -13.5% vs short-context decode. RAM after:
69 used / 55 avail, no pressure.

### Step 3.7 driver incident (fixed, rerun in progress)

First step37-ctx512k attempt benched the STILL-LIVE 384K server: the arm
driver's stop used the hardcoded preset "IQ3_S 256K", but context arms run
under launch names iq3_s-384k/-512k, so the stop missed; the 512K launch
refused (port held) and the driver's readiness loop saw 8080 serving (the
384K server) and benched it. Discarded: the "step37-ctx512k" battery numbers
(505.0/63.1/1304.3/23.49) are a 384K second draw; TTFT@128K (87.36s,
127743 tok) and TTFT@256K (184.98s, 255393 tok) below are VALID 384K numbers;
the needle 400'd (411K prompt > 393216 real n_ctx) which exposed the trap.
Driver fixed: stops any model, kills all supervisors, hard-fails if 8080 is
still held, prints live n_ctx per arm. Also learned: context arms run YaRN
rope scaling (--rope-scaling yarn --rope-scale 1.5 at 384K) — the model was
trained on 262144; CLI warns answers may get less reliable. The needle probe
is exactly the test of that.

| step37-ctx512k-r2 (--context 524288, n_ctx VERIFIED) | 510.5 | 64.95 | 1269.2 | 23.97 | 3887 (unchanged) | NEUTRAL vs matched base: pp -1.9%, tg +0.7%, pp16k -1.6%, TTFT +1.5% — all noise |
| TTFT@128K (512K) | | | | 88.86s (127745 tok) | | same as 384K (87.4) — prefill speed is context-size-independent |
| TTFT@256K (512K) | | | | 186.23s (255395 tok) | | ~1371 t/s sustained at 256K |
| needle @ ~400K (512K, YaRN 2.0) | RECALL=TRUE | | | prompt 410080 tok | | codeword PURPLE-FALCON-7741 correctly retrieved first try; 3.7c criteria MET (decode regression <2%: 64.95 vs 64.5 base; needle recalls) -> **512K KEPT**, q4_0 fallback not needed |

## Step 8 — quant_quality yardstick (tools/quant_quality.py from upstream @ 0.1.52 tools/)

Two runs of the fixed yardstick (experts on CPU, fp16 KV, TAIL_SKIP=0,
CPU_SHARE=0 forced; MTP dropped from config: draft head does not fit the
yardstick's expert-cache-1 VRAM picture — startup failure, noted):
- REF qq-ref-baseline.tsv (Step-1 baseline env)
- RUN qq-run-stack.tsv (+EMB_REUSE_ACCOUNT +PREFILL_HELP +KV_PREFETCH)
compare: **top-1 agreement 100.00% (4995 pos), mean KL 0.00000, p99 0.0000,
PPL 4.644 vs 4.644** — distribution-identical; far inside the DETAILS.md
noise band (SPLIT_ATTN reference 0.0016). Caveat recorded: the yardstick
scores decode windows, so prompt-path-only switches (chunk accounting, peer
helper) are exercised by the 20 greedy refs + the 400K needle instead.

## Step 9 — final freeze battery at 512K (n_ctx verified 524288, median of 2)

**pp_short 550.4 (3053 tok) · tg 71.37 · pp_16k 1355.1 (24505 tok) ·
TTFT@32K 22.71 s (31905 tok) · TTFT@64K 41.26 s (63728 tok) ·
TTFT@256K 168.70 s (255392 tok)**
Quality ref: quality-ref-final-freeze-512k.txt (1685 chars, complete,
coherent — gate PASS).
vs 256K freeze (557.8/68.0/1374.6/22.1/40.3): pp_short -1.3%, tg +5.0%
(band-noise draw), pp_16k -1.4%, TTFT@32K +2.8%, TTFT@64K +2.4% —
performance parity, double the context.

## Step 10 — frozen config at 512K (unit hestia-strata.service updated)

strata launch --model iq3_s --context 524288 --vision cpu --tune skip \
  --access local --port 8080 --gpu 0,1 --no-tui --yes --restart \
  --set vram-reserve-mib=1800 --set vram-reserve-later-mib=700 \
  --set layer-split=27 --set kv-resident=8192 --set trim-stage-weights=1 \
  --set STRATA_SPLIT_MTP_BATCH=1 --set STRATA_ROUTE_TAIL_SKIP=0 \
  --set STRATA_EMB_REUSE_ACCOUNT=1 --set STRATA_PREFILL_CPU_SHARE=1 \
  --set STRATA_PREFILL_CPU_SHARE_MAX=3072 --set STRATA_PREFILL_HELP=1 \
  --set STRATA_KV_PREFETCH=1

## Memory-health summary (whole card, 2026-11-10 + 2026-11-11)

- RAM: 128 GB @ 3600 MT/s (Dylan-stated 11-10; dmidecode sudo-gated,
  UNAVAILABLE non-interactively). 25 engine launches + 2 yardstick runs.
- MCE/EDAC: edac_mce_amd loaded, no mc* sysfs counters exposed ("EDAC not
  exposed"); rasdaemon never installed (Dylan waived 11-10); journalctl -k
  clean every session (no mce/ecc/edac lines). UE: 0 observed, CE: 0
  observed. Unavailable checks: dmidecode speed read, rasdaemon counters.
- Quality canaries: 25 greedy temp-0 refs across the card, all same-class
  coherent; quant_quality KL 0.00000 top-1 100% stack-vs-baseline; needle
  recall at 410K tokens TRUE. No memory-incident signature at any point.
