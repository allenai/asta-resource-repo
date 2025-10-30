code-check:
	uv run black --check src/ tests/
	uv run flake8 src/ tests/

code-format:
	uv run black src/ tests/

test: docker-check-db
	uv run pytest tests -v

verify: code-check docker-start test docker-stop

### DOCKER TARGETS ###

# Docker network name
DOCKER_NETWORK = asta-resource-repository-network

docker-start-db:
	docker compose up -d postgres

docker-check-db:
	@docker exec -it $(shell docker compose ps -q postgres) pg_isready -U postgres  > /dev/null 2>&1 || (echo "Postgres is not ready" && exit 1)

docker-start-api:
	@echo "API: http://localhost:8000"
	docker compose up -d --build api

docker-start:
	docker compose up -d --build

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