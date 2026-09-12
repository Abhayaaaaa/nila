#!/usr/bin/env python3
"""
Manually trigger a full risk-score recompute for all lakes — useful for
the very first population of risk_scores (the scheduler intentionally
does not fire on boot), and for testing.

Usage: python scripts/recompute_risk.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.services.risk_pipeline import recompute_all_risk_scores  # noqa: E402

if __name__ == "__main__":
    result = recompute_all_risk_scores()
    print(json.dumps(result, indent=2))
