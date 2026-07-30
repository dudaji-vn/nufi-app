PYTHON ?= python3

.PHONY: test lint fmt clean bench demo

test:
	$(PYTHON) -m pytest tests/ -q

lint:
	$(PYTHON) -m pylint enforcement/ nufi/

fmt:
	$(PYTHON) -m black . --check

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name '*.pyc' -delete 2>/dev/null || true

bench:
	$(PYTHON) scripts/bench.py --ner gazetteer

demo:
	./scripts/demo_all.sh
