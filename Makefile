.PHONY: test test-storage test-signals test-fusion test-integration coverage refresh-fixtures m1-acceptance openapi-export openapi-check m2-acceptance m3-acceptance m4a-acceptance

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

m3-acceptance:
	@echo "==> Running M3 acceptance suite"
	cd frontend && pnpm install --frozen-lockfile
	cd frontend && pnpm tsc --noEmit
	cd frontend && pnpm next lint
	cd frontend && pnpm next build
	@echo "M3 acceptance PASS (frontend builds cleanly)"

m4a-acceptance:
	@echo "==> Running M4a acceptance suite"
	# Backend: signal fetcher + ohlcv endpoint tests
	pytest tests/signals/test_yf_helpers.py tests/signals/test_factor.py \
	       tests/signals/test_news.py tests/signals/test_earnings.py \
	       tests/api/test_stock_ohlcv.py -v
	# Frontend: deps clean, types clean, lint clean, builds
	cd frontend && npm ci
	cd frontend && npx tsc --noEmit
	cd frontend && npx next lint
	cd frontend && npx next build
	# Smoke: hit the deployed endpoints to confirm production parity
	@echo "==> Smoke: /api/stock/AAPL/ohlcv (deployed)"
	@curl -sS --max-time 30 "https://alpha.bobbyzhong.com/api/stock/AAPL/ohlcv?period=6mo" \
	  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  bars={len(d[\"bars\"])}, period={d[\"period\"]}')" \
	  || (echo 'ohlcv smoke FAILED' && exit 1)
	@echo "==> Smoke: /api/stock/AAPL has factor.raw.fundamentals"
	@curl -sS --max-time 15 "https://alpha.bobbyzhong.com/api/stock/AAPL" \
	  | python3 -c "import json,sys; d=json.load(sys.stdin); f=next((b for b in d['card']['breakdown'] if b['signal']=='factor'), None); assert f and isinstance(f['raw'], dict) and 'fundamentals' in f['raw'], 'factor.raw missing fundamentals'" \
	  || (echo 'factor.raw smoke FAILED' && exit 1)
	@echo "M4a acceptance PASS"

m4b-acceptance:
	@echo "==> Running M4b acceptance suite"
	# Backend: alerts + brief stream endpoint tests
	pytest tests/api/test_alerts_recent.py tests/api/test_brief_stream.py -v
	# Frontend: deps clean, types clean, lint clean, builds
	cd frontend && npm ci
	cd frontend && npx tsc --noEmit
	cd frontend && npx next lint
	cd frontend && npx next build
	# Smoke: hit the deployed alerts endpoint
	@echo "==> Smoke: /api/alerts/recent?limit=5 (deployed)"
	@curl -sS --max-time 15 "https://alpha.bobbyzhong.com/api/alerts/recent?limit=5" \
	  | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'  alerts={len(d[\"alerts\"])}')" \
	  || (echo 'alerts smoke FAILED' && exit 1)
	# Smoke: confirm /api/brief/AAPL/stream rejects missing key with 422
	@echo "==> Smoke: /api/brief/AAPL/stream rejects malformed body"
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
	  -X POST -H 'content-type: application/json' \
	  -d '{"provider":"openai"}' \
	  "https://alpha.bobbyzhong.com/api/brief/AAPL/stream"); \
	  if [ "$$code" != "422" ]; then echo "expected 422 got $$code"; exit 1; fi
	@echo "M4b acceptance PASS"

m5-acceptance:
	@echo "==> Running M5 acceptance suite"
	# Backend: auth module + user routes + brief auth + alpha translate auth
	pytest tests/auth/ tests/api/test_user_routes.py tests/api/test_brief_stream_auth.py tests/api/test_alpha_translate_auth.py -v
	# Frontend: deps clean, types clean, lint clean, builds
	cd frontend && npm ci
	cd frontend && npx tsc --noEmit
	cd frontend && npx next lint
	cd frontend && npx next build
	# Smoke: protected endpoints reject anonymous access
	@echo "==> Smoke: POST /api/brief/AAPL/stream without auth -> 401"
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
	  -X POST -H 'content-type: application/json' -d '{}' \
	  "https://alpha.bobbyzhong.com/api/brief/AAPL/stream"); \
	  if [ "$$code" != "401" ]; then echo "expected 401 got $$code"; exit 1; fi
	@echo "==> Smoke: GET /api/user/me without auth -> 401"
	@code=$$(curl -sS -o /dev/null -w "%{http_code}" --max-time 10 \
	  "https://alpha.bobbyzhong.com/api/user/me"); \
	  if [ "$$code" != "401" ]; then echo "expected 401 got $$code"; exit 1; fi
	@echo "M5 acceptance PASS"
