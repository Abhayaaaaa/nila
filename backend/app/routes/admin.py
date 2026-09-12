from flask import Blueprint, jsonify, request

from app.db import get_cursor
from app.services.risk_pipeline import recompute_all_risk_scores
from config import Config

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _check_admin_token():
    token = request.headers.get("X-Admin-Token", "")
    return token and token == Config.ADMIN_TOKEN


@bp.post("/recompute")
def recompute():
    if not _check_admin_token():
        return jsonify({"error": "unauthorized"}), 401
    result = recompute_all_risk_scores()
    return jsonify(result)


@bp.get("/reports/pending")
def pending_reports():
    if not _check_admin_token():
        return jsonify({"error": "unauthorized"}), 401
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT ur.id, ur.lake_id, l.name AS lake_name, ur.reporter_name, ur.condition,
                   ur.description, ur.severity, ur.status, ur.spam_score, ur.created_at
            FROM user_reports ur JOIN lakes l ON l.id = ur.lake_id
            WHERE ur.status IN ('pending', 'flagged')
            ORDER BY ur.created_at DESC
            """
        )
        rows = cur.fetchall()
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
        r["spam_score"] = float(r["spam_score"]) if r["spam_score"] is not None else None
    return jsonify(rows)


@bp.post("/reports/<int:report_id>/moderate")
def moderate_report(report_id):
    if not _check_admin_token():
        return jsonify({"error": "unauthorized"}), 401
    data = request.get_json(silent=True) or {}
    new_status = data.get("status")
    if new_status not in ("approved", "rejected", "flagged", "pending"):
        return jsonify({"error": "status must be approved|rejected|flagged|pending"}), 400
    with get_cursor(commit=True) as cur:
        cur.execute(
            "UPDATE user_reports SET status = %(status)s WHERE id = %(id)s RETURNING id",
            {"status": new_status, "id": report_id},
        )
        if not cur.fetchone():
            return jsonify({"error": "report not found"}), 404
    return jsonify({"id": report_id, "status": new_status})
