# ComplianceAgent backend image
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# No system build deps needed: every dependency in requirements.txt ships a
# manylinux wheel (the native chromadb/hnswlib stack is optional and excluded
# from the default image). Keeps the build fast and reliable on the free tier.

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Build the processed dataset (DuckDB + reference docs) at image build time so the
# container is ready to serve immediately.
RUN python -m app.data_pipeline

# Train the GNN detector on the built graph (fast, NumPy-only) so weights match the
# deployed data.
RUN python -m gnn.train

# Precompute the responsible-AI report (golden-set + red-team + fairness) offline so
# the /api/responsible-ai endpoint serves it instantly instead of running ~40 live
# investigations per request.
RUN python -m eval.responsible_ai --precompute

EXPOSE 8000

# Render provides $PORT; default to 8000 locally.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
