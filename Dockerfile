FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml ./
COPY chargeforward ./chargeforward
RUN pip install --no-cache-dir '.[api,app]'
COPY data/processed ./data/processed
EXPOSE 8000
CMD ["uvicorn", "chargeforward.api:app", "--host", "0.0.0.0", "--port", "8000"]
