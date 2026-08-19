# AION AXON core.
#
# Holds the governance stack and the credentials. Generated code never
# runs in this image -- that is what aion-sandbox is for.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts

RUN useradd --create-home --uid 1001 axon
USER axon

EXPOSE 8080

CMD exec uvicorn app.api:app --host 0.0.0.0 --port ${PORT:-8080}
