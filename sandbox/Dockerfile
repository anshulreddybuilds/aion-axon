# AION AXON sandbox — the trust boundary.
#
# Deliberately minimal. No Google client libraries, no service-account
# key, no application code from aion-core. If generated code escapes its
# constraints, there is nothing here worth stealing.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

# Non-root: generated code should not run as root even inside the box.
RUN useradd --create-home --uid 1001 sandbox
USER sandbox

EXPOSE 8080

CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
