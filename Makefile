VENV_PYTHON := $(CURDIR)/.venv/bin/python
FRONTEND_DIR := $(CURDIR)/frontend
PYTEST_WORKERS ?= 8
SERVED_APP := $(CURDIR)/src/github_orchestrator/board_api/static/app
PREVIEW_PORT ?= 8791
RESTART_LOCK := $(CURDIR)/.restart-all.lock
HOLDING_LOCK := $(if $(shell command -v lockf),lockf -k,flock -o)
WARM_WORKTREE := sh $(CURDIR)/tools/warm_worktree.sh
export MAIN_CHECKOUT := $(patsubst %/.git,%,$(shell git rev-parse --path-format=absolute --git-common-dir))
export SHARED_CACHE := $(MAIN_CHECKOUT)/.shared-cache
export MYPY_CACHE_DIR := $(SHARED_CACHE)/mypy
export FRONTEND_LINT_CACHE := $(SHARED_CACHE)/frontend-lint

.PHONY: dev-install build_frontend frontend_deps install_hooks restart-all restart-all-holding-the-lock notifier_apps fmt fmt-check lint lint-python lint-frontend lint-fix lint-python-fix lint-frontend-fix test test-python test-frontend record interface-report measure-test-speed watch preview contract

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
		$(WARM_WORKTREE) clone_node_modules $(FRONTEND_DIR) || \
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

preview:
	@if [ ! -e $(SERVED_APP)/index.html ] || [ -n "$$(cd $(FRONTEND_DIR) && find app public config index.html vite.config.mjs babel.config.mjs package-lock.json -newer $(SERVED_APP)/index.html -print -quit)" ]; then \
		$(MAKE) --no-print-directory build_frontend; \
	else \
		echo "front end unchanged since its last build"; \
	fi
	@echo "preview at http://127.0.0.1:$(PREVIEW_PORT)/pr/acme/widgets/7/"
	uv run python -m github_orchestrator.preview --port $(PREVIEW_PORT) --agents-disabled $(PREVIEW_ARGS)

notifier_apps:
	@sh src/github_orchestrator/desktop/notifier/build.sh

fmt:
	@uv run mdformat $(MD_FILES)

fmt-check:
	@uv run mdformat --check $(MD_FILES) || { echo "fix: make fmt"; exit 1; }

lint:
	@out=$$(mktemp -d) || exit 1; trap 'rm -rf "$$out"' EXIT; \
	echo "==> Linting python, the front end and markdown formatting alongside each other"; \
	{ $(MAKE) --no-print-directory lint-python > "$$out/python" 2>&1; echo $$? > "$$out/python-status"; } & \
	{ $(MAKE) --no-print-directory lint-frontend > "$$out/frontend" 2>&1; echo $$? > "$$out/frontend-status"; } & \
	{ $(MAKE) --no-print-directory fmt-check > "$$out/markdown" 2>&1; echo $$? > "$$out/markdown-status"; } & \
	wait; \
	echo "==> Linting python"; cat "$$out/python"; \
	echo "==> Linting the front end"; cat "$$out/frontend"; \
	echo "==> Checking markdown formatting"; cat "$$out/markdown"; \
	verdict() { [ "$$(cat "$$out/$$1-status")" -eq 0 ] && echo ok || echo FAILED; }; \
	echo "python: $$(verdict python) | front end: $$(verdict frontend) | markdown: $$(verdict markdown)"; \
	[ "$$(verdict python)$$(verdict frontend)$$(verdict markdown)" = okokok ]

lint-python:
	@out=$$(mktemp -d) || exit 1; trap 'rm -rf "$$out"' EXIT; \
	{ uv run ruff check src tests plugins .claude/skills > "$$out/ruff" 2>&1; echo $$? > "$$out/ruff-status"; } & \
	{ uv run mypy > "$$out/mypy" 2>&1; echo $$? > "$$out/mypy-status"; } & \
	{ uv run pytest tests/test_layering.py -q -p no:randomly --tb=line -rN > "$$out/layering" 2>&1; echo $$? > "$$out/layering-status"; } & \
	wait; \
	echo "--> ruff"; cat "$$out/ruff"; \
	echo "--> mypy"; cat "$$out/mypy"; \
	echo "--> layering tests"; cat "$$out/layering"; \
	verdict() { [ "$$(cat "$$out/$$1-status")" -eq 0 ] && echo ok || echo FAILED; }; \
	echo "ruff: $$(verdict ruff) | mypy: $$(verdict mypy) | layering: $$(verdict layering)"; \
	[ "$$(verdict ruff)" = ok ] || echo "fix: make lint-python-fix, then edit what ruff still reports"; \
	[ "$$(verdict ruff)$$(verdict mypy)$$(verdict layering)" = okokok ]

lint-frontend:
	@$(MAKE) frontend_deps
	@cd $(FRONTEND_DIR) && log=$$(mktemp) && trap 'rm -f "$$log" "$$log.status"' EXIT; \
	{ npm run lint; echo $$? > "$$log.status"; } 2>&1 | tee "$$log"; \
	[ "$$(cat "$$log.status")" -eq 0 ] && exit 0; \
	grep -qE 'lint:(format|js|css|hbs) exited with code [1-9]' "$$log" && \
	echo "fix: make lint-frontend-fix fixes prettier and what eslint, stylelint and ember-template-lint can; edit the rest"; \
	exit 1

lint-fix:
	@echo "==> Fixing python"
	@$(MAKE) lint-python-fix
	@echo "==> Fixing the front end"
	@$(MAKE) lint-frontend-fix
	@echo "==> Formatting markdown"
	@$(MAKE) fmt

lint-python-fix:
	uv run ruff check --fix --exit-zero src tests plugins .claude/skills

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
	@$(WARM_WORKTREE) durations
	uv run pytest tests/ -q --forks $(PYTEST_WORKERS) --ignore=tests/test_layering.py

test-frontend:
	@$(MAKE) frontend_deps
	@cd $(FRONTEND_DIR) && \
	if [ -e dist-tests/.built-for-tests ] && [ -z "$$(find app tests public config index.html vite.config.mjs babel.config.mjs package-lock.json -newer dist-tests/.built-for-tests -print -quit)" ]; then \
		echo "front end unchanged since its last test build"; \
	else \
		$(WARM_WORKTREE) restore_test_build . || \
		{ npx vite build --mode development --outDir dist-tests && touch dist-tests/.built-for-tests && \
		$(WARM_WORKTREE) store_test_build .; }; \
	fi && node_modules/.bin/testem ci -f testem.cjs --port 0

record:
	uv run pytest tests/ -q --record

contract:
	@if uv run pytest tests/board_api/test_contract_copy.py -q -p no:randomly >/dev/null; then \
		echo "the front end's API types already match /api/openapi.json"; \
	else \
		uv run pytest tests/board_api/test_contract_copy.py -q -p no:randomly && \
		echo "rewrote frontend/app/data/api.ts and the fake board's contract copy; commit both, then run the full make lint and make test"; \
	fi

interface-report:
	uv run python -m tests.interface_report

measure-test-speed:
	uv run python tools/measure_make_test.py 3 5

watch:
	while true; do \
		find src tests -name '*.py' | entr -cd uv run pytest tests/ -q -n 4; \
		[ $$? -eq 2 ] || break; \
	done
