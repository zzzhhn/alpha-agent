.PHONY: test test-storage test-signals test-fusion test-integration coverage refresh-fixtures m1-acceptance openapi-export openapi-check m2-acceptance

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

m1-acceptance:
	@echo "=== M1 acceptance: coverage gate ==="
	pytest tests/storage tests/signals tests/fusion tests/cli tests/integration \
		--cov=alpha_agent.signals \
		--cov=alpha_agent.fusion \
		--cov=alpha_agent.storage.postgres \
		--cov=alpha_agent.storage.queries \
		--cov=alpha_agent.storage.migrations \
		--cov=alpha_agent.cli \
		--cov-fail-under=85 \
		-m "not slow" \
		--tb=short -q
	@echo "=== M1 acceptance: CLI smoke ==="
	python -m alpha_agent build-card AAPL --use-fixtures > /tmp/m1_card.json
	@echo "=== M1 acceptance: Pydantic validation ==="
	python -c "\
import json, sys; \
from alpha_agent.core.types import RatingCard; \
data = json.load(open('/tmp/m1_card.json')); \
card = RatingCard(**data); \
assert card.ticker == 'AAPL', f'unexpected ticker: {card.ticker}'; \
assert card.tier in ('BUY','OW','HOLD','UW','SELL'), f'invalid tier: {card.tier}'; \
assert 0.0 <= card.confidence <= 1.0, f'confidence out of range: {card.confidence}'; \
print(f'  ticker={card.ticker} tier={card.tier} confidence={card.confidence:.3f}  OK'); \
"
	@echo "M1 acceptance PASS"

openapi-export:
	python -c "from alpha_agent.api.app import create_app; \
import json; \
open('openapi.snapshot.json','w').write(json.dumps(create_app().openapi(), indent=2, sort_keys=True))"
	@echo "Snapshot updated. Commit openapi.snapshot.json."
	@if [ -d frontend ]; then \
	  npx -y openapi-typescript openapi.snapshot.json -o frontend/api-types.gen.ts || \
	  echo "Frontend type gen skipped (npx unavailable)"; \
	fi

openapi-check:
	pytest tests/api/test_openapi_export.py -v

m2-acceptance:
	@echo "==> Running M2 acceptance suite"
	pytest tests/api tests/orchestrator tests/cron \
	    --cov=alpha_agent.api.routes.picks \
	    --cov=alpha_agent.api.routes.stock \
	    --cov=alpha_agent.api.routes.brief \
	    --cov=alpha_agent.api.routes.health \
	    --cov=alpha_agent.orchestrator \
	    --cov-fail-under=85 -m "not slow"
	$(MAKE) openapi-check
	@echo "M2 acceptance PASS (deploy.sh runs separately for actual Vercel deploy)"
