#!/usr/bin/env bash
set -euo pipefail

# สรุป class/function ของโปรเจกต์ลงไฟล์ out/symbols.md
# ใช้ tools/summarize_symbols.py (ที่คุณมีอยู่แล้ว)
ROOT="${1:-.}"
OUTDIR="${2:-out}"
INCLUDE_METHODS="${3:-true}"     # true/false
IGNORE_REGEX='venv|\.git|__pycache__|build|dist|site-packages|\.mypy_cache|\.pytest_cache'

mkdir -p "$OUTDIR"
OUT="$OUTDIR/symbols.md"

INCLUDE_FLAG=""
if [[ "$INCLUDE_METHODS" == "true" ]]; then
  INCLUDE_FLAG="--include-methods"
fi

echo "[symbols] root=$ROOT -> $OUT"
python tools/summarize_symbols.py \
  --root "$ROOT" \
  --out "$OUT" \
  --ignore "$IGNORE_REGEX" \
  $INCLUDE_FLAG

echo "[ok] $OUT"