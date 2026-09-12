from flask import Blueprint, jsonify, request

from app.db import get_cursor

bp = Blueprint("lakes", __name__, url_prefix="/api/lakes")


def _lake_to_geojson_feature(row):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [row["lon"], row["lat"]]},
        "properties": {
            "id": row["id"],
            "icimod_id": row["icimod_id"],
            "name": row["name"],
            "district": row["district"],
            "basin": row["basin"],
            "elevation_m": row["elevation_m"],
            "area_km2": float(row["area_km2"]) if row["area_km2"] is not None else None,
            "dam_type": row["dam_type"],
            "slope_deg": float(row["slope_deg"]) if row["slope_deg"] is not None else None,
            "source": row["source"],
            "risk_score": float(row["score"]) if row.get("score") is not None else None,
            "risk_level": row.get("level"),
            "risk_computed_at": row["computed_at"].isoformat() if row.get("computed_at") else None,
        },
    }


@bp.get("")
def list_lakes():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.id, l.icimod_id, l.name, l.district, l.basin, l.elevation_m,
                   l.area_km2, l.dam_type, l.slope_deg, l.source,
                   ST_Y(l.geom) AS lat, ST_X(l.geom) AS lon,
                   r.score, r.level, r.computed_at
            FROM lakes l
            LEFT JOIN latest_risk_scores r ON r.lake_id = l.id
            ORDER BY l.name
            """
        )
        rows = cur.fetchall()
    return jsonify(
        {"type": "FeatureCollection", "features": [_lake_to_geojson_feature(r) for r in rows]}
    )


@bp.get("/search")
def search_lakes():
    try:
        lat = float(request.args.get("lat"))
        lon = float(request.args.get("lon"))
    except (TypeError, ValueError):
        return jsonify({"error": "lat and lon query params are required numbers"}), 400
    radius_km = float(request.args.get("radius_km", 50))

    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.id, l.icimod_id, l.name, l.district, l.basin, l.elevation_m,
                   l.area_km2, l.dam_type, l.slope_deg, l.source,
                   ST_Y(l.geom) AS lat, ST_X(l.geom) AS lon,
                   r.score, r.level, r.computed_at,
                   ST_Distance(l.geom::geography, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography) / 1000.0 AS distance_km
            FROM lakes l
            LEFT JOIN latest_risk_scores r ON r.lake_id = l.id
            WHERE ST_DWithin(
                l.geom::geography,
                ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326)::geography,
                %(radius_m)s
            )
            ORDER BY distance_km ASC
            """,
            {"lat": lat, "lon": lon, "radius_m": radius_km * 1000},
        )
        rows = cur.fetchall()

    features = []
    for r in rows:
        feature = _lake_to_geojson_feature(r)
        feature["properties"]["distance_km"] = round(float(r["distance_km"]), 2)
        features.append(feature)

    return jsonify({"type": "FeatureCollection", "features": features})


@bp.get("/<int:lake_id>")
def lake_detail(lake_id):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT l.id, l.icimod_id, l.name, l.district, l.basin, l.elevation_m,
                   l.area_km2, l.area_1990_km2, l.dam_type, l.slope_deg, l.source,
                   ST_Y(l.geom) AS lat, ST_X(l.geom) AS lon
            FROM lakes l WHERE l.id = %(id)s
            """,
            {"id": lake_id},
        )
        lake = cur.fetchone()
        if not lake:
            return jsonify({"error": "lake not found"}), 404

        cur.execute(
            """
            SELECT score, level, breakdown, computed_at
            FROM risk_scores WHERE lake_id = %(id)s
            ORDER BY computed_at DESC LIMIT 1
            """,
            {"id": lake_id},
        )
        risk = cur.fetchone()

        cur.execute(
            """
            SELECT score, computed_at FROM risk_scores
            WHERE lake_id = %(id)s ORDER BY computed_at ASC
            """,
            {"id": lake_id},
        )
        history = cur.fetchall()

        cur.execute(
            """
            SELECT id, reporter_name, condition, description, severity, status, created_at
            FROM user_reports
            WHERE lake_id = %(id)s AND status != 'rejected'
            ORDER BY created_at DESC LIMIT 50
            """,
            {"id": lake_id},
        )
        reports = cur.fetchall()

    lake["area_km2"] = float(lake["area_km2"]) if lake["area_km2"] is not None else None
    lake["area_1990_km2"] = float(lake["area_1990_km2"]) if lake["area_1990_km2"] is not None else None
    lake["slope_deg"] = float(lake["slope_deg"]) if lake["slope_deg"] is not None else None

    if risk:
        risk["score"] = float(risk["score"])
        risk["computed_at"] = risk["computed_at"].isoformat()

    for h in history:
        h["score"] = float(h["score"])
        h["computed_at"] = h["computed_at"].isoformat()

    for r in reports:
        r["created_at"] = r["created_at"].isoformat()

    return jsonify({"lake": lake, "risk": risk, "risk_history": history, "reports": reports})
