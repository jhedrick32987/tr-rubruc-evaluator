# T&R Rubric Evaluation Generator — App Runner image
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    MODEL_PROVIDER=bedrock \
    BEDROCK_MODEL_ID=amazon.nova-pro-v1:0 \
    AWS_REGION=us-east-1

WORKDIR /app

# Install dependencies first for better layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code, templates, static assets, config, examples.
COPY app/ ./app/
COPY templates/ ./templates/
COPY static/ ./static/
COPY config.json ./config.json
COPY examples/ ./examples/

# The source corpus (read-only) — required for the Design stage.
COPY corpus/ ./corpus/

# Pre-seed demo scenarios so the demo always has content (Req 8.3).
# Rubric versions/drafts are ephemeral on App Runner by design.
COPY data/demo_scenarios.json ./data/demo_scenarios.json

# App Runner routes to port 8080 by default.
ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
