FROM python:3.11-slim AS runtime
WORKDIR /app
COPY pyproject.toml ./
COPY chargeforward ./chargeforward
COPY flows ./flows
COPY sql ./sql
RUN pip install --no-cache-dir '.[api,app]'
COPY data/processed ./data/processed
EXPOSE 8000

FROM runtime AS cloud
RUN pip install --no-cache-dir '.[cloud]'
CMD ["python", "-m", "flows.chargeforward_pipeline", "--help"]

FROM runtime AS api
CMD ["uvicorn", "chargeforward.api:app", "--host", "0.0.0.0", "--port", "8000"]
