code-check:
	uv run --extra dev black --check src/ tests/
	uv run --extra dev flake8 src/ tests/

code-format:
	uv run --extra dev black src/ tests/

test: docker-check-db
	uv run --extra dev pytest tests -v

verify: code-check docker-start test

### DOCKER TARGETS ###

# Docker network name
DOCKER_NETWORK = asta-resource-repository-network

docker-start-db:
	docker compose up -d --wait --quiet-pull postgres

docker-check-db:
	@docker exec $(shell docker compose ps -q postgres) pg_isready -U asta_resources  > /dev/null 2>&1 || (echo "Postgres is not ready" && docker compose logs postgres && exit 1)

docker-start-api:
	@echo "API: http://localhost:8000"
	docker compose build --quiet api
	docker compose up -d api

docker-start: docker-start-db docker-start-api

docker-stop:
	docker compose down

docker-restart: docker-stop docker-start

docker-logs:
	docker compose logs -f

docker-logs-db:
	docker compose logs -f postgres

docker-logs-api:
	docker compose logs -f api

docker-status:
	docker compose ps