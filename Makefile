PY ?= python
PIP ?= $(PY) -m pip
PYTHONPATH := src

.PHONY: setup test demo clean

setup:
	$(PIP) install -U -r requirements-dev.txt

test:
	@export PYTHONPATH=$(PYTHONPATH); \
	export MOTION_FALLBACK=1; \
	pytest -q

demo:
	@export PYTHONPATH=$(PYTHONPATH); \
	$(PY) scripts/demo_motion.py --frames 200 --hz 12 --print-every 10

clean:
	@find . -name "__pycache__" -type d -exec rm -rf {} + || true