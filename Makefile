# Shortcuts for the common tasks. `make help` lists them.

.DEFAULT_GOAL := help
.PHONY: help install install-dev build doctor test eval lint format check visuals deck icons up down serve console export clean

PYTHON ?= python

# The compose file lives in deploy/ to keep the repository root short. Its build
# context is the root, so this runs correctly from the root.
COMPOSE ?= docker compose -f deploy/docker-compose.yml

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install runtime dependencies and the package
	$(PYTHON) -m pip install -r requirements.txt
	$(PYTHON) -m pip install -e .

install-dev: ## Install development dependencies
	$(PYTHON) -m pip install -r requirements-dev.txt
	$(PYTHON) -m pip install -e .

build: ## Build the DuckDB warehouse from the workbook
	cardiac-agent build

doctor: ## Check the installation
	cardiac-agent doctor

test: ## Run the test suite
	$(PYTHON) -m pytest

eval: ## Run the golden question set in deterministic mode
	CARDIAC_LLM_PROVIDER=none $(PYTHON) evaluation/run_eval.py

lint: ## Check style, formatting and types
	$(PYTHON) -m ruff check src tests evaluation scripts
	$(PYTHON) -m ruff format --check src tests evaluation scripts
	$(PYTHON) -m mypy src/cardiac_agent --ignore-missing-imports

format: ## Apply formatting fixes
	$(PYTHON) -m ruff check --fix src tests evaluation scripts
	$(PYTHON) -m ruff format src tests evaluation scripts

check: ## Check slide geometry and prose style
	$(PYTHON) scripts/check_deck.py
	$(PYTHON) scripts/check_prose.py

visuals: ## Regenerate the charts into docs/assets
	$(PYTHON) scripts/build_visuals.py

deck: ## Rebuild both presentation decks
	$(PYTHON) scripts/build_deck.py

icons: ## Regenerate the site icons and the web manifest
	$(PYTHON) scripts/build_favicon.py

up: ## Start the API and console in Docker
	$(COMPOSE) up --build

down: ## Stop the Docker services
	$(COMPOSE) down

serve: ## Run the API on port 8000
	cardiac-agent serve

console: ## Run the Streamlit console on port 8501
	streamlit run src/cardiac_agent/ui/streamlit_app.py

export: ## Write the scorecard and metadata to exports/
	cardiac-agent export

clean: ## Remove derived artefacts, leaving the source workbook alone
	rm -rf data/processed/* data/vectorstore/* exports/*
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
