# Shortcuts for the common tasks. `make help` lists them.

.DEFAULT_GOAL := help
.PHONY: help install install-dev build doctor test eval lint format serve console export clean

PYTHON ?= python

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

lint: ## Check style and types
	$(PYTHON) -m ruff check src tests evaluation
	$(PYTHON) -m mypy src/cardiac_agent --ignore-missing-imports

format: ## Apply formatting fixes
	$(PYTHON) -m ruff check --fix src tests evaluation
	$(PYTHON) -m ruff format src tests evaluation

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
