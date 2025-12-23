.PHONY: help install-ts install-py test-ts test-py lint-ts lint-py format-py build-ts build-py publish-ts publish-py clean test-interop venv-py

help:
	@echo "Available commands:"
	@echo "  make install-ts    - Install TypeScript dependencies"
	@echo "  make install-py    - Install Python dependencies"
	@echo "  make test-ts       - Run TypeScript tests"
	@echo "  make test-py       - Run Python tests"
	@echo "  make lint-ts       - Lint TypeScript code"
	@echo "  make lint-py       - Lint Python code"
	@echo "  make format-py     - Format Python code"
	@echo "  make build-ts      - Build TypeScript package"
	@echo "  make build-py      - Build Python package"
	@echo "  make publish-ts    - Publish TypeScript to npm"
	@echo "  make publish-py    - Publish Python to PyPI"
	@echo "  make clean         - Clean build artifacts"
	@echo "  make test-interop  - Run interoperability tests"
	@echo "  make venv-py       - Show Python virtual environment location"

# TypeScript commands
install-ts:
	cd Typescript && npm install

test-ts:
	cd Typescript && npm test

lint-ts:
	cd Typescript && npm run lint

build-ts:
	cd Typescript && npm run build

publish-ts:
	cd Typescript && npm publish

# Python commands
install-py:
	@echo "Setting up Python environment with uv..."
	cd Python && uv sync
	@echo "Virtual environment created at Python/.venv/"

test-py:
	cd Python && uv run pytest

lint-py:
	cd Python && uv run ruff check src tests
	cd Python && uv run ruff format --check src tests

format-py:
	cd Python && uv run ruff format src tests

build-py:
	cd Python && uv build

publish-py:
	cd Python && uv publish

# Utility commands
venv-py:
	@echo "Virtual environment location:"
	@cd Python && uv run python -c "import sys; print(sys.prefix)"

# Combined commands
install: install-ts install-py

test-interop:
	@echo "Starting Redis for interop tests..."
	docker-compose -f redis-compose.yml up -d
	@echo "Running TypeScript interop tests..."
	cd Typescript && npm run test -- tests/interop.test.ts || true
	@echo "Running Python interop tests..."
	cd Python && uv run pytest tests/test_interop.py -v
	@echo "Stopping Redis..."
	docker-compose -f redis-compose.yml down --volumes

test: test-ts test-py

clean:
	rm -rf Typescript/dist Typescript/coverage
	rm -rf Python/dist Python/.pytest_cache Python/src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
