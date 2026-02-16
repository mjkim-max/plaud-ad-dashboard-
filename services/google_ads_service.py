from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
except Exception:  # pragma: no cover - optional dependency
    GoogleAdsClient = None  # type: ignore[assignment]
    GoogleAdsException = Exception  # type: ignore[assignment]


def _normalize_customer_id(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def _load_config_from_secrets() -> Dict[str, Any]:
    try:
        import streamlit as st
    except Exception:
        return {}

    try:
        if "google_ads" in st.secrets:
            return dict(st.secrets["google_ads"])
    except Exception:
        return {}

    return {}


def _load_config_from_env() -> Dict[str, Any]:
    mapping = {
        "developer_token": "GOOGLE_ADS_DEVELOPER_TOKEN",
        "client_id": "GOOGLE_ADS_CLIENT_ID",
        "client_secret": "GOOGLE_ADS_CLIENT_SECRET",
        "refresh_token": "GOOGLE_ADS_REFRESH_TOKEN",
        "login_customer_id": "GOOGLE_ADS_LOGIN_CUSTOMER_ID",
        "use_proto_plus": "GOOGLE_ADS_USE_PROTO_PLUS",
    }

    cfg: Dict[str, Any] = {}
    for key, env_name in mapping.items():
        val = os.getenv(env_name)
        if val:
            cfg[key] = val
    return cfg


def _coerce_bool(val: Any) -> Any:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in ("1", "true", "yes", "y")
    return val


def build_google_ads_client() -> Optional["GoogleAdsClient"]:
    if GoogleAdsClient is None:
        return None

    cfg = _load_config_from_secrets()
    if not cfg:
        cfg = _load_config_from_env()

    if "login_customer_id" in cfg and cfg["login_customer_id"]:
        cfg["login_customer_id"] = _normalize_customer_id(str(cfg["login_customer_id"]))

    if "use_proto_plus" in cfg:
        cfg["use_proto_plus"] = _coerce_bool(cfg["use_proto_plus"])

    required = ("developer_token", "client_id", "client_secret", "refresh_token")
    if any(not cfg.get(k) for k in required):
        return None

    try:
        return GoogleAdsClient.load_from_dict(cfg)
    except Exception:
        return None


def fetch_google_ads_insights(
    *,
    client: "GoogleAdsClient",
    customer_id: str,
    since: str,
    until: str,
) -> List[Dict[str, Any]]:
    if client is None:
        return []

    cust_id = _normalize_customer_id(customer_id or "")
    if not cust_id:
        return []

    query = f"""
    SELECT
      segments.date,
      campaign.id,
      campaign.name,
      metrics.impressions,
      metrics.clicks,
      metrics.cost_micros,
      metrics.conversions,
      metrics.conversions_value
    FROM campaign
    WHERE segments.date BETWEEN '{since}' AND '{until}'
    """

    service = client.get_service("GoogleAdsService")
    rows: List[Dict[str, Any]] = []

    try:
        stream = service.search_stream(customer_id=cust_id, query=query)
        for batch in stream:
            for row in batch.results:
                cost_micros = row.metrics.cost_micros or 0
                rows.append(
                    {
                        "Date": str(row.segments.date),
                        "Campaign": row.campaign.name or "",
                        "AdGroup": "",
                        "Creative_ID": "",
                        "Cost": cost_micros / 1_000_000,
                        "Impressions": row.metrics.impressions or 0,
                        "Clicks": row.metrics.clicks or 0,
                        "Conversions": row.metrics.conversions or 0,
                        "Conversion_Value": row.metrics.conversions_value or 0,
                        "Status": "On",
                        "Platform": "Google",
                        "Gender": "Unknown",
                        "Age": "Unknown",
                    }
                )
    except GoogleAdsException as ex:
        # Raise short, actionable message to surface in UI.
        msg = str(ex)
        if hasattr(ex, "failure") and ex.failure:
            msg = str(ex.failure)
        raise RuntimeError(f"Google Ads API error: {msg}") from ex

    return rows


def check_google_ads_customer(
    *,
    client: "GoogleAdsClient",
    customer_id: str,
) -> Dict[str, Any]:
    if client is None:
        raise RuntimeError("Google Ads client is not initialized.")

    cust_id = _normalize_customer_id(customer_id or "")
    if not cust_id:
        raise RuntimeError("customer_id is missing.")

    query = """
    SELECT
      customer.id,
      customer.descriptive_name,
      customer.currency_code,
      customer.time_zone
    FROM customer
    LIMIT 1
    """

    service = client.get_service("GoogleAdsService")
    try:
        resp = service.search(customer_id=cust_id, query=query)
        for row in resp:
            return {
                "customer_id": str(row.customer.id),
                "name": row.customer.descriptive_name or "",
                "currency": row.customer.currency_code or "",
                "time_zone": row.customer.time_zone or "",
            }
    except GoogleAdsException as ex:
        msg = str(ex)
        if hasattr(ex, "failure") and ex.failure:
            msg = str(ex.failure)
        raise RuntimeError(f"Google Ads API error: {msg}") from ex

    raise RuntimeError("Google Ads API returned no customer data.")


def list_accessible_customers(client: "GoogleAdsClient") -> List[str]:
    if client is None:
        return []
    service = client.get_service("CustomerService")
    try:
        resp = service.list_accessible_customers()
        return [str(r).split("/")[-1] for r in resp.resource_names]
    except GoogleAdsException:
        return []
