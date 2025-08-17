#!/usr/bin/env bash
set -euo pipefail

# แสดงโครงสร้างโปรเจกต์ (ลึก 3 ชั้น) โดยไม่เอา __pycache__ หรือไฟล์ .pyc/.pyo
ROOT="${1:-$(pwd)}"
OUTDIR="${2:-out}"
DEPTH="${3:-3}"

mkdir -p "$OUTDIR"
OUT="$OUTDIR/tree.txt"

echo "[tree] root=$ROOT depth=$DEPTH -> $OUT"

# -I ใช้ ignore pattern (regex-like, | = OR)
tree -L "$DEPTH" -I "__pycache__|*.pyc|*.pyo" "$ROOT" > "$OUT"

echo "[ok] $OUT"