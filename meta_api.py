"""
Meta Marketing API - Insights API 호출
광고 성과 관리 BI 앱용 (ad 레벨, 일별)
"""

import os
from typing import Any, Optional

import requests


def get_access_token() -> Optional[str]:
    """환경변수에서 ACCESS_TOKEN 로드 (.env는 app에서 load_dotenv()로 미리 로드)."""
    return os.getenv("ACCESS_TOKEN")


def fetch_insights(
    ad_account_id: str,
    since: str,
    until: str,
    *,
    level: str = "ad",
    use_breakdowns: bool = True,
    api_version: str = "v23.0",
    limit: int = 500,
) -> list[dict[str, Any]]:
    """
    Meta Insights API 호출, pagination 처리 후 전체 결과 반환.

    Args:
        ad_account_id: 광고계정 ID (act_ 없이 숫자만 가능)
        since: 시작일 YYYY-MM-DD
        until: 종료일 YYYY-MM-DD
        level: campaign / adset / ad (기본 ad)
        use_breakdowns: True면 age,gender breakdown 요청 (일부 계정/권한에서는 400 발생 가능)
        api_version: API 버전
        limit: 페이지당 건수

    Returns:
        insights 레코드 리스트 (date_start, campaign_name, adset_name, ad_name, impressions, clicks, spend, actions 등)
    """
    token = get_access_token()
    if not token:
        return []

    account_id = f"act_{ad_account_id}" if not str(ad_account_id).startswith("act_") else ad_account_id
    base_url = f"https://graph.facebook.com/{api_version}/{account_id}/insights"

    fields = (
        "campaign_name,adset_name,ad_name,ad_id,impressions,clicks,spend,"
        "actions,action_values,date_start"
    )
    params: dict[str, Any] = {
        "access_token": token,
        "fields": fields,
        "time_range": str({"since": since, "until": until}).replace("'", '"'),
        "time_increment": 1,
        "limit": limit,
        "level": level,
    }
    if use_breakdowns:
        params["breakdowns"] = "age,gender"

    all_data: list = []
    url: Optional[str] = base_url
    max_pages = 15  # 페이지 수 제한 (화면이 너무 오래 안 뜨는 것 방지)

    while url and max_pages > 0:
        max_pages -= 1
        if url == base_url:
            resp = requests.get(url, params=params, timeout=25)
        else:
            resp = requests.get(url, timeout=25)
        resp.raise_for_status()
        body = resp.json()

        if "data" in body and body["data"]:
            all_data.extend(body["data"])

        next_url = (body.get("paging") or {}).get("next")
        url = next_url if next_url else None

    return all_data


def fetch_ad_effective_statuses(
    ad_account_id: str,
    ad_ids: list[str],
    *,
    token: Optional[str] = None,
    api_version: str = "v23.0",
) -> dict[str, str]:
    """
    Ad effective_status 조회.
    ad_ids: 숫자 id 리스트 (act_ 아님)
    """
    if not ad_ids:
        return {}
    token = token or get_access_token()
    if not token:
        return {}

    base_url = f"https://graph.facebook.com/{api_version}"
    out: dict[str, str] = {}
    chunk_size = 50

    for i in range(0, len(ad_ids), chunk_size):
        chunk = ad_ids[i:i + chunk_size]
        for ad_id in chunk:
            params = {"access_token": token, "fields": "effective_status"}
            resp = requests.get(f"{base_url}/{ad_id}", params=params, timeout=25)
            resp.raise_for_status()
            data = resp.json()
            if "effective_status" in data:
                out[str(ad_id)] = str(data["effective_status"])

    return out
