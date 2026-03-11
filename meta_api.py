"""
Meta Marketing API - Insights API 호출
광고 성과 관리 BI 앱용 (ad 레벨, 일별)
"""

import os
import re
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
    max_pages: Optional[int] = 15,
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
    pages_left = max_pages if max_pages is not None else 10**9
    while url and pages_left > 0:
        pages_left -= 1
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


def _extract_first_url(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"(https?://[^\s]+)", str(text))
    return m.group(1).strip() if m else ""


def _extract_video_id_and_url_from_creative(creative: dict[str, Any]) -> tuple[str, str]:
    """
    Meta creative payload에서 video_id/video_url 후보를 최대한 안전하게 추출.
    """
    if not creative:
        return "", ""

    object_story_spec = creative.get("object_story_spec") or {}
    asset_feed_spec = creative.get("asset_feed_spec") or {}

    video_id = ""
    video_url = ""

    # 1) object_story_spec.video_data
    video_data = object_story_spec.get("video_data") or {}
    if isinstance(video_data, dict):
        video_id = str(video_data.get("video_id") or "").strip()
        video_url = str(video_data.get("video_url") or "").strip()
        if not video_url:
            cta_link = ((video_data.get("call_to_action") or {}).get("value") or {}).get("link")
            video_url = str(cta_link or "").strip()

    # 2) object_story_spec.link_data / template_data / child_attachments
    link_data = object_story_spec.get("link_data") or {}
    if isinstance(link_data, dict):
        if not video_id:
            video_id = str(link_data.get("video_id") or "").strip()
        if not video_url:
            video_url = str(link_data.get("link") or "").strip()
        if not video_url:
            template_data = link_data.get("template_data") or {}
            if isinstance(template_data, dict):
                video_url = str(template_data.get("link") or "").strip()
        if not video_url:
            children = link_data.get("child_attachments") or []
            if isinstance(children, list):
                for ch in children:
                    if not isinstance(ch, dict):
                        continue
                    cand = str(ch.get("link") or "").strip()
                    if cand:
                        video_url = cand
                        break

    # 3) asset_feed_spec.videos[0].video_id
    if not video_id:
        videos = asset_feed_spec.get("videos") or []
        if isinstance(videos, list) and videos:
            first_video = videos[0] or {}
            video_id = str(first_video.get("video_id") or "").strip()

    # 4) landing URL fallback (asset feed)
    if not video_url:
        link_urls = asset_feed_spec.get("link_urls") or []
        if isinstance(link_urls, list) and link_urls:
            first_link = link_urls[0] or {}
            video_url = str(first_link.get("website_url") or first_link.get("display_url") or "").strip()

    # 5) id 기반 watch URL 보정
    if not video_url and video_id:
        video_url = f"https://www.facebook.com/watch/?v={video_id}"

    # 6) 최후 fallback: 문자열 안 URL 탐색
    if not video_url:
        for candidate in (
            str(creative.get("name") or ""),
            str(object_story_spec),
            str(asset_feed_spec),
        ):
            video_url = _extract_first_url(candidate)
            if video_url:
                break

    return video_id, video_url


def fetch_ad_video_assets(
    ad_ids: list[str],
    *,
    token: Optional[str] = None,
    api_version: str = "v23.0",
) -> dict[str, dict[str, str]]:
    """
    ad_id별 video_id/video_url + ad/adset/campaign 상태 추출.
    Returns:
        {
          "123": {
            "video_id": "...",
            "video_url": "...",
            "video_key": "...",
            "ad_status": "...",
            "adset_status": "...",
            "campaign_status": "..."
          },
          ...
        }
    """
    cleaned = [str(v).strip() for v in ad_ids if str(v).strip()]
    if not cleaned:
        return {}

    token = token or get_access_token()
    if not token:
        return {}

    base_url = f"https://graph.facebook.com/{api_version}"
    fields = "id,name,effective_status,adset{id,effective_status},campaign{id,effective_status},creative{id,object_story_id,effective_object_story_id,object_story_spec,asset_feed_spec,name}"
    out: dict[str, dict[str, str]] = {}
    chunk_size = 25

    for i in range(0, len(cleaned), chunk_size):
        chunk = cleaned[i:i + chunk_size]
        params = {
            "access_token": token,
            "ids": ",".join(chunk),
            "fields": fields,
        }
        resp = requests.get(f"{base_url}/", params=params, timeout=25)
        resp.raise_for_status()
        body = resp.json()

        for ad_id in chunk:
            row = body.get(str(ad_id)) or {}
            creative = row.get("creative") or {}
            video_id, video_url = _extract_video_id_and_url_from_creative(creative)
            video_key = ""
            if video_url:
                video_key = video_url
            elif video_id:
                video_key = f"video_id:{video_id}"
            else:
                video_key = f"ad_id:{ad_id}"

            ad_status = str(row.get("effective_status") or "").strip()
            adset = row.get("adset") or {}
            campaign = row.get("campaign") or {}
            adset_status = str(adset.get("effective_status") or "").strip()
            campaign_status = str(campaign.get("effective_status") or "").strip()
            creative_id = str(creative.get("id") or "").strip()
            story_id = str(
                creative.get("effective_object_story_id")
                or creative.get("object_story_id")
                or ""
            ).strip()

            out[str(ad_id)] = {
                "video_id": video_id,
                "video_url": video_url,
                "video_key": video_key,
                "ad_status": ad_status,
                "adset_status": adset_status,
                "campaign_status": campaign_status,
                "creative_id": creative_id,
                "story_id": story_id,
            }

    return out


def fetch_video_source_url(
    video_id: str,
    *,
    token: Optional[str] = None,
    api_version: str = "v23.0",
) -> str:
    """
    video_id의 재생 가능한 source URL(가능 시) 또는 permalink를 반환.
    """
    vid = str(video_id or "").strip()
    if not vid:
        return ""
    token = token or get_access_token()
    if not token:
        return f"https://www.facebook.com/watch/?v={vid}"

    base_url = f"https://graph.facebook.com/{api_version}"
    params = {"access_token": token, "fields": "source,permalink_url"}
    resp = requests.get(f"{base_url}/{vid}", params=params, timeout=25)
    resp.raise_for_status()
    body = resp.json()
    return str(body.get("source") or body.get("permalink_url") or f"https://www.facebook.com/watch/?v={vid}")
