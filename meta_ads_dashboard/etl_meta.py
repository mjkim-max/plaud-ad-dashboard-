"""
Meta Insights API 응답을 DataFrame으로 변환하고 SQLite에 저장하는 ETL 모듈
"""

import sqlite3
import os
from pathlib import Path

import pandas as pd

from meta_api import fetch_insights, get_access_token


def safe_float(value: str | int | float | None) -> float:
    """문자열/숫자를 float으로 변환, 불가능하면 0.0 반환."""
    if value is None or value == "":
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def insights_to_dataframe(
    ad_account_id: str,
    since: str,
    until: str,
) -> pd.DataFrame:
    """
    API를 호출한 뒤 pandas DataFrame으로 변환합니다.
    impressions, clicks, spend를 숫자형으로 변환하고 CTR 컬럼을 추가합니다.

    Args:
        ad_account_id: 광고계정 ID
        since: 시작일 (YYYY-MM-DD)
        until: 종료일 (YYYY-MM-DD)

    Returns:
        정제된 DataFrame (campaign_name, date_start, impressions, clicks, spend, ctr)
    """
    raw = fetch_insights(ad_account_id, since=since, until=until)

    if not raw:
        return pd.DataFrame(
            columns=[
                "campaign_name",
                "date_start",
                "impressions",
                "clicks",
                "spend",
                "ctr",
            ]
        )

    rows = []
    for r in raw:
        impressions = safe_float(r.get("impressions"))
        clicks = safe_float(r.get("clicks"))
        spend = safe_float(r.get("spend"))
        ctr = (clicks / impressions * 100) if impressions else 0.0

        rows.append(
            {
                "campaign_name": r.get("campaign_name") or r.get("name") or "",
                "date_start": r.get("date_start", ""),
                "impressions": impressions,
                "clicks": clicks,
                "spend": spend,
                "ctr": round(ctr, 2),
            }
        )

    df = pd.DataFrame(rows)

    # date_start가 없으면 since~until 기준으로 컬럼 채우기
    if "date_start" not in df.columns or df["date_start"].isna().all():
        df["date_start"] = since

    return df


def get_db_path() -> str:
    """SQLite DB 파일 경로 (프로젝트 루트/data/meta_insights.db)."""
    base = Path(__file__).resolve().parent
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    return str(data_dir / "meta_insights.db")


def save_to_sqlite(df: pd.DataFrame, db_path: str | None = None) -> None:
    """
    DataFrame을 SQLite에 저장합니다. 테이블이 없으면 생성합니다.

    Args:
        df: 저장할 DataFrame
        db_path: DB 파일 경로 (None이면 기본 경로 사용)
    """
    if df.empty:
        return

    path = db_path or get_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(path) as conn:
        df.to_sql(
            "insights",
            conn,
            if_exists="append",
            index=False,
            method="multi",
        )


def run_etl(
    ad_account_id: str = "732978580670026",
    since: str | None = None,
    until: str | None = None,
    db_path: str | None = None,
) -> pd.DataFrame:
    """
    ETL 파이프라인 실행: API 호출 → DataFrame 변환 → SQLite 저장.

    Args:
        ad_account_id: 광고계정 ID
        since: 시작일 (YYYY-MM-DD), 미지정 시 최근 7일 기준
        until: 종료일 (YYYY-MM-DD), 미지정 시 오늘
        db_path: SQLite 경로 (None이면 기본)

    Returns:
        생성된 DataFrame
    """
    from datetime import datetime, timedelta

    today = datetime.now().date()
    if until is None:
        until = today.isoformat()
    if since is None:
        since = (today - timedelta(days=7)).isoformat()

    df = insights_to_dataframe(ad_account_id, since=since, until=until)
    save_to_sqlite(df, db_path=db_path)
    return df


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    df = run_etl(since="2025-02-01", until="2025-02-14")
    print(df.head())
