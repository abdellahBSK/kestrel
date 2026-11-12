# Developer shortcuts (Linux and macOS). Windows: run the commands in CONTRIBUTING.md.
.PHONY: install web demo check lint test web-check build docker clean

install:  ## Python package in editable mode, with dev tools
	pip install -e ".[dev]"

web:  ## Build the dashboard into src/kestrel/static
	cd frontend && npm ci && npm run build

demo: web  ## Run the demo
	kestrel demo

lint:
	ruff check . && ruff format --check .

test:
	pytest

web-check:
	cd frontend && npm run typecheck && npm run lint && npm run format:check && npm test

check: lint test web-check  ## Everything CI runs

build: web  ## Wheel and sdist with the dashboard inside
	python -m build

docker:
	docker build -t kestrel .

clean:
	rm -rf build dist *.egg-info .pytest_cache .ruff_cache .coverage htmlcov src/kestrel/static
