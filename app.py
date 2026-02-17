from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
try:
    import plotly.graph_objects as go
except Exception:
    go = None
import streamlit as st

from services.data_loader import (
    load_main_data,
    load_google_demo_data,
    diagnose_meta_no_data,
    get_meta_token_info,
)
from services.diagnosis import run_diagnosis

# -----------------------------------------------------------------------------
# [SETUP] 페이지 설정
# -----------------------------------------------------------------------------
st.set_page_config(page_title="광고 성과 관리 BI", page_icon=None, layout="wide")
if go is None:
    st.error("plotly 패키지가 설치되어 있지 않습니다. 네트워크가 되는 환경에서 설치해 주세요.")
    st.code("/Users/kmj/Desktop/Cursor/venv/bin/pip install plotly", language="bash")
    st.stop()

st.markdown("""
<style>
    .block-container {padding-top: 1rem; padding-bottom: 2rem;}
    div[data-testid="stExpanderDetails"] {padding-top: 0.5rem; padding-bottom: 0.5rem;}
    p {margin-bottom: 0px !important;} 
    hr {margin: 0.5rem 0 !important;}
</style>
""", unsafe_allow_html=True)

# [세션 상태 초기화]
if 'chart_target_creative' not in st.session_state:
    st.session_state['chart_target_creative'] = None
if 'chart_target_adgroup' not in st.session_state:
    st.session_state['chart_target_adgroup'] = None

# -----------------------------------------------------------------------------
# 3. 사이드바 & 데이터 준비
# -----------------------------------------------------------------------------
df_raw, meta_fetched_at, google_fetched_at = load_main_data()
df_google_demo_raw = load_google_demo_data()

# Meta 로드 건수 (필터 적용 전 기준, 진단/표시용)
meta_row_count = int((df_raw["Platform"] == "Meta").sum()) if (not df_raw.empty and "Platform" in df_raw.columns) else 0
google_row_count = int((df_raw["Platform"] == "Google").sum()) if (not df_raw.empty and "Platform" in df_raw.columns) else 0

st.sidebar.header("목표 설정")
target_cpa_warning = st.sidebar.number_input("목표 CPA", value=100000, step=1000)
st.sidebar.markdown("---")

st.sidebar.header("기간 설정")
preset = st.sidebar.selectbox(
    "기간선택",
    ["오늘", "어제", "최근 3일", "최근 7일", "최근 14일", "최근 30일", "이번 달", "지난 달", "최근 90일", "전체 기간"],
    index=4
)
today = datetime.now().date()

# [중요] 사용자가 데이터를 2025년과 2026년을 섞어서 넣었으므로, 기본 날짜 계산을 유연하게
if preset == "오늘": s, e = today, today
elif preset == "어제": s = today - timedelta(days=1); e = s
elif preset == "최근 3일": s = today - timedelta(days=2); e = today
elif preset == "최근 7일": s = today - timedelta(days=6); e = today
elif preset == "최근 14일": s = today - timedelta(days=13); e = today
elif preset == "최근 30일": s = today - timedelta(days=29); e = today
elif preset == "최근 90일": s = today - timedelta(days=89); e = today
elif preset == "이번 달": s = date(today.year, today.month, 1); e = today
elif preset == "지난 달":
    first = date(today.year, today.month, 1); e = first - timedelta(days=1); s = date(e.year, e.month, 1)
elif preset == "전체 기간": s = date(2020, 1, 1); e = today  # 충분히 넓게

date_range = st.sidebar.date_input("날짜범위", [s, e])
st.sidebar.markdown("---")

st.sidebar.header("필터 설정")
c_m, c_g = st.sidebar.columns(2)
sel_pl = []
if c_m.checkbox("Meta", True): sel_pl.append("Meta")
if c_g.checkbox("Google", True): sel_pl.append("Google")
if 'Platform' in df_raw.columns:
    df_raw = df_raw[df_raw['Platform'].isin(sel_pl)]

# 데이터 로드 상태 (Meta가 선택됐는데 0건이면 원인 진단 후 안내)
if "Meta" in sel_pl and meta_row_count == 0:
    reason = diagnose_meta_no_data()
    st.sidebar.error("**Meta 데이터 없음**")
    st.sidebar.caption(reason)
    st.sidebar.caption("💡 .env를 수정했다면 **Streamlit 중지 후 다시 실행**해야 반영됩니다.")
