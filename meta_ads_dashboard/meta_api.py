"""
Meta Marketing API - Insights API 호출 모듈
ads_read 권한 필요
"""

import os
import requests
from typing import Any


def get_access_token() -> str:
    """환경변수에서 ACCESS_TOKEN 로드 (python-dotenv로 .env 사용)."""
    token = os.getenv("ACCESS_TOKEN")
    if not token:
        raise ValueError(
            "ACCESS_TOKEN이 설정되지 않았습니다. .env 파일에 ACCESS_TOKEN=... 를 추가하세요."
        )
    return token


def fetch_insights(
    ad_account_id: str,
    since: str,
    until: str,
    fields: str = "campaign_name,impressions,clicks,spend",
    api_version: str = "v23.0",
    limit: int = 500,
) -> list[dict[str, Any]]:
    """
    Meta Insights API를 호출하고 pagination을 처리해 모든 결과를 반환합니다.

    Args:
        ad_account_id: 광고계정 ID (숫자만, act_ 접두사 없이)
        since: 시작일 (YYYY-MM-DD)
        until: 종료일 (YYYY-MM-DD)
        fields: 요청할 필드 (쉼표 구분)
        api_version: API 버전 (기본 v23.0)
        limit: 페이지당 레코드 수 (기본 500)

    Returns:
        insights 레코드 리스트
    """
    account_id = (
        ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"
    )
    token = get_access_token()
    base_url = f"https://graph.facebook.com/{api_version}/{account_id}/insights"

    all_data: list[dict[str, Any]] = []
    url: str | None = base_url
    params: dict[str, Any] = {
        "access_token": token,
        "fields": fields,
        "time_range": str({"since": since, "until": until}).replace("'", '"'),
        "limit": limit,
        "level": "campaign",
    }

    while url:
        if url == base_url:
            resp = requests.get(url, params=params, timeout=30)
        else:
            # pagination next URL에는 access_token이 포함되어 있을 수 있음
            resp = requests.get(url, timeout=30)

        resp.raise_for_status()
        body = resp.json()

        if "data" in body and body["data"]:
            all_data.extend(body["data"])

        paging = body.get("paging", {})
        next_url = paging.get("next")
        url = next_url if next_url else None

    return all_data
