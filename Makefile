# Makefile for asta-resource-repo

.PHONY: code-check code-format test verify set-version push-version-tag

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

# Set version in both __init__.py and pyproject.toml
# Usage: make set-version VERSION=0.2.0
set-version:
	@if [ -z "$(VERSION)" ]; then \
		echo "Error: VERSION parameter is required"; \
		echo "Usage: make set-version VERSION=0.2.0"; \
		exit 1; \
	fi
	@echo "Setting version to $(VERSION)..."
	@sed -i '' 's/__version__ = ".*"/__version__ = "$(VERSION)"/' src/asta/resources/__init__.py
	@sed -i '' 's/^version = ".*"/version = "$(VERSION)"/' pyproject.toml
	@echo "Version updated to $(VERSION) in:"
	@echo "  - src/asta/resources/__init__.py"
	@echo "  - pyproject.toml"

# Push git tag with version number (verifies versions match first)
# Usage: make push-version-tag
push-version-tag:
	@echo "Checking version consistency..."
	@INIT_VERSION=$$(grep '__version__ = ' src/asta/resources/__init__.py | sed 's/__version__ = "\(.*\)"/\1/'); \
	PYPROJECT_VERSION=$$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/'); \
	if [ "$$INIT_VERSION" != "$$PYPROJECT_VERSION" ]; then \
		echo "Error: Version mismatch!"; \
		echo "  __init__.py: $$INIT_VERSION"; \
		echo "  pyproject.toml: $$PYPROJECT_VERSION"; \
		echo "Run 'make set-version VERSION=<version>' to synchronize"; \
		exit 1; \
	fi; \
	echo "Version $$INIT_VERSION verified in both files"; \
	echo "Creating and pushing git tag: v$$INIT_VERSION"; \
	git tag v$$INIT_VERSION && \
	git push origin v$$INIT_VERSION && \
	echo "Successfully pushed tag v$$INIT_VERSION"