elif meta_row_count > 0:
    st.sidebar.caption(f"📊 Meta {meta_row_count:,}건 / Google {google_row_count:,}건 로드")

if "Meta" in sel_pl:
    if meta_fetched_at:
        st.sidebar.caption("Meta 데이터 반영시점")
        st.sidebar.caption(meta_fetched_at.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        st.sidebar.caption("Meta 데이터 반영시점")
        st.sidebar.caption("데이터 없음")

    if st.sidebar.checkbox("디버그: 토큰 상태"):
        info = get_meta_token_info()
        st.sidebar.caption(f"토큰 소스: {info['source']}")
        st.sidebar.caption(f"토큰 길이: {info['length']}")
        st.sidebar.caption(f"secrets 키: {', '.join(info['keys']) if info['keys'] else '-'}")
        if info.get("error"):
            st.sidebar.caption(f"secrets 오류: {info['error']}")

if "Google" in sel_pl:
    if google_fetched_at:
        st.sidebar.caption("Google 데이터 반영시점")
        st.sidebar.caption(google_fetched_at.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        st.sidebar.caption("Google 데이터 반영시점")
        st.sidebar.caption("데이터 없음")
        err = None
        try:
            err = st.session_state.get("google_api_error")
        except Exception:
            err = None
        if err:
            st.sidebar.error(err)

# 1. Main Data 필터링
df_filtered = df_raw.copy()
if len(date_range) == 2 and not df_filtered.empty and 'Date' in df_filtered.columns:
    df_filtered = df_filtered[(df_filtered['Date'].dt.date >= date_range[0]) & (df_filtered['Date'].dt.date <= date_range[1])]

# 2. Google Demo Data 필터링
df_google_demo_filtered = df_google_demo_raw.copy()
if not df_google_demo_filtered.empty and 'Date' in df_google_demo_filtered.columns and len(date_range) == 2:
    df_google_demo_filtered = df_google_demo_filtered[
        (df_google_demo_filtered['Date'].dt.date >= date_range[0]) &
        (df_google_demo_filtered['Date'].dt.date <= date_range[1])
    ]

camps = ['전체'] + sorted(df_filtered['Campaign'].unique().tolist()) if (not df_filtered.empty and 'Campaign' in df_filtered.columns) else ['전체']
sel_camp = st.sidebar.selectbox("캠페인필터", camps)

grps = ['전체']
if sel_camp != '전체' and (not df_filtered.empty):
    grps = ['전체'] + sorted(df_filtered[df_filtered['Campaign'] == sel_camp]['AdGroup'].unique().tolist())
sel_grp = st.sidebar.selectbox("광고그룹필터", grps)

crvs = []
if sel_grp != '전체' and (not df_filtered.empty):
    crvs = sorted(df_filtered[df_filtered['AdGroup'] == sel_grp]['Creative_ID'].unique().tolist())
sel_crv = st.sidebar.multiselect("광고소재필터", crvs)

status_opt = st.sidebar.radio("게재상태", ["전체", "게재중 (On)", "비게재 (Off)"], index=1)
if 'Status' in df_filtered.columns:
    if status_opt == "게재중 (On)":
        df_filtered = df_filtered[df_filtered['Status'] == 'On']
    elif status_opt == "비게재 (Off)":
        df_filtered = df_filtered[df_filtered['Status'] == 'Off']

target_df = df_filtered.copy()
if sel_camp != '전체': target_df = target_df[target_df['Campaign'] == sel_camp]
if sel_grp != '전체': target_df = target_df[target_df['AdGroup'] == sel_grp]
if sel_crv: target_df = target_df[target_df['Creative_ID'].isin(sel_crv)]

# -----------------------------------------------------------------------------
# 4. 메인 화면: 진단 리포트
# -----------------------------------------------------------------------------
st.title("광고 성과 관리 대시보드")

st.subheader("1. 캠페인 성과 진단")

# 진단 기간: 오늘 포함 최근 15일 (오늘 + 전일기준 14일 모두 포함)
_today_ts = pd.Timestamp(datetime.now().date())
if not df_raw.empty and "Date" in df_raw.columns:
    diag_base = df_raw[(df_raw["Date"].notna()) & (df_raw["Date"] >= (_today_ts - timedelta(days=14)))]
else:
    diag_base = pd.DataFrame()
diag_res = run_diagnosis(diag_base, target_cpa_warning)

if not diag_res.empty:
    camp_grps = diag_res.groupby('Campaign')
    sorted_camps = []

    for c_name, grp in camp_grps:
        has_red = 'Red' in grp['Status_Color'].values
        has_yellow = 'Yellow' in grp['Status_Color'].values
        prio = 1 if has_red else 2 if has_yellow else 3
        h_col = ":red" if has_red else ":orange" if has_yellow else ":blue"

        ct = grp['Cost_today'].sum() if 'Cost_today' in grp.columns else 0
        cvt = grp['Conversions_today'].sum() if 'Conversions_today' in grp.columns else 0
        cpa_today = ct / cvt if cvt > 0 else 0
        c3 = grp['Cost_3'].sum(); cv3 = grp['Conversions_3'].sum()
        cpa3 = c3 / cv3 if cv3 > 0 else 0
        c7 = grp['Cost_7'].sum(); cv7 = grp['Conversions_7'].sum()
        cpa7 = c7 / cv7 if cv7 > 0 else 0
        c14 = grp['Cost_14'].sum(); cv14 = grp['Conversions_14'].sum()
        cpa14 = c14 / cv14 if cv14 > 0 else 0

        sorted_camps.append({
            'name': c_name, 'data': grp, 'prio': prio, 'header': c_name, 'color': h_col,
            'stats_today': (cpa_today, ct, cvt),
            'stats_3': (cpa3, c3, cv3), 'stats_7': (cpa7, c7, cv7), 'stats_14': (cpa14, c14, cv14)
        })

    sorted_camps.sort(key=lambda x: x['prio'])

    for item in sorted_camps:
        if sel_camp != '전체' and item['name'] != sel_camp:
            continue

        with st.expander(f"{item['color']}[{item['header']}]", expanded=False):
            st.markdown("##### 캠페인 기간별 성과 요약")
            c_today, c_3d, c_7d, c_14d = st.columns(4)

            def fmt_head(label, cpa, cost, conv):
                return f"""<div style="line-height:1.4;"><strong>{label}</strong><br>CPA <strong>{cpa:,.0f}원</strong><br>비용 {cost:,.0f}원<br>전환 {conv:,.0f}</div>"""

            with c_today: st.markdown(fmt_head("오늘", *item['stats_today']), unsafe_allow_html=True)
            with c_3d: st.markdown(fmt_head("3일(전일기준)", *item['stats_3']), unsafe_allow_html=True)
            with c_7d: st.markdown(fmt_head("7일(전일기준)", *item['stats_7']), unsafe_allow_html=True)
            with c_14d: st.markdown(fmt_head("14일(전일기준)", *item['stats_14']), unsafe_allow_html=True)

            st.markdown("<hr style='margin: 10px 0; border: none; border-top: 1px solid #f0f2f6;'>", unsafe_allow_html=True)
            st.markdown("##### 소재별 진단")

            for idx, (_, r) in enumerate(item['data'].iterrows()):
                st.markdown(f"#### {r['Creative_ID']}")
                col0, col1, col2, col3, col4 = st.columns([1, 1, 1, 1, 1.2])

                def format_stat_block(label, cpa, cost, conv):
                    cpa_val = "∞" if cpa == np.inf or (isinstance(cpa, float) and np.isinf(cpa)) else f"{cpa:,.0f}"
                    return f"""<div style="line-height:1.6;"><strong>{label}</strong><br>CPA <strong>{cpa_val}원</strong><br>비용 {cost:,.0f}원<br>전환 {conv:,.0f}</div>"""

                cpa_t = r.get("CPA_today", 0) or 0
                cost_t = r.get("Cost_today", 0) or 0
                conv_t = r.get("Conversions_today", 0) or 0
                with col0: st.markdown(format_stat_block("오늘", cpa_t, cost_t, conv_t), unsafe_allow_html=True)
                with col1: st.markdown(format_stat_block("3일", r['CPA_3'], r['Cost_3'], r['Conversions_3']), unsafe_allow_html=True)
                with col2: st.markdown(format_stat_block("7일", r['CPA_7'], r['Cost_7'], r['Conversions_7']), unsafe_allow_html=True)
                with col3: st.markdown(format_stat_block("14일", r['CPA_14'], r['Cost_14'], r['Conversions_14']), unsafe_allow_html=True)

                with col4:
                    t_col = "red" if r['Status_Color'] == "Red" else "blue" if r['Status_Color'] == "Blue" else "orange"
                    st.markdown(f":{t_col}[**{r['Diag_Title']}**]")
                    st.caption(r['Diag_Detail'])

                    unique_key = f"btn_{item['name']}_{r['Creative_ID']}_{idx}"
                    if st.button("분석하기", key=unique_key):
                        st.session_state['chart_target_creative'] = r['Creative_ID']
                        st.session_state['chart_target_adgroup'] = r['AdGroup']
                        st.rerun()

                st.markdown("<hr style='margin: 5px 0; border: none; border-top: 1px solid #f0f2f6;'>", unsafe_allow_html=True)
else:
    st.info("진단 데이터 부족")

# -----------------------------------------------------------------------------
# 5. 추세 그래프 & 상세 표 & 성별/연령 분석
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("2. 지표별 추세 및 상세 분석")

target_creative = st.session_state['chart_target_creative']
target_adgroup = st.session_state['chart_target_adgroup']

trend_df = target_df.copy()
demog_df = pd.DataFrame()
is_specific = False

if target_creative:
    trend_df = target_df[target_df['Creative_ID'] == target_creative]

    sel_row = target_df[target_df['Creative_ID'] == target_creative]
    if not sel_row.empty:
        platform = sel_row['Platform'].iloc[0]
        current_adgroup = target_adgroup if target_adgroup else sel_row['AdGroup'].iloc[0]

        if platform == 'Google':
            if not df_google_demo_filtered.empty:
                demog_df = df_google_demo_filtered[df_google_demo_filtered['AdGroup'] == current_adgroup]

                if demog_df.empty:
                    st.warning(f"⚠️ '{current_adgroup}' 광고그룹 데이터가 하단 시트에 없습니다. 날짜범위({date_range[0]}~{date_range[1]})가 맞는지 확인해주세요. (시트 날짜: 2025년 / 현재 선택: 2026년 가능성)")
                else:
                    st.info(f"🔎 **'{target_creative}'** (구글) 분석 중. 인구통계는 **'{current_adgroup}'** 광고그룹 전체 기준입니다.")
            else:
                st.warning("구글 인구통계 데이터가 날짜 필터링에 의해 모두 제외되었습니다. 기간 설정을 확인해주세요.")
        else:
            demog_df = trend_df
            st.info(f"🔎 현재 **'{target_creative}'** 소재를 집중 분석 중입니다.")

    is_specific = True

    if st.button("전체 목록으로 차트 초기화"):
        st.session_state['chart_target_creative'] = None
        st.session_state['chart_target_adgroup'] = None
        st.rerun()
else:
    demog_df = target_df.copy()
    st.info("📊 통합 추세 분석 중 (특정 소재를 보려면 위에서 '분석하기'를 누르세요)")

c_freq, c_opts, c_norm = st.columns([1, 2, 1])
freq_option = c_freq.radio("집계 기준", ["1일", "3일", "7일"], horizontal=True)
freq_map = {"1일": "D", "3일": "3D", "7일": "W"}
metrics = c_opts.multiselect(
    "지표 선택",
    ['Impressions', 'Clicks', 'CTR', 'CPM', 'CPC', 'CPA', 'Cost', 'Conversions', 'CVR', 'ROAS'],
    default=['Conversions', 'CPA', 'CTR', 'Impressions']
)
use_norm = c_norm.checkbox("데이터 정규화 (0-100%)", value=True)

if not trend_df.empty and metrics:
    agg_df = trend_df.set_index('Date').groupby(pd.Grouper(freq=freq_map[freq_option])).agg({
        'Cost': 'sum', 'Impressions': 'sum', 'Clicks': 'sum', 'Conversions': 'sum', 'Conversion_Value': 'sum'
    }).reset_index().sort_values('Date', ascending=False)

    agg_df['CPA'] = np.where(agg_df['Conversions'] > 0, agg_df['Cost'] / agg_df['Conversions'], 0)
    agg_df['CPM'] = np.where(agg_df['Impressions'] > 0, agg_df['Cost'] / agg_df['Impressions'] * 1000, 0)
    agg_df['CTR'] = np.where(agg_df['Impressions'] > 0, agg_df['Clicks'] / agg_df['Impressions'] * 100, 0)
    agg_df['CPC'] = np.where(agg_df['Clicks'] > 0, agg_df['Cost'] / agg_df['Clicks'], 0)
    agg_df['CVR'] = np.where(agg_df['Clicks'] > 0, agg_df['Conversions'] / agg_df['Clicks'] * 100, 0)
    agg_df['ROAS'] = np.where(agg_df['Cost'] > 0, agg_df['Conversion_Value'] / agg_df['Cost'] * 100, 0)

    plot_df = agg_df.sort_values('Date', ascending=True)
    fig = go.Figure()

    style_map = {
        'Conversions': {'color': 'black', 'width': 3},
        'CPA': {'color': 'red', 'width': 3},
        'CTR': {'color': 'blue', 'width': 2},
        'Impressions': {'color': 'green', 'width': 2}
    }

    for m in metrics:
        y_data = plot_df[m]
        y_plot = (y_data - y_data.min()) / (y_data.max() - y_data.min()) * 100 if use_norm and y_data.max() > 0 else y_data
        style = style_map.get(m, {'color': None, 'width': 2})
        fig.add_trace(go.Scatter(
            x=plot_df['Date'],
            y=y_plot,
            mode='lines+markers',
            name=m,
            line=dict(color=style['color'], width=style['width']),
            customdata=y_data,
            hovertemplate=f"{m}: %{{customdata:,.2f}}"
        ))

    fig.update_layout(height=450, hovermode='x unified', title=f"추세 분석 ({freq_option} 기준)", plot_bgcolor='white')
    st.plotly_chart(fig, use_container_width=True)

    table_df = agg_df.copy()
    table_df['Date'] = table_df['Date'].dt.strftime('%Y-%m-%d')
    st.dataframe(
        table_df[['Date', 'CPA', 'Cost', 'Impressions', 'CPM', 'Clicks', 'Conversions', 'CTR', 'CPC', 'CVR', 'ROAS']],
        use_container_width=True,
        hide_index=True
    )

    st.divider()
    st.subheader("성별/연령 심층 분석")

    if demog_df.empty or 'Gender' not in demog_df.columns:
        st.info("데이터가 없습니다. (날짜 범위나 시트 데이터를 확인해주세요)")
    else:
        valid_gender_check = demog_df[~demog_df['Gender'].isin(['Unknown', 'unknown', '알수없음'])]
        if valid_gender_check.empty:
            st.info("성별/연령 정보가 없습니다.")
        else:
            demog_agg = valid_gender_check.groupby(['Age', 'Gender']).agg({
                'Cost': 'sum', 'Conversions': 'sum', 'Impressions': 'sum'
            }).reset_index()
            demog_agg['CPA'] = np.where(demog_agg['Conversions'] > 0, demog_agg['Cost'] / demog_agg['Conversions'], 0)

            male_data = demog_agg[demog_agg['Gender'].str.contains('남성|Male|male', case=False, na=False)]
            female_data = demog_agg[demog_agg['Gender'].str.contains('여성|Female|female', case=False, na=False)]

            title_txt = f"{target_creative} 성별/연령별 전환수" if is_specific else "성별/연령별 전환수 (통합)"
            st.markdown(f"#### {title_txt}")

            fig_conv = go.Figure()
            fig_conv.add_trace(go.Bar(x=male_data['Age'], y=male_data['Conversions'], name='남성', marker_color='#9EB9F3'))
            fig_conv.add_trace(go.Bar(x=female_data['Age'], y=female_data['Conversions'], name='여성', marker_color='#F8C8C8'))
            fig_conv.update_layout(
                barmode='group',
                height=350,
                margin=dict(l=20, r=20, t=20, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig_conv, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**CPA**")
                st.dataframe(
                    demog_agg.pivot_table(index='Gender', columns='Age', values='CPA', aggfunc='sum', fill_value=0).style.format("{:,.0f}"),
                    use_container_width=True
                )
            with c2:
                st.markdown("**비용**")
                st.dataframe(
                    demog_agg.pivot_table(index='Gender', columns='Age', values='Cost', aggfunc='sum', fill_value=0).style.format("{:,.0f}"),
                    use_container_width=True
                )
else:
    st.warning("설정된 기간 내에 데이터가 없습니다.")
