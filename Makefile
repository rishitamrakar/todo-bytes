.PHONY: install install-dev test test-cov clean uninstall

install:
	pipx install --force .

install-dev:
	python3 -m venv .venv
	. .venv/bin/activate && pip install --upgrade pip && pip install -e ".[dev,ui]"
	@echo ""
	@echo "Dev env ready. Activate it with:  source .venv/bin/activate"

test:
	. .venv/bin/activate && pytest

test-cov:
	. .venv/bin/activate && pytest --cov=todo_bytes --cov-report=term-missing

clean:
	rm -rf .venv build dist *.egg-info .pytest_cache .coverage htmlcov
	find . -type d -name __pycache__ -exec rm -rf {} +

uninstall:
	pipx uninstall todo-bytes || true
