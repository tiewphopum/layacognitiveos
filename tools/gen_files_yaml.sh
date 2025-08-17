#!/usr/bin/env bash
set -euo pipefail

# gen_files_yaml.sh
# สร้างไฟล์ YAML ที่รวม path ของไฟล์ตามนามสกุลที่เลือก
# ใช้: ./gen_files_yaml.sh [root] [out.yaml] [ext1,ext2,...]

ROOT="${1:-.}"                    # โฟลเดอร์ root (default = current dir)
OUT="${2:-tools/files.yaml}"      # ไฟล์ output (default = tools/files.yaml)
EXTS="${3:-py,md,toml,txt,yml,yaml}"  # นามสกุลที่เลือก (comma-separated)

# ทำ regex สำหรับ egrep
PATTERN=$(echo "$EXTS" | sed 's/,/|/g')

mkdir -p "$(dirname "$OUT")"

echo "files:" > "$OUT"

# หาไฟล์ที่ตรงกับนามสกุล กรองโฟลเดอร์ที่ไม่อยากได้ออก
find "$ROOT" -type f \
  | egrep "\.($PATTERN)$" \
  | grep -vE "__pycache__|\.git|\.egg-info|/out/|\.venv|/env/|site-packages" \
  | sort \
  | sed 's/^/  - /' >> "$OUT"

echo "[ok] generated $OUT"