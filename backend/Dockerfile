FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . /app
RUN chmod +x /app/backend/docker-entrypoint.sh

EXPOSE 5050
CMD ["/app/backend/docker-entrypoint.sh"]
