VENV_PYTHON := $(CURDIR)/.venv/bin/python
FRONTEND_DIR := $(CURDIR)/frontend
PYTEST_WORKERS ?= 8
SERVED_APP := $(CURDIR)/src/github_orchestrator/board_api/static/app
RESTART_LOCK := $(CURDIR)/.restart-all.lock
HOLDING_LOCK := $(if $(shell command -v lockf),lockf -k,flock -o)

.PHONY: dev-install build_frontend frontend_deps install_hooks restart-all restart-all-holding-the-lock notifier_apps fmt fmt-check lint lint-python lint-frontend lint-fix lint-python-fix lint-frontend-fix test test-python test-frontend record interface-report measure-test-speed watch

dev-install:
	uv tool install --force --editable .
	@$(MAKE) --no-print-directory build_frontend

build_frontend:
	@command -v npm >/dev/null 2>&1 || { \
		echo "npm not found; the review board front end needs node" >&2; \
		exit 1; }
	@cd $(FRONTEND_DIR) && { [ node_modules/.package-lock.json -nt package-lock.json ] || npm ci --silent; } && npm run build --silent
	@rm -rf $(SERVED_APP)
	@mkdir -p $(SERVED_APP)
	@cp -R $(FRONTEND_DIR)/dist/. $(SERVED_APP)/
	@echo "front end built into $(SERVED_APP)"

frontend_deps:
	@command -v npm >/dev/null 2>&1 || { \
		echo "npm not found; the review board front end needs node" >&2; \
		exit 1; }
	@[ $(FRONTEND_DIR)/node_modules/.package-lock.json -nt $(FRONTEND_DIR)/package-lock.json ] || \
		(cd $(FRONTEND_DIR) && npm ci --silent)

MD_FILES = $(shell git ls-files '*.md' ':!:src/github_orchestrator/cli/skills/**')

install_hooks:
	@git config core.hooksPath .githooks
	@echo "git hooks installed (core.hooksPath=.githooks)"

restart-all:
	@$(HOLDING_LOCK) $(RESTART_LOCK) $(MAKE) --no-print-directory restart-all-holding-the-lock

restart-all-holding-the-lock:
	@echo "==> Syncing dependencies"
	@uv sync
	@echo "==> Rebuilding the review board front end"
	@$(MAKE) --no-print-directory build_frontend
	@echo "==> Building the notification apps"
	@$(MAKE) --no-print-directory notifier_apps
	@$(VENV_PYTHON) -m github_orchestrator.cli restart-all

notifier_apps:
	@sh src/github_orchestrator/desktop/notifier/build.sh

fmt:
	uv run mdformat $(MD_FILES)

fmt-check:
	uv run mdformat --check $(MD_FILES)

lint:
	@echo "==> Linting python"
	@$(MAKE) lint-python
	@echo "==> Linting the front end"
	@$(MAKE) lint-frontend
	@echo "==> Checking markdown formatting"
	@$(MAKE) fmt-check

lint-python:
	uv run ruff check src tests; ruff=$$?; uv run mypy; mypy=$$?; \
	uv run pytest tests/test_layering.py -q -p no:randomly; layering=$$?; \
	[ $$ruff -eq 0 ] && [ $$mypy -eq 0 ] && [ $$layering -eq 0 ]

lint-frontend:
	@$(MAKE) frontend_deps
	@cd $(FRONTEND_DIR) && npm run lint

lint-fix:
	@echo "==> Fixing python"
	@$(MAKE) lint-python-fix
	@echo "==> Fixing the front end"
	@$(MAKE) lint-frontend-fix
	@echo "==> Formatting markdown"
	@$(MAKE) fmt

lint-python-fix:
	uv run ruff check --fix src tests

lint-frontend-fix:
	@$(MAKE) frontend_deps
	@cd $(FRONTEND_DIR) && npm run lint:fix

test:
	@out=$$(mktemp -d) || exit 1; trap 'rm -rf "$$out"' EXIT; \
	echo "==> Running the python suite, with the front end suite alongside"; \
	{ $(MAKE) test-frontend > "$$out/ember" 2>&1; echo $$? > "$$out/ember-status"; } & \
	{ $(MAKE) test-python; echo $$? > "$$out/python-status"; } 2>&1 | tee "$$out/python"; \
	wait; \
	echo "==> The front end suite"; \
	cat "$$out/ember"; \
	pass=$$(sed -n 's/^# pass  *//p' "$$out/ember"); fail=$$(sed -n 's/^# fail  *//p' "$$out/ember"); \
	python=$$(grep -E '^[0-9]+ (passed|failed|errors?)' "$$out/python" | tail -n 1); \
	echo "python: $${python:-no summary} | ember: $${pass:-?} pass, $${fail:-?} fail"; \
	[ "$$(cat "$$out/python-status")" -eq 0 ] && [ "$$(cat "$$out/ember-status")" -eq 0 ]

test-python:
	uv run pytest tests/ -q --forks $(PYTEST_WORKERS) --ignore=tests/test_layering.py

test-frontend:
	@$(MAKE) frontend_deps
	@cd $(FRONTEND_DIR) && \
	if [ -e dist-tests/.built-for-tests ] && [ -z "$$(find app tests public config index.html vite.config.mjs babel.config.mjs package-lock.json -newer dist-tests/.built-for-tests -print -quit)" ]; then \
		echo "front end unchanged since its last test build"; \
	else \
		npx vite build --mode development --outDir dist-tests && touch dist-tests/.built-for-tests; \
	fi && node_modules/.bin/testem ci -f testem.cjs --port 0

record:
	uv run pytest tests/ -q --record

interface-report:
	uv run python -m tests.interface_report

measure-test-speed:
	uv run python tools/measure_make_test.py 3 5

watch:
	while true; do \
		find src tests -name '*.py' | entr -cd uv run pytest tests/ -q -n 4; \
		[ $$? -eq 2 ] || break; \
	done
