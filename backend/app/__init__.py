import atexit
import logging
import os

from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS

from config import Config

logging.basicConfig(level=logging.INFO)


def create_app():
    frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "frontend")
    app = Flask(__name__, static_folder=frontend_dir, static_url_path="")
    app.config.from_object(Config)
    CORS(app)

    from app.routes import lakes, reports, admin

    app.register_blueprint(lakes.bp)
    app.register_blueprint(reports.bp)
    app.register_blueprint(admin.bp)

    @app.get("/api/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/")
    def index():
        return send_from_directory(frontend_dir, "index.html")

    _start_scheduler(app)

    return app


def _start_scheduler(app):
    if os.environ.get("DISABLE_SCHEDULER") == "1":
        return
    from apscheduler.schedulers.background import BackgroundScheduler
    from app.services.risk_pipeline import recompute_all_risk_scores

    scheduler = BackgroundScheduler(daemon=True)

    def job():
        with app.app_context():
            logging.getLogger("scheduler").info("running scheduled risk recompute")
            recompute_all_risk_scores()

    scheduler.add_job(
        job,
        "interval",
        hours=Config.RISK_RECOMPUTE_INTERVAL_HOURS,
        id="risk_recompute",
        next_run_time=None,  # don't fire immediately on boot; use /api/admin/recompute or scripts/recompute_risk.py for that
    )
    scheduler.start()
    atexit.register(lambda: scheduler.shutdown(wait=False))
