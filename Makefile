.PHONY: help install-ts install-py test-ts test-py test-ts-unit test-ts-integration test-ts-interop test-py-unit test-interop test-all lint-ts lint-py format-py build-ts build-py publish-ts publish-py clean venv-py

help:
	@echo "Available commands:"
	@echo "  make install-ts         - Install TypeScript dependencies"
	@echo "  make install-py         - Install Python dependencies"
	@echo "  make test-ts            - Run TypeScript unit tests (fast, no Docker)"
	@echo "  make test-py            - Run Python unit tests (fast, no Docker)"
	@echo "  make test-ts-unit       - Run TypeScript unit tests"
	@echo "  make test-ts-integration- Run TypeScript integration tests (requires Docker)"
	@echo "  make test-ts-interop    - Run TypeScript interop tests (requires Docker)"
	@echo "  make test-py-unit       - Run Python unit tests"
	@echo "  make test-interop       - Run full interoperability test suite (requires Docker)"
	@echo "  make test-all           - Run all tests sequentially (unit + interop)"
	@echo "  make lint-ts            - Lint TypeScript code"
	@echo "  make lint-py            - Lint Python code"
	@echo "  make format-py          - Format Python code"
	@echo "  make build-ts           - Build TypeScript package"
	@echo "  make build-py           - Build Python package"
	@echo "  make publish-ts         - Publish TypeScript to npm"
	@echo "  make publish-py         - Publish Python to PyPI"
	@echo "  make clean              - Clean build artifacts"
	@echo "  make venv-py            - Show Python virtual environment location"

# TypeScript commands
install-ts:
	cd Typescript && npm install

test-ts-unit:
	cd Typescript && npm run test:unit

test-ts-integration:
	@echo "Starting Docker services..."
	docker-compose -f redis-compose.yml up -d
	@sleep 10
	@echo "Running TypeScript integration tests..."
	cd Typescript && npm run test:integration || true
	@echo "Stopping Docker services..."
	docker-compose -f redis-compose.yml down --volumes

test-ts-interop:
	@echo "Starting Docker services..."
	docker-compose -f redis-compose.yml up -d
	@sleep 10
	@echo "Running TypeScript interop tests..."
	cd Typescript && npm run test:interop || true
	@echo "Stopping Docker services..."
	docker-compose -f redis-compose.yml down --volumes

test-ts: test-ts-unit

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

test-py-unit:
	cd Python && uv run pytest -m unit

test-py: test-py-unit

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
	@echo "========================================="
	@echo "Starting Interoperability Test Suite"
	@echo "========================================="
	@echo ""
	@echo "Starting Docker services (MySQL + Redis)..."
	docker-compose -f redis-compose.yml up -d
	@echo "Waiting for services to be ready..."
	@sleep 10
	@echo ""
	@echo "Running TypeScript interoperability tests..."
	@echo "-----------------------------------------"
	cd Typescript && npm run test:interop || true
	@echo ""
	@echo "Running Python interoperability tests..."
	@echo "---------------------------------------"
	cd Python && uv run pytest -m interop -v -s || true
	@echo ""
	@echo "Stopping Docker services..."
	docker-compose -f redis-compose.yml down --volumes
	@echo ""
	@echo "========================================="
	@echo "Interoperability Test Suite Complete"
	@echo "========================================="

test-all:
	@echo "========================================="
	@echo "Running Complete Test Suite"
	@echo "========================================="
	@echo ""
	@echo "1. TypeScript Unit Tests..."
	@echo "---------------------------"
	$(MAKE) test-ts-unit
	@echo ""
	@echo "2. Python Unit Tests..."
	@echo "----------------------"
	$(MAKE) test-py-unit
	@echo ""
	@echo "3. Interoperability Tests..."
	@echo "---------------------------"
	$(MAKE) test-interop
	@echo ""
	@echo "========================================="
	@echo "All Tests Complete"
	@echo "========================================="
	docker-compose -f redis-compose.yml down --volumes

test: test-ts test-py

clean:
	rm -rf Typescript/dist Typescript/coverage
	rm -rf Python/dist Python/.pytest_cache Python/src/*.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
