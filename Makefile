# Makefile for asta-resource-repo

.PHONY: code-check code-format test verify

# Check code formatting and linting
code-check:
	uv run --extra dev black --check src/ tests/
	uv run --extra dev flake8 src/ tests/

# Format code
code-format:
	uv run --extra dev black src/ tests/

# Run all tests
test:
	uv run --extra dev pytest tests/ -v

# Verify code quality and tests
verify: code-check test
