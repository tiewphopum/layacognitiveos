python tools/summarize_symbols.py --root . --out tools/SYMBOLS_SOURCE.md

python tools/merge_sources.py --config tools/files.yaml --out tools/MERGE_SOURCE.md --format md

python tools/merge_sources.py --config tools/files.yaml --out merged.md --format md

tools/gen_files_yaml.sh . tools/files.yaml py

PYTHONPATH=src python scripts/demo_motion.py --frames 200 --hz 12 --print-every 5
