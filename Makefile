.PHONY: up down logs ps ingest enrich test lint eval api-dev web-dev

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f api web

ps:
	docker compose ps

ingest:
	docker compose exec api python -m civic.tools.ingest --source /data/samples/rivermont

enrich:
	docker compose exec api python -m civic.tools.enrich --limit 200

test:
	cd server && pytest -q

eval:
	cd server && python dev/eval_harness.py

lint:
	cd server && ruff check src tests

api-dev:
	cd server && uvicorn civic.main:app --reload --port 8000

web-dev:
	cd web && npm run dev
