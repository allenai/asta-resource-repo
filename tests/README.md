# Test Suite Documentation

This directory contains the test suite for the asta-resource-repository, including unit tests, integration tests, and PostgreSQL integration tests.

## Test Structure

- `test_rest_api.py` - REST API endpoint tests (uses filesystem storage)
- `test_server_integration.py` - MCP server integration tests (uses filesystem storage)
- `test_postgres_integration.py` - PostgreSQL backend integration tests (requires PostgreSQL)

## Running Tests

### Quick Start

Run all tests except PostgreSQL integration tests (default):
```bash
make test
```

This will run 26 tests and skip 12 PostgreSQL tests.

### Running PostgreSQL Integration Tests

1. Start PostgreSQL database:
   ```bash
   make db-start
   ```

2. Run PostgreSQL tests only:
   ```bash
   make test-postgres
   ```

3. Or run all tests including PostgreSQL:
   ```bash
   make test-all
   ```

### Running Tests with pytest directly

Run all tests (PostgreSQL tests will be skipped if database is not configured):
```bash
uv run pytest tests/
```

Run only PostgreSQL tests with database:
```bash
POSTGRES_URL=postgresql://astauser:astauser@localhost:15432/asta_resources uv run pytest tests/test_postgres_integration.py -v
```

Run with verbose output:
```bash
uv run pytest tests/ -v
```

Run specific test file:
```bash
uv run pytest tests/test_rest_api.py -v
```

Run specific test:
```bash
uv run pytest tests/test_rest_api.py::TestRestAPIUpload::test_upload_text_document -v
```

## PostgreSQL Test Configuration

PostgreSQL integration tests use a configuration file for database connection settings. The tests will:

1. Load configuration from `src/asta_resource_repository/config/test.conf`
2. Override with environment variable `POSTGRES_URL` if provided
3. Skip tests if PostgreSQL is not configured

### Environment Variables

- `POSTGRES_URL` - Full PostgreSQL connection URL (e.g., `postgresql://user:pass@host:port/database`)
- `ENV` - Config environment to use (defaults to `test` for PostgreSQL tests)
- `STORAGE_BACKEND` - Storage backend type (`local` or `postgres`)

## Test Database

The PostgreSQL tests use a separate test database:
- **Database:** `test_documents` (or `asta_resources` if using docker-compose)
- **Host:** `localhost`
- **Port:** `15432` (when using docker-compose) or `5432` (default)
- **User:** `astauser`
- **Password:** `astauser`

Tests automatically:
- Create database schema on startup
- Clean up test data after each test
- Close database connections properly

## CI/CD

For CI/CD pipelines:

1. Start PostgreSQL service
2. Set `POSTGRES_URL` environment variable
3. Run `make test-all`

Example GitHub Actions:
```yaml
services:
  postgres:
    image: postgres:15
    env:
      POSTGRES_USER: astauser
      POSTGRES_PASSWORD: astauser
      POSTGRES_DB: asta_resources
    ports:
      - 5432:5432

steps:
  - name: Run tests
    env:
      POSTGRES_URL: postgresql://astauser:astauser@localhost:5432/asta_resources
    run: make test-all
```

## Test Coverage

To run tests with coverage:
```bash
uv run pytest tests/ --cov=src/asta_resource_repository --cov-report=html
```

View coverage report:
```bash
open htmlcov/index.html
```

## Troubleshooting

### PostgreSQL tests are skipped
- Make sure PostgreSQL is running: `make db-start`
- Verify connection: `PGPASSWORD=astauser psql -h localhost -p 15432 -d asta_resources -U astauser`
- Check `POSTGRES_URL` environment variable is set

### Database connection errors
- Ensure PostgreSQL is healthy: `docker compose ps`
- Check logs: `make logs-db`
- Restart database: `make restart`

### Tests fail with "table already exists"
- Database schema is created automatically
- Tests clean up after themselves
- If needed, reset database: `make clean && make db-start`
