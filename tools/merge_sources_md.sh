#!/usr/bin/env bash
set -euo pipefail

# รวมไฟล์ตาม config (YAML/JSON/newline list) เป็น Markdown เดียว
# ใช้ tools/merge_sources.py (ที่คุณมีอยู่แล้ว)
CONFIG="${1:-tools/files.yaml}"
OUTDIR="${2:-out}"
TITLE="${3:-Merged Sources}"
ROOT="${4:-.}"
SKIP_MISSING="${5:-true}"   # true/false

mkdir -p "$OUTDIR"
OUT="$OUTDIR/merged.md"

SKIP_FLAG=""
if [[ "$SKIP_MISSING" == "true" ]]; then
  SKIP_FLAG="--skip-missing"
fi

echo "[merge] config=$CONFIG root=$ROOT -> $OUT"
python tools/merge_sources.py \
  --config "$CONFIG" \
  --out "$OUT" \
  --format md \
  --root "$ROOT" \
  --title "$TITLE" \
  $SKIP_FLAG

echo "[ok] $OUT"