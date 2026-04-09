.PHONY: up down build logs shell-backend shell-worker migrate test clean

# ─── Dev lifecycle ─────────────────────────────────────────────────────────────
up:
	docker compose up -d

down:
	docker compose down

build:
	docker compose build --parallel

rebuild:
	docker compose build --no-cache --parallel

logs:
	docker compose logs -f --tail=100

logs-backend:
	docker compose logs -f backend

logs-worker:
	docker compose logs -f celery-worker

# ─── Shells ────────────────────────────────────────────────────────────────────
shell-backend:
	docker compose exec backend bash

shell-worker:
	docker compose exec celery-worker bash

shell-db:
	docker compose exec postgres psql -U clipuser -d clipdb

shell-redis:
	docker compose exec redis redis-cli

# ─── DB migrations ─────────────────────────────────────────────────────────────
migrate:
	docker compose exec backend alembic upgrade head

migrate-create:
	@read -p "Migration name: " name; \
	docker compose exec backend alembic revision --autogenerate -m "$$name"

migrate-history:
	docker compose exec backend alembic history --verbose

migrate-down:
	docker compose exec backend alembic downgrade -1

# ─── Tests ─────────────────────────────────────────────────────────────────────
test:
	docker compose exec backend pytest --tb=short -q

test-v:
	docker compose exec backend pytest -v

test-local:
	cd backend && pytest --tb=short -q

# ─── MinIO ─────────────────────────────────────────────────────────────────────
minio-init:
	docker compose run --rm minio-init

# ─── Prod profile ──────────────────────────────────────────────────────────────
prod-up:
	docker compose --profile prod up -d

prod-down:
	docker compose --profile prod down

# ─── Cleanup ───────────────────────────────────────────────────────────────────
clean:
	docker compose down -v --remove-orphans
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true

# ─── Setup (first run) ─────────────────────────────────────────────────────────
setup:
	@test -f .env || (cp .env.example .env && echo "✅ .env created — edit OPENAI_API_KEY and JWT_SECRET")
	docker compose build --parallel
	docker compose up -d
	@echo "⏳ Waiting for services to be healthy..."
	@sleep 15
	docker compose exec backend alembic upgrade head
	@echo "✅ All done! API: http://localhost:8000  Frontend: http://localhost:5173"
