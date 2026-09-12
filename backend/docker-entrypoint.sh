#!/bin/sh
set -e

echo "Waiting for database..."
until pg_isready -h db -U postgres -d glof_db >/dev/null 2>&1; do
  sleep 1
done

echo "Applying schema (safe to re-run)..."
PGPASSWORD=glof_dev_pw psql -h db -U postgres -d glof_db -f /app/data/schema.sql

echo "Loading sample lake data (safe to re-run)..."
python /app/scripts/import_lakes.py /app/data/sample_lakes.csv --source sample

echo "Computing initial risk scores..."
python /app/scripts/recompute_risk.py || echo "Initial risk compute hit an error (check internet access) - the site will still start; retry from Admin > Recompute."

echo "Starting web server on :5050 ..."
exec gunicorn -w 2 -b 0.0.0.0:5050 run:app
