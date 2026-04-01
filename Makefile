.PHONY: up down build logs api-logs worker-logs seed migrate test

up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build

logs:
	docker compose logs -f

api-logs:
	docker compose logs -f api

worker-logs:
	docker compose logs -f worker beat

seed:
	docker compose exec -e PYTHONPATH=/app api python -m scripts.seed_sources

migrate:
	docker compose exec -e PYTHONPATH=/app api alembic upgrade head

migrate-create:
	docker compose exec -e PYTHONPATH=/app api alembic revision --autogenerate -m "$(msg)"

test:
	docker compose exec api pytest -v

scrape:
	docker compose exec -e PYTHONPATH=/app api python -m scripts.manual_scrape

scrape-source:
	docker compose exec -e PYTHONPATH=/app api python -m scripts.manual_scrape $(slug)
