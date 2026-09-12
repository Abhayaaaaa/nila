"""
GLOF risk scoring.

Combines, per lake:
  - Sentinel-2 derived lake area change (live or inventory-derived fallback)
  - USGS nearby seismicity (real)
  - Open-Meteo precipitation/temperature anomaly (real)
  - Dam type (moraine/ice/bedrock, from inventory)
  - Slope steepness (from inventory)
  - Recent approved user reports (from our own DB)

into a single 0-100 score with a per-factor breakdown, so the UI can show
*why* a lake scored the way it did rather than just a number.
"""
from app.services import earthquakes, weather, sentinel

# Weights sum to 100.
WEIGHTS = {
    "area_change": 30,
    "seismicity": 20,
    "climate": 20,
    "dam_type": 15,
    "slope": 10,
    "user_reports": 5,
}

DAM_TYPE_RISK = {
    "moraine": 1.0,   # least stable, most GLOF-prone dam type
    "ice": 0.75,
    "bedrock": 0.15,  # most stable
    "unknown": 0.5,
}


def _clamp(x, lo=0.0, hi=1.0):
    return max(lo, min(hi, x))


def _score_area_change(pct_change):
    """Faster growth -> higher risk. >=15% growth over the comparison window saturates."""
    if pct_change is None:
        return 0.3
    return _clamp(pct_change / 15.0)


def _score_seismicity(quake_info):
    """More/larger nearby quakes -> higher risk. 5+ M3+ quakes in 90d saturates;
    a single M6+ event alone pushes the score high."""
    count = quake_info.get("count") or 0
    max_mag = quake_info.get("max_magnitude") or 0
    from_count = _clamp(count / 5.0)
    from_mag = _clamp((max_mag - 4.0) / 2.5) if max_mag else 0.0
    return _clamp(max(from_count, from_mag))


def _score_climate(climate_info):
    """Heavy rain anomaly and warm temp anomaly both raise risk (extreme-rainfall
    triggers, accelerated melt/ice-dam weakening)."""
    precip_anom = climate_info.get("precip_anomaly_pct") or 0.0
    temp_anom = climate_info.get("temp_anomaly_c") or 0.0
    from_precip = _clamp(precip_anom / 60.0)
    from_temp = _clamp(temp_anom / 3.0)
    return _clamp(0.6 * from_precip + 0.4 * from_temp)


def _score_dam_type(dam_type):
    return DAM_TYPE_RISK.get((dam_type or "unknown").lower(), 0.5)


def _score_slope(slope_deg):
    """Steeper surrounding terrain -> more landslide/avalanche-triggered
    displacement waves. 35 degrees saturates."""
    if slope_deg is None:
        return 0.3
    return _clamp(float(slope_deg) / 35.0)


def _score_user_reports(reports):
    """Approved reports raise risk in proportion to severity and recency;
    higher-severity conditions (rising_water, new_cracks, seepage) weigh more."""
    if not reports:
        return 0.0
    HIGH_SIGNAL = {"rising_water", "new_cracks", "seepage"}
    total = 0.0
    for r in reports:
        base = (r["severity"] or 1) / 5.0
        if r["condition"] in HIGH_SIGNAL:
            base *= 1.3
        total += base
    return _clamp(total / 3.0)  # a few strong reports saturate this factor


def _level_for(score):
    if score >= 75:
        return "very_high"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


def compute_risk(lake, approved_reports):
    """
    lake: dict with id, lat, lon, area_km2, area_1990_km2, dam_type, slope_deg
    approved_reports: list of dicts with condition, severity (status='approved')
    """
    quake_info = earthquakes.get_nearby_earthquakes(lake["lat"], lake["lon"])
    climate_info = weather.get_climate_signal(lake["lat"], lake["lon"])
    area_info = sentinel.get_area_change(lake)

    factor_scores = {
        "area_change": _score_area_change(area_info.get("area_change_pct")),
        "seismicity": _score_seismicity(quake_info),
        "climate": _score_climate(climate_info),
        "dam_type": _score_dam_type(lake.get("dam_type")),
        "slope": _score_slope(lake.get("slope_deg")),
        "user_reports": _score_user_reports(approved_reports),
    }

    weighted_total = sum(factor_scores[k] * WEIGHTS[k] for k in WEIGHTS)
    score = round(_clamp(weighted_total / 100.0) * 100, 1)

    breakdown = {
        "factors": {
            k: {
                "weight_pct": WEIGHTS[k],
                "normalized_0_1": round(factor_scores[k], 3),
                "contribution_points": round(factor_scores[k] * WEIGHTS[k], 2),
            }
            for k in WEIGHTS
        },
        "raw_inputs": {
            "area_change": area_info,
            "seismicity": quake_info,
            "climate": climate_info,
            "dam_type": lake.get("dam_type"),
            "slope_deg": lake.get("slope_deg"),
            "approved_report_count": len(approved_reports),
        },
    }

    return {
        "score": score,
        "level": _level_for(score),
        "breakdown": breakdown,
    }
