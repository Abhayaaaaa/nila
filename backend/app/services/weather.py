"""
Open-Meteo integration — real, free, no API key required.
Docs: https://open-meteo.com/en/docs and .../en/docs/historical-weather-api
"""
from datetime import date, timedelta

import requests

from config import Config

TIMEOUT_S = 15


def get_climate_signal(lat, lon, recent_days=30, baseline_years=5):
    """
    Compares recent precipitation/temperature against a multi-year baseline
    for the same lat/lon, as a proxy for glacier-melt acceleration and
    extreme-rainfall GLOF triggers.

    Returns:
      {
        "source": "open-meteo" | "error",
        "recent_precip_mm": float,       # total precip, last `recent_days`
        "recent_temp_mean_c": float,     # mean temp, last `recent_days`
        "baseline_precip_mm": float,     # avg precip over same calendar window, baseline_years back
        "baseline_temp_mean_c": float,
        "precip_anomaly_pct": float,     # % above/below baseline
        "temp_anomaly_c": float,         # degrees above/below baseline
      }
    """
    today = date.today()
    recent_start = today - timedelta(days=recent_days)
    recent_end = today - timedelta(days=1)  # archive API lags ~2 days; forecast API covers recent explicitly below

    try:
        # Recent window: forecast API also serves past_days for near-real-time data
        resp = requests.get(
            Config.OPEN_METEO_FORECAST_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "precipitation_sum,temperature_2m_mean",
                "past_days": min(recent_days, 92),
                "forecast_days": 1,
                "timezone": "UTC",
            },
            timeout=TIMEOUT_S,
        )
        resp.raise_for_status()
        recent = resp.json().get("daily", {})
        recent_precip_vals = [v for v in recent.get("precipitation_sum", []) if v is not None]
        recent_temp_vals = [v for v in recent.get("temperature_2m_mean", []) if v is not None]
        recent_precip = sum(recent_precip_vals) if recent_precip_vals else 0.0
        recent_temp = (
            sum(recent_temp_vals) / len(recent_temp_vals) if recent_temp_vals else None
        )

        # Baseline: same calendar window, N years ago, from the historical archive
        base_start = recent_start.replace(year=recent_start.year - baseline_years)
        base_end = recent_end.replace(year=recent_end.year - baseline_years)
        resp2 = requests.get(
            Config.OPEN_METEO_ARCHIVE_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": base_start.isoformat(),
                "end_date": base_end.isoformat(),
                "daily": "precipitation_sum,temperature_2m_mean",
                "timezone": "UTC",
            },
            timeout=TIMEOUT_S,
        )
        resp2.raise_for_status()
        baseline = resp2.json().get("daily", {})
        base_precip_vals = [v for v in baseline.get("precipitation_sum", []) if v is not None]
        base_temp_vals = [v for v in baseline.get("temperature_2m_mean", []) if v is not None]
        base_precip = sum(base_precip_vals) if base_precip_vals else 0.0
        base_temp = sum(base_temp_vals) / len(base_temp_vals) if base_temp_vals else None

        precip_anomaly_pct = (
            ((recent_precip - base_precip) / base_precip * 100) if base_precip > 0 else 0.0
        )
        temp_anomaly_c = (
            (recent_temp - base_temp) if (recent_temp is not None and base_temp is not None) else 0.0
        )

        return {
            "source": "open-meteo",
            "recent_precip_mm": round(recent_precip, 1),
            "recent_temp_mean_c": round(recent_temp, 1) if recent_temp is not None else None,
            "baseline_precip_mm": round(base_precip, 1),
            "baseline_temp_mean_c": round(base_temp, 1) if base_temp is not None else None,
            "precip_anomaly_pct": round(precip_anomaly_pct, 1),
            "temp_anomaly_c": round(temp_anomaly_c, 2),
        }
    except (requests.RequestException, ValueError, KeyError) as exc:
        return {
            "source": "error",
            "error": str(exc),
            "recent_precip_mm": None,
            "recent_temp_mean_c": None,
            "baseline_precip_mm": None,
            "baseline_temp_mean_c": None,
            "precip_anomaly_pct": 0.0,
            "temp_anomaly_c": 0.0,
        }
