#!/usr/bin/env bash
# Run Kimi non-interactively against docs/prompts/KIMI_CURRENT.md (see Kimi CLI: --prompt, --yolo, Ralph loop).
# Default UI: --quiet (final message only). Full stream: KIMI_VERBOSE=1 ./scripts/kimi-run-current.sh
# File logging (no stdout spam): KIMI_DEBUG=1 — Kimi writes debug trace to ~/.kimi/logs/kimi.log (see Kimi CLI --debug).
#   Second terminal: tail -f ~/.kimi/logs/kimi.log
# Or pass --print / --quiet / --wire / --acp yourself (mutually exclusive in Kimi).
# Usage: ./scripts/kimi-run-current.sh [extra kimi args...]
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
rm -f .kimi-done

PROMPT="$(cat <<'EOF'
You are working in this Git repository. Open docs/prompts/KIMI_CURRENT.md and execute the entire "Current task" section, including every linked file it references (especially under docs/design/). Follow the design specs literally: code changes, tests, commits, push, handoff updates, and the .kimi-done artifact described in the active design doc. Do not skip the final orchestration steps.
EOF
)"

has_ui_mode=false
for a in "$@"; do
  case "$a" in
    --print|--quiet|--acp|--wire) has_ui_mode=true ;;
  esac
done

default_ui=()
if [[ "${KIMI_VERBOSE:-}" == 1 ]]; then
  default_ui=(--print)
elif [[ "$has_ui_mode" == false ]]; then
  default_ui=(--quiet)
fi

debug_flags=()
if [[ "${KIMI_DEBUG:-}" == 1 ]]; then
  debug_flags=(--debug)
fi

exec kimi \
  "${debug_flags[@]}" \
  --work-dir "$ROOT" \
  --yolo \
  --max-ralph-iterations -1 \
  "${default_ui[@]}" \
  --prompt "$PROMPT" \
  "$@"
