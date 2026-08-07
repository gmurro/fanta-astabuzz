# Shortcuts for the routine tasks. Run `make` with no target to list them.

.DEFAULT_GOAL := help
.PHONY: help install run run-local start stop status logs check test clean

# Settings live in .env (see .env.example). These are only for overriding one
# run without editing it -- deliberately empty, because a default here would
# silently win over .env.
PORT    ?=
BUTTONS ?=
DOMAIN  ?=
RUN     := .run

OPTS = $(if $(PORT),--port $(PORT)) $(if $(BUTTONS),--buttons $(BUTTONS)) $(if $(DOMAIN),--domain $(DOMAIN))

help: ## Show this help
	@grep -hE '^[a-z][a-z-]*:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-11s\033[0m %s\n", $$1, $$2}'

install: ## Install dependencies and check that cloudflared is present
	uv sync
	@command -v cloudflared >/dev/null \
		|| { echo "cloudflared is missing — run: brew install cloudflared"; exit 1; }
	@echo "Ready. Run 'make run' to start."

run: ## Foreground: LAN + public link, live press log (Ctrl-C stops both)
	uv run astabuzz $(OPTS)

run-local: ## Foreground, LAN only, no public link
	uv run astabuzz $(OPTS) --no-tunnel

# The process writes its own PID: `uv run` interposes a process, so the shell's
# $! would be the wrong one. --pgroup makes its PID double as the group ID.
# One shell for the whole recipe so $$! survives: the launcher's death is what
# tells us a preflight check failed, and waiting the full 30s to report a
# missing permission would be a poor way to find out.
start: ## Start in the background, then print the URL and PIN
	@mkdir -p $(RUN); \
	rm -f $(RUN)/url.txt; \
	nohup uv run astabuzz $(OPTS) --pgroup >$(RUN)/server.log 2>&1 & \
	LAUNCHER=$$!; \
	for i in $$(seq 1 60); do \
		[ -s $(RUN)/url.txt ] && break; \
		kill -0 $$LAUNCHER 2>/dev/null || break; \
		sleep 0.5; \
	done; \
	if [ -s $(RUN)/url.txt ]; then \
		echo "URL  $$(cat $(RUN)/url.txt)"; \
		echo "PIN  $$(cat $(RUN)/pin.txt)"; \
	else \
		echo "Failed to start. Output:"; tail -20 $(RUN)/server.log; exit 1; \
	fi

# Signals the whole process group so the tunnel dies with the server, then
# sweeps up any cloudflared still bound to our port. Idempotent on purpose: a
# cleanup target that fails when there is nothing to clean breaks the moment it
# is chained into anything.
stop: ## Stop the background server and its tunnel
	@if [ -f $(RUN)/server.pid ]; then \
		PID=$$(cat $(RUN)/server.pid); \
		kill -TERM -$$PID 2>/dev/null || kill -TERM $$PID 2>/dev/null || true; \
		for i in $$(seq 1 20); do kill -0 $$PID 2>/dev/null || break; sleep 0.25; done; \
		kill -KILL -$$PID 2>/dev/null || true; \
	fi
	@pkill -f "cloudflared tunnel --no-autoupdate --url http://127.0.0.1:$$(cat $(RUN)/port.txt 2>/dev/null)" 2>/dev/null || true
	@rm -f $(RUN)/server.pid $(RUN)/url.txt $(RUN)/pin.txt $(RUN)/port.txt
	@echo "Stopped."

status: ## Show whether it is running, with the URL and PIN
	@if [ -f $(RUN)/server.pid ] && kill -0 $$(cat $(RUN)/server.pid) 2>/dev/null; then \
		echo "Running (pid $$(cat $(RUN)/server.pid))"; \
		echo "URL  $$(cat $(RUN)/url.txt 2>/dev/null)"; \
		echo "PIN  $$(cat $(RUN)/pin.txt 2>/dev/null)"; \
	else \
		echo "Not running."; \
	fi

logs: ## Follow the background server log
	@tail -f $(RUN)/server.log

check: ## Lint and format, fixing what can be fixed
	uv run python -m ruff check src/ tests/ --fix
	uv run python -m ruff format src/ tests/

test: ## Run the test suite
	uv run python -m pytest tests/ -q

clean: ## Remove caches and runtime state
	rm -rf .pytest_cache .ruff_cache $(RUN)
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
