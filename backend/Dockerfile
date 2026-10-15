FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 OMP_NUM_THREADS=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home iiris
COPY app ./app
COPY scripts ./scripts
COPY migrations ./migrations
COPY alembic.ini ./
COPY data ./data
FROM base AS model
RUN python scripts/fetch_datasets.py --sources dims --offline && python scripts/build_training_table.py && python -m app.ml.train
RUN python scripts/build_research_datasets.py && python -m app.ml.onset
FROM base AS runtime
COPY --from=model /app/artifacts/progression_model.joblib /app/artifacts/progression_model.metrics.json ./artifacts/
COPY --from=model /app/artifacts/onset_model.joblib /app/artifacts/onset_model.metrics.json ./artifacts/
COPY --from=model /app/data/research ./data/research/
COPY --from=model /app/data/training_visits.csv /app/data/training_visits.provenance.json ./data/
RUN chown -R iiris:iiris /app
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:'+os.getenv('PORT','8000')+'/readyz', timeout=4)"
CMD ["python", "scripts/start.py"]
