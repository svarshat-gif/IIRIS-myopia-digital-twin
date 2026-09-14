# Convenience targets. Run `make help` for the list.
.PHONY: help setup data train seed api ui test build clean demo

PY := backend/.venv/bin/python
PIP := backend/.venv/bin/pip

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup:  ## Create the venv, install backend + frontend dependencies
	python3 -m venv backend/.venv
	$(PIP) install --upgrade pip
	$(PIP) install -r backend/requirements.txt
	cd frontend && npm install

data:  ## Generate the synthetic cohort
	cd backend && .venv/bin/python scripts/generate_synthetic.py

train:  ## Train the models and write the bundle + metrics
	cd backend && .venv/bin/python -m app.ml.train

seed:  ## Load the cohort, build twin histories, create demo accounts
	cd backend && .venv/bin/python scripts/seed_demo.py --patients 25 --reset
	cd backend && .venv/bin/python scripts/seed_users.py --reset

api:  ## Run the API on :8000
	cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000

ui:  ## Run the UI on :5173
	cd frontend && npm run dev

test:  ## Run the backend test suite
	cd backend && .venv/bin/python -m pytest tests -q

build:  ## Production build of the frontend
	cd frontend && npm run build

demo: data train seed  ## One command: data -> model -> database -> demo accounts
	@echo ""
	@echo "Ready. Start the two servers in separate terminals:"
	@echo "  make api"
	@echo "  make ui     ->  http://localhost:5173"
	@echo ""
	@echo "Sign in with  demo@iiris.health  /  irisdemo2026"

clean:  ## Remove generated artifacts (keeps source)
	rm -f backend/artifacts/*.db backend/artifacts/*.joblib backend/artifacts/*.json
	rm -rf frontend/dist
