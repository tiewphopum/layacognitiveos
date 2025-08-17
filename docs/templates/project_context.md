# Project Context (สำหรับ AI)

## 1. Overview
- Goal: …
- Non-goals: …
- Current WIP: …

## 2. Runbook
- Setup: `pyenv …`, `pip install -r requirements.txt`
- Dev run: `make dev` / `python -m app`
- Tests: `pytest -q`
- Lint/Fmt: `ruff check`, `black .`

## 3. Rhythm & Buffer Policy
- tick_ms: 2
- quota_per_tick (per partition): 280
- buffer policies:
  - preprocess: defer
  - enrich: skip/drop
  - detect: priority
- watermarks: hi=0.7, lo=0.3
- idempotency_key: `${tick_id}:${key}:${hash(payload)}`

## 4. Contracts/Schemas
- DTOs: link to `/contracts/*.yaml`
- Ports: `/src/l0_foundation/ports.py`

## 5. Code Map
- See `symbols.md` (generated) + `tree.txt`

## 6. Known issues / TODO
- …