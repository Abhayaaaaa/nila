"""Orchestrates recomputing risk scores for all lakes and persisting them."""
import json
import logging
from decimal import Decimal

from app.db import get_cursor
from app.services.risk_engine import compute_risk

logger = logging.getLogger("risk_pipeline")


def _json_default(obj):
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def recompute_all_risk_scores():
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, ST_Y(geom) AS lat, ST_X(geom) AS lon, area_km2, area_1990_km2,
                   dam_type, slope_deg
            FROM lakes
            """
        )
        lakes = cur.fetchall()

    results = []
    errors = []
    for lake in lakes:
        try:
            with get_cursor() as cur:
                cur.execute(
                    """
                    SELECT condition, severity FROM user_reports
                    WHERE lake_id = %(id)s AND status = 'approved'
                    """,
                    {"id": lake["id"]},
                )
                approved_reports = cur.fetchall()

            risk = compute_risk(lake, approved_reports)

            with get_cursor(commit=True) as cur:
                cur.execute(
                    """
                    INSERT INTO risk_scores (lake_id, score, level, breakdown)
                    VALUES (%(lake_id)s, %(score)s, %(level)s, %(breakdown)s)
                    """,
                    {
                        "lake_id": lake["id"],
                        "score": risk["score"],
                        "level": risk["level"],
                        "breakdown": json.dumps(risk["breakdown"], default=_json_default),
                    },
                )
            results.append({"lake_id": lake["id"], "score": risk["score"], "level": risk["level"]})
        except Exception as exc:  # keep going even if one lake's external calls fail
            logger.exception("risk computation failed for lake %s", lake["id"])
            errors.append({"lake_id": lake["id"], "error": str(exc)})

    return {"computed": len(results), "failed": len(errors), "results": results, "errors": errors}
