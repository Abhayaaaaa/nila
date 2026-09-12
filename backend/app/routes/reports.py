from flask import Blueprint, jsonify, request

from app.db import get_cursor
from app.services import spam

bp = Blueprint("reports", __name__, url_prefix="/api/lakes")


@bp.post("/<int:lake_id>/reports")
def submit_report(lake_id):
    data = request.get_json(silent=True) or {}

    condition = (data.get("condition") or "").strip()
    description = (data.get("description") or "").strip()
    reporter_name = (data.get("reporter_name") or "").strip()[:100] or None
    severity = data.get("severity", 1)
    honeypot_value = data.get("website", "")  # hidden field; real users never fill this in

    try:
        severity = int(severity)
    except (TypeError, ValueError):
        severity = 1
    severity = max(1, min(5, severity))

    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown").split(",")[0].strip()
    ip_hash = spam.hash_ip(ip)

    if spam.is_rate_limited(ip_hash):
        return jsonify({"error": "rate limit exceeded, try again later"}), 429

    spam_score, honeypot_tripped = spam.score_spam(description, honeypot_value, condition)

    if condition not in spam.VALID_CONDITIONS:
        return jsonify({"error": f"condition must be one of {sorted(spam.VALID_CONDITIONS)}"}), 400

    status = "flagged" if (honeypot_tripped or spam_score >= 0.6) else "pending"

    with get_cursor(commit=True) as cur:
        cur.execute("SELECT id FROM lakes WHERE id = %(id)s", {"id": lake_id})
        if not cur.fetchone():
            return jsonify({"error": "lake not found"}), 404

        cur.execute(
            """
            INSERT INTO user_reports
                (lake_id, reporter_name, condition, description, severity,
                 status, submitter_ip_hash, honeypot_tripped, spam_score)
            VALUES
                (%(lake_id)s, %(reporter_name)s, %(condition)s, %(description)s, %(severity)s,
                 %(status)s, %(ip_hash)s, %(honeypot_tripped)s, %(spam_score)s)
            RETURNING id, status
            """,
            {
                "lake_id": lake_id,
                "reporter_name": reporter_name,
                "condition": condition,
                "description": description,
                "severity": severity,
                "status": status,
                "ip_hash": ip_hash,
                "honeypot_tripped": honeypot_tripped,
                "spam_score": spam_score,
            },
        )
        result = cur.fetchone()

    spam.record_submission(ip_hash)

    return jsonify(
        {
            "id": result["id"],
            "status": result["status"],
            "message": (
                "Report submitted and pending moderation."
                if result["status"] == "pending"
                else "Report submitted but flagged for review before it affects risk scores."
            ),
        }
    ), 201


@bp.get("/<int:lake_id>/reports")
def list_reports(lake_id):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT id, reporter_name, condition, description, severity, status, created_at
            FROM user_reports
            WHERE lake_id = %(id)s AND status != 'rejected'
            ORDER BY created_at DESC LIMIT 100
            """,
            {"id": lake_id},
        )
        rows = cur.fetchall()
    for r in rows:
        r["created_at"] = r["created_at"].isoformat()
    return jsonify(rows)
