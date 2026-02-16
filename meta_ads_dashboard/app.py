"""
Meta 광고 인사이트 Streamlit 대시보드
DB에서 데이터를 읽어 KPI 카드, 테이블, 막대 그래프를 표시합니다.
"""

from dotenv import load_dotenv

load_dotenv()

import sqlite3
from pathlib import Path

import pandas as pd
import streamlit as st

from etl_meta import get_db_path, run_etl


def load_data_from_db(
    db_path: str | None = None,
    date_start: str | None = None,
    date_end: str | None = None,
) -> pd.DataFrame:
    """SQLite에서 insights 테이블을 읽고, 날짜 필터를 적용해 반환합니다."""
    path = db_path or get_db_path()
    if not Path(path).exists():
        return pd.DataFrame()

    with sqlite3.connect(path) as conn:
        df = pd.read_sql("SELECT * FROM insights", conn)

    if df.empty:
        return df

    if "date_start" in df.columns and date_start:
        df = df[df["date_start"] >= date_start]
    if "date_start" in df.columns and date_end:
        df = df[df["date_start"] <= date_end]

    return df


def main() -> None:
    st.set_page_config(
        page_title="Meta 광고 인사이트",
        page_icon="📊",
        layout="wide",
    )
    st.title("📊 Meta 광고 인사이트 대시보드")

    db_path = get_db_path()

    # 사이드바: 데이터 새로고침 & 날짜 필터
    with st.sidebar:
        st.subheader("데이터")
        if st.button("🔄 API에서 데이터 가져오기 (ETL 실행)"):
            with st.spinner("API 호출 및 DB 저장 중..."):
                try:
                    run_etl(
                        ad_account_id="732978580670026",
                        since=st.session_state.get("filter_since", "2025-02-01"),
                        until=st.session_state.get("filter_until", "2025-02-14"),
                    )
                    st.success("저장 완료")
                except Exception as e:
                    st.error(str(e))

        st.subheader("날짜 필터")
        filter_since = st.date_input("시작일", value=pd.Timestamp("2025-02-01").date())
        filter_end = st.date_input("종료일", value=pd.Timestamp("2025-02-14").date())
        st.session_state["filter_since"] = filter_since.isoformat()
        st.session_state["filter_until"] = filter_end.isoformat()

    df = load_data_from_db(
        db_path=db_path,
        date_start=st.session_state.get("filter_since"),
        date_end=st.session_state.get("filter_until"),
    )

    if df.empty:
        st.info(
            "표시할 데이터가 없습니다. 사이드바에서 'API에서 데이터 가져오기'를 실행하거나, "
            "날짜 범위를 조정해 보세요."
        )
        return

    # KPI 요약 카드
    spend = df["spend"].sum()
    impressions = int(df["impressions"].sum())
    clicks = int(df["clicks"].sum())
    ctr = (df["clicks"].sum() / df["impressions"].sum() * 100) if df["impressions"].sum() else 0

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Spend", f"${spend:,.2f}")
    col2.metric("Impressions", f"{impressions:,}")
    col3.metric("Clicks", f"{clicks:,}")
    col4.metric("CTR (%)", f"{ctr:.2f}%")

    st.divider()

    # 테이블
    st.subheader("캠페인별 데이터")
    st.dataframe(df, use_container_width=True, hide_index=True)

    # 막대 그래프 (캠페인별 Spend)
    st.subheader("캠페인별 Spend")
    agg = (
        df.groupby("campaign_name", as_index=False)["spend"]
        .sum()
        .sort_values("spend", ascending=False)
    )
    if not agg.empty:
        st.bar_chart(agg.set_index("campaign_name"))

    # 캠페인별 Impressions 막대 그래프
    st.subheader("캠페인별 Impressions")
    agg_imp = (
        df.groupby("campaign_name", as_index=False)["impressions"]
        .sum()
        .sort_values("impressions", ascending=False)
    )
    if not agg_imp.empty:
        st.bar_chart(agg_imp.set_index("campaign_name"))


if __name__ == "__main__":
    main()
