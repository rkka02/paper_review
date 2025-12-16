FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir -e .

# Cloud platforms typically inject PORT; default to 8000.
CMD ["sh", "-c", "paper-review serve --host 0.0.0.0 --port ${PORT:-8000} --no-reload"]

