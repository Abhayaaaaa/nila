import os

from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, "..", ".env"))


class Config:
    DATABASE_URL = os.environ.get(
        "DATABASE_URL", "postgresql://postgres:glof_dev_pw@localhost:5432/glof_db"
    )
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "dev-admin-token-change-me")

    # Copernicus Data Space Ecosystem (Sentinel Hub) OAuth credentials.
    # Free to create at https://dataspace.copernicus.eu/ -> Sentinel Hub ->
    # User Settings -> OAuth clients. When unset, the Sentinel-2 service
    # falls back to a clearly-labeled mock derived from stored lake area
    # history instead of live imagery.
    CDSE_CLIENT_ID = os.environ.get("CDSE_CLIENT_ID", "")
    CDSE_CLIENT_SECRET = os.environ.get("CDSE_CLIENT_SECRET", "")
    CDSE_TOKEN_URL = (
        "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/"
        "protocol/openid-connect/token"
    )
    CDSE_PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

    USGS_QUAKE_URL = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
    OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
    NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

    # Risk recompute cadence (hours). Product spec asks for daily/weekly;
    # default to daily.
    RISK_RECOMPUTE_INTERVAL_HOURS = int(os.environ.get("RISK_RECOMPUTE_INTERVAL_HOURS", "24"))
