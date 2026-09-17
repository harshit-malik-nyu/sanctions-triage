.PHONY: install test coverage lint audit study clean

install:
	pip install -e ".[dev]"

test:
	pytest -q

coverage:
	pytest -q --cov=triage --cov-report=term-missing

lint:
	python -m pyflakes src/triage scripts tests
	python -m mypy src/triage --ignore-missing-imports

audit:
	python -c "import sys; sys.path.insert(0,'src'); from triage import costs; print(costs.audit())"

study:
	python scripts/run_study.py

clean:
	rm -rf .cache .pytest_cache .coverage
	find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true
