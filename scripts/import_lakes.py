#!/usr/bin/env python3
"""
Import glacial lake data into the GLOF database.

Reads a CSV with columns:
  icimod_id,name,district,basin,lat,lon,elevation_m,area_km2,area_1990_km2,dam_type,slope_deg

Usage:
  python scripts/import_lakes.py data/sample_lakes.csv --source sample

To import a real ICIMOD export instead, convert it to this CSV shape first
(or extend this script to read the ICIMOD shapefile/GeoJSON directly with
geopandas) and re-run with --source icimod.
"""
import argparse
import csv
import os
import sys

import psycopg2

DB_DSN = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres:glof_dev_pw@localhost:5432/glof_db",
)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv_path")
    parser.add_argument("--source", default="sample", help="value stored in lakes.source")
    args = parser.parse_args()

    conn = psycopg2.connect(DB_DSN)
    cur = conn.cursor()

    inserted, updated = 0, 0
    with open(args.csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute(
                """
                INSERT INTO lakes
                    (icimod_id, name, district, basin, geom, elevation_m,
                     area_km2, area_1990_km2, dam_type, slope_deg, source)
                VALUES
                    (%(icimod_id)s, %(name)s, %(district)s, %(basin)s,
                     ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326),
                     %(elevation_m)s, %(area_km2)s, %(area_1990_km2)s,
                     %(dam_type)s, %(slope_deg)s, %(source)s)
                ON CONFLICT (icimod_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    district = EXCLUDED.district,
                    basin = EXCLUDED.basin,
                    geom = EXCLUDED.geom,
                    elevation_m = EXCLUDED.elevation_m,
                    area_km2 = EXCLUDED.area_km2,
                    area_1990_km2 = EXCLUDED.area_1990_km2,
                    dam_type = EXCLUDED.dam_type,
                    slope_deg = EXCLUDED.slope_deg,
                    source = EXCLUDED.source
                RETURNING (xmax = 0) AS was_insert
                """,
                {**row, "source": args.source},
            )
            was_insert = cur.fetchone()[0]
            if was_insert:
                inserted += 1
            else:
                updated += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Imported {inserted + updated} lakes ({inserted} new, {updated} updated) "
          f"from {args.csv_path} [source={args.source}]")


if __name__ == "__main__":
    main()
