PYTHON ?= python
.PHONY: model bootstrap migrate test build up
model:
	cd backend && $(PYTHON) scripts/fetch_datasets.py --sources dims --offline
	cd backend && $(PYTHON) scripts/build_training_table.py
	cd backend && OMP_NUM_THREADS=1 $(PYTHON) -m app.ml.train
	cd backend && $(PYTHON) scripts/build_research_datasets.py
	cd backend && OMP_NUM_THREADS=1 $(PYTHON) -m app.ml.onset
	cd backend && OMP_NUM_THREADS=1 $(PYTHON) -m app.ml.expanded --without-catboost --promote
	cd backend && OMP_NUM_THREADS=1 $(PYTHON) -m app.ml.trajectory
bootstrap:
	$(PYTHON) backend/scripts/bootstrap.py
migrate:
	docker compose run --rm api python -m alembic upgrade head
test:
	cd backend && OMP_NUM_THREADS=1 $(PYTHON) -m pytest tests -q --cov=app.twin --cov=app.simulator --cov=app.ml --cov=app.core --cov-fail-under=80
	cd frontend && npm test
build:
	cd frontend && npm ci && npm run build
	docker compose build
up:
	docker compose up -d
