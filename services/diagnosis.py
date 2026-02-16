from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd


def get_stats_for_period(df, days, end_date=None):
    """
    기간별 집계. end_date 미지정 시 전일(어제) 기준으로 기간 계산 (당일 제외).
    end_date 지정 시 해당일 포함 과거 days일. (오늘만 보려면 days=1, end_date=today)
    """
    today = datetime.now().date()
    if end_date is None:
        end_date = today - timedelta(days=1)  # 전일 기준 (당일 제외)
    if hasattr(end_date, 'date') and not isinstance(end_date, date):
        end_date = end_date.date()
    start_date = end_date - timedelta(days=days - 1)

    df = df.copy()
    df["_d"] = pd.to_datetime(df["Date"]).dt.date
    filtered = df[(df["_d"] >= start_date) & (df["_d"] <= end_date)]

    stats = filtered.groupby(["Campaign", "AdGroup", "Creative_ID"]).agg({
        "Cost": "sum", "Conversions": "sum", "Impressions": "sum", "Clicks": "sum"
    }).reset_index()
    stats["CPA"] = np.where(stats["Conversions"] > 0, stats["Cost"] / stats["Conversions"], np.inf)
    return stats


def run_diagnosis(df, target_cpa):
    if df.empty:
        return pd.DataFrame()

    today = datetime.now().date()
    yesterday = today - timedelta(days=1)

    # 오늘(1일) + 전일 기준 3일 / 7일 / 14일 (당일 제외)
    s_today = get_stats_for_period(df, 1, end_date=today)
    s3 = get_stats_for_period(df, 3, end_date=yesterday)
    s7 = get_stats_for_period(df, 7, end_date=yesterday)
    s14 = get_stats_for_period(df, 14, end_date=yesterday)
    s_all = get_stats_for_period(df, 9999, end_date=yesterday)

    key = ["Campaign", "AdGroup", "Creative_ID"]
    m = s_today[key + ["Cost", "Conversions", "CPA"]].rename(
        columns={"Cost": "Cost_today", "Conversions": "Conversions_today", "CPA": "CPA_today"}
    )
    m = m.merge(
        s3[key + ["Cost", "Conversions", "CPA"]].rename(
            columns={"Cost": "Cost_3", "Conversions": "Conversions_3", "CPA": "CPA_3"}
        ),
        on=key, how="outer"
    )
    m = m.merge(
        s7[key + ["Cost", "Conversions", "CPA"]].rename(
            columns={"Cost": "Cost_7", "Conversions": "Conversions_7", "CPA": "CPA_7"}
        ),
        on=key, how="left"
    )
    m = m.merge(
        s14[key + ["Cost", "Conversions", "CPA"]].rename(
            columns={"Cost": "Cost_14", "Conversions": "Conversions_14", "CPA": "CPA_14"}
        ),
        on=key, how="left"
    )
    m = m.merge(s_all[key], on=key, how="left")
    m = m.fillna(0)

    for col in ['CPA_today', 'CPA_3', 'CPA_7', 'CPA_14']:
        if col in m.columns:
            m[col] = m[col].replace(0, np.inf)

    results = []
    for _, row in m.iterrows():
        if row['Cost_3'] < 3000:
            continue

        cpa3, cpa7, cpa14 = row['CPA_3'], row['CPA_7'], row['CPA_14']
        status, title, detail = "White", "", ""

        if (cpa14 <= target_cpa) and (cpa7 <= target_cpa) and (cpa3 <= target_cpa):
            status = "Blue"; title = "성과 우수 (Best)"; detail = "14일/7일/3일(전일기준) 모두 목표 달성."
        elif (cpa14 > target_cpa) and (cpa7 > target_cpa) and (cpa3 > target_cpa):
            status = "Red"; title = "종료 추천 (지속 부진)"; detail = "14일/7일/3일(전일기준) 모두 목표 미달성."
        else:
            status = "Yellow"
            if cpa3 <= target_cpa:
                title = "성장 가능성 (반등)"; detail = "과거엔 목표 초과했으나, 최근 3일(전일기준)은 목표 달성."
            else:
                title = "관망 필요 (최근 저하)"; detail = "과거엔 좋았으나, 최근 3일(전일기준)은 목표 초과."

        row['Status_Color'] = status
        row['Diag_Title'] = title
        row['Diag_Detail'] = detail
        results.append(row)

    return pd.DataFrame(results)
