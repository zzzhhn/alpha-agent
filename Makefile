.PHONY: test test-storage test-signals test-fusion test-integration coverage refresh-fixtures

test:
	pytest tests/ -m "not slow" -v

test-storage:
	pytest tests/storage/ -v

test-signals:
	pytest tests/signals/ -v

test-fusion:
	pytest tests/fusion/ -v

test-integration:
	pytest tests/integration/ -v

coverage:
	pytest tests/ --cov=alpha_agent --cov-report=term-missing --cov-report=html -m "not slow"

refresh-fixtures:
	@echo "Run scripts/refresh_fixtures.py with TICKER and DATE"
	python scripts/refresh_fixtures.py --ticker $(TICKER) --date $(DATE)
