.PHONY: dev-up dev-down test seed

dev-up:
	cd backend && \
	if [ ! -d .venv ]; then uv venv .venv --python 3.11; fi && \
	. .venv/bin/activate && uv pip install -r requirements.txt && \
	uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

dev-down:
	@echo "Ctrl-C the dev-up process; no persistent background services to tear down."

test:
	cd backend && . .venv/bin/activate && pytest -v

seed:
	cd backend && . .venv/bin/activate && python -m app.seed

docker-up:
	docker compose up -d --build

docker-down:
	docker compose down
