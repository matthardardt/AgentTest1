FROM python:3.11-slim

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Persist SQLite database to a mounted volume
RUN mkdir -p /app/data
ENV DATABASE_URL=sqlite+aiosqlite:////app/data/dropshipping.db

EXPOSE 8000

# Runs both the storefront and the agent orchestrator in one process
CMD ["python", "orchestrator.py", "--store"]
