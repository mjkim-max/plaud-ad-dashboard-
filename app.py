from datetime import datetime, timedelta, date

import numpy as np
import pandas as pd
try:
    import plotly.graph_objects as go
except Exception:
    go = None
import streamlit as st
import traceback

try:
    from services.data_loader import (
        load_main_data,
        load_google_demo_data,
        diagnose_meta_no_data,
        get_meta_token_info,
    )
except Exception:
    st.error("data_loader import failed")
    st.code(traceback.format_exc())
    st.stop()
from services.diagnosis import run_diagnosis
from services.action_store import load_actions, upsert_action, delete_action

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
    .tl-note {font-size: 12px; color: #666; text-align: center;}
    .tl-wrap {background: transparent; border: 0; border-radius: 0; padding: 0;}
    .tl-panel {background: #efefef; border: 0; border-radius: 8px; padding: 10px;}
    .tl-cell button {width: 48px !important; height: 44px !important; padding: 0 !important;}
    .tl-cell-selected button {border: 2px solid #111 !important;}
    .tl-cell button p {font-size: 11px !important; line-height: 1.1;}
    .tl-form {display: flex; align-items: center; gap: 8px;}
    .sec-divider {border-top: 1px solid #eef0f2; margin: 10px 0;}
    .v-divider {border-left: 1px solid #eef0f2; padding-left: 12px; height: 100%;}
</style>
""", unsafe_allow_html=True)

# [세션 상태 초기화]
if 'chart_target_creative' not in st.session_state:
    st.session_state['chart_target_creative'] = None
if 'chart_target_adgroup' not in st.session_state:
    st.session_state['chart_target_adgroup'] = None
if 'chart_target_campaign' not in st.session_state:
    st.session_state['chart_target_campaign'] = None
if "action_mode" not in st.session_state:
    st.session_state["action_mode"] = ""
if "action_selected" not in st.session_state:
    st.session_state["action_selected"] = {}
if "camp_loaded" not in st.session_state:
    st.session_state["camp_loaded"] = {}


def _set_selected_date(cid: str, d_str: str) -> None:
    current = dict(st.session_state.get("action_selected", {}))
    current[cid] = d_str
    st.session_state["action_selected"] = current



# -----------------------------------------------------------------------------
# 3. 사이드바 & 데이터 준비
# -----------------------------------------------------------------------------
if "data_cache" not in st.session_state:
    st.session_state["data_cache"] = {}
if "data_loaded_at" not in st.session_state:
    st.session_state["data_loaded_at"] = None

if st.session_state["data_cache"].get("df_raw") is None:
    df_raw, meta_fetched_at, google_fetched_at = load_main_data()
    df_google_demo_raw = load_google_demo_data()
    st.session_state["data_cache"]["df_raw"] = df_raw
    st.session_state["data_cache"]["df_google_demo_raw"] = df_google_demo_raw
    st.session_state["data_cache"]["meta_fetched_at"] = meta_fetched_at
    st.session_state["data_cache"]["google_fetched_at"] = google_fetched_at
    st.session_state["data_loaded_at"] = datetime.now()
else:
    df_raw = st.session_state["data_cache"]["df_raw"]
    df_google_demo_raw = st.session_state["data_cache"]["df_google_demo_raw"]
    meta_fetched_at = st.session_state["data_cache"]["meta_fetched_at"]
    google_fetched_at = st.session_state["data_cache"]["google_fetched_at"]

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

# 데이터 업데이트 버튼
if st.sidebar.button("데이터 업데이트"):
    st.cache_data.clear()
    st.session_state["data_cache"] = {}
    st.session_state["data_loaded_at"] = None
    st.rerun()

# 데이터 로드 상태 (Meta가 선택됐는데 0건이면 원인 진단 후 안내)
if "Meta" in sel_pl and meta_row_count == 0:
    reason = diagnose_meta_no_data()
    st.sidebar.error("**Meta 데이터 없음**")
    st.sidebar.caption(reason)
    st.sidebar.caption("💡 .env를 수정했다면 **Streamlit 중지 후 다시 실행**해야 반영됩니다.")
    err = st.session_state.get("meta_api_error")
    if err:
        st.sidebar.error(err)
elif meta_row_count > 0:
    st.sidebar.caption(f"📊 Meta {meta_row_count:,}건 / Google {google_row_count:,}건 로드")

if "Meta" in sel_pl:
    if meta_fetched_at:
        st.sidebar.caption("Meta 데이터 반영시점")
        st.sidebar.caption(meta_fetched_at.strftime("%Y-%m-%d %H:%M:%S"))
    else:
        st.sidebar.caption("Meta 데이터 반영시점")
        st.sidebar.caption("데이터 없음")


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
        df_filtered = df_filtered[df_filtered['Status'].isin(['ACTIVE', 'On'])]
    elif status_opt == "비게재 (Off)":
        df_filtered = df_filtered[~df_filtered['Status'].isin(['ACTIVE', 'On'])]

target_df = df_filtered.copy()
if sel_camp != '전체': target_df = target_df[target_df['Campaign'] == sel_camp]
if sel_grp != '전체': target_df = target_df[target_df['AdGroup'] == sel_grp]
if sel_crv: target_df = target_df[target_df['Creative_ID'].isin(sel_crv)]

# -----------------------------------------------------------------------------
# 4. 메인 화면: 진단 리포트
# -----------------------------------------------------------------------------
st.title("광고 성과 관리 대시보드")

st.subheader("1. 캠페인 성과 진단")

# 조치 내용 출력
st.markdown("<div class='sec-divider'></div>", unsafe_allow_html=True)
st.markdown("##### 조치 내용 출력")
sheet_err = st.session_state.get("sheet_error")
if sheet_err:
    st.error(f"조치 시트 연결 오류: {sheet_err}")
report_cols = st.columns([2, 1, 6])
with report_cols[0]:
    report_date = st.date_input("날짜 선택", datetime.now().date(), key="action_report_date")
with report_cols[1]:
    run_report = st.button("출력", key="action_report_btn")

if run_report:
    actions_df = load_actions()
    report_date_str = report_date.isoformat()
    if actions_df.empty:
        st.info("조치 내용이 없습니다.")
    else:
        actions_day = actions_df[actions_df["action_date"] == report_date_str]
        if actions_day.empty:
            st.info("선택한 날짜의 조치 내용이 없습니다.")
        else:
            # 선택 날짜에 Spend 1 이상인 소재만
            df_day = df_raw.copy()
            if "Date" in df_day.columns:
                df_day = df_day[df_day["Date"].dt.date == report_date]
            df_day = df_day[df_day["Cost"] >= 1] if "Cost" in df_day.columns else df_day
            valid_creatives = set(df_day["Creative_ID"].astype(str).tolist()) if "Creative_ID" in df_day.columns else set()
            valid_keys = set((df_day["Campaign"].astype(str) + "|" + df_day["AdGroup"].astype(str)).tolist()) if "Campaign" in df_day.columns and "AdGroup" in df_day.columns else set()

            filtered = actions_day[
                (actions_day["creative_id"].astype(str).isin(valid_creatives)) |
                (actions_day["creative_key"].astype(str).isin(valid_keys))
            ]
            if filtered.empty:
                st.info("선택한 날짜에 Spend 1 이상인 소재의 조치 내용이 없습니다.")
            else:
                st.markdown(f"**{report_date.month}/{report_date.day} 조치내용**")
                for _, row in filtered.iterrows():
                    st.markdown(
                        f"{row.get('campaign','')} / {row.get('creative_id','')} / "
                        f"{row.get('action','')} / {row.get('note','')}"
                    )
st.markdown("<div class='sec-divider'></div>", unsafe_allow_html=True)

# 진단 기간: 오늘 포함 최근 15일 (오늘 + 전일기준 14일 모두 포함)
_today_ts = pd.Timestamp(datetime.now().date())
if not df_raw.empty and "Date" in df_raw.columns:
    diag_base = df_raw[(df_raw["Date"].notna()) & (df_raw["Date"] >= (_today_ts - timedelta(days=14)))]
else:
    diag_base = pd.DataFrame()
diag_res = run_diagnosis(diag_base, target_cpa_warning)

if not diag_res.empty:
    if "actions_cache" not in st.session_state:
        st.session_state["actions_cache"] = None
    if st.session_state["actions_cache"] is None:
        st.session_state["actions_cache"] = load_actions()
    actions_df = st.session_state["actions_cache"]
    # 진단 결과에 최신 Status 병합
    if "Status" in df_raw.columns:
        status_src = df_raw.copy()
        if "Date" in status_src.columns:
            status_src = status_src.sort_values("Date")
        status_latest = status_src.dropna(subset=["Status"]).groupby(
            ["Campaign", "AdGroup", "Creative_ID"], as_index=False
        ).tail(1)
        diag_res = diag_res.merge(
            status_latest[["Campaign", "AdGroup", "Creative_ID", "Status"]],
            on=["Campaign", "AdGroup", "Creative_ID"],
            how="left",
        )

    def _is_active_status(v: str) -> bool:
        return str(v).upper() in {"ACTIVE", "ON", "ENABLED"}

    if "Status" in diag_res.columns:
        if status_opt == "게재중 (On)":
            diag_res = diag_res[diag_res["Status"].apply(_is_active_status)]
        elif status_opt == "비게재 (Off)":
            diag_res = diag_res[~diag_res["Status"].apply(_is_active_status)]

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
            with c_3d: st.markdown(fmt_head("3일", *item['stats_3']), unsafe_allow_html=True)
            with c_7d: st.markdown(fmt_head("7일", *item['stats_7']), unsafe_allow_html=True)
            with c_14d: st.markdown(fmt_head("14일", *item['stats_14']), unsafe_allow_html=True)

            st.markdown("<div class='sec-divider'></div>", unsafe_allow_html=True)
            st.markdown("##### 소재별 진단")

            if not st.session_state["camp_loaded"].get(item['name']):
                if st.button("소재별 진단 로드", key=f"load_camp_{item['name']}"):
                    st.session_state["camp_loaded"][item['name']] = True
                    st.rerun()
                else:
                    st.caption("로딩 버튼을 누르면 해당 캠페인 소재별 진단이 표시됩니다.")
                    continue

            for idx, (_, r) in enumerate(item['data'].iterrows()):
                creative_raw = str(r.get("Creative_ID", "")).strip()
                if creative_raw.lower() in ("", "nan", "none"):
                    creative_label = ""
                    creative_id = ""
                else:
                    creative_label = creative_raw
                    creative_id = creative_raw
                campaign_name = str(r.get("Campaign", "")).strip()
                adgroup_name = str(r.get("AdGroup", "")).strip()
                creative_key = creative_id if creative_id else f"{campaign_name}|{adgroup_name}"
                is_inactive = False
                if "Status" in r:
                    is_inactive = not _is_active_status(r.get("Status"))
                inactive_color = "#9aa0a6"
                title_color = inactive_color if is_inactive else "inherit"
                st.markdown(
                    f"<div style='color:{title_color}; font-size: 1.1rem; font-weight: 600;'>"
                    f"{creative_label}</div>",
                    unsafe_allow_html=True,
                )

                col0, col1, col2, col3 = st.columns([1, 1, 1, 1])

                def format_stat_block(label, cpa, cost, conv, text_color):
                    cpa_val = "∞" if cpa == np.inf or (isinstance(cpa, float) and np.isinf(cpa)) else f"{cpa:,.0f}"
                    return (
                        f"<div style=\"line-height:1.6; color:{text_color};\">"
                        f"<strong>{label}</strong><br>CPA <strong>{cpa_val}원</strong><br>"
                        f"비용 {cost:,.0f}원<br>전환 {conv:,.0f}</div>"
                    )

                cpa_t = r.get("CPA_today", 0) or 0
                cost_t = r.get("Cost_today", 0) or 0
                conv_t = r.get("Conversions_today", 0) or 0
                t_color = inactive_color if is_inactive else "inherit"
                with col0: st.markdown(format_stat_block("오늘", cpa_t, cost_t, conv_t, t_color), unsafe_allow_html=True)
                with col1: st.markdown(format_stat_block("3일", r['CPA_3'], r['Cost_3'], r['Conversions_3'], t_color), unsafe_allow_html=True)
                with col2: st.markdown(format_stat_block("7일", r['CPA_7'], r['Cost_7'], r['Conversions_7'], t_color), unsafe_allow_html=True)
                with col3: st.markdown(format_stat_block("14일", r['CPA_14'], r['Cost_14'], r['Conversions_14'], t_color), unsafe_allow_html=True)

                # 소재별 타임라인/입력/진단 (최근 14일)
                today = datetime.now().date()
                start = today - timedelta(days=13)
                dates = [start + timedelta(days=i) for i in range(14)]
                cid = creative_key
                if cid not in st.session_state["action_selected"]:
                    _set_selected_date(cid, today.isoformat())
                selected_date = st.session_state["action_selected"].get(cid, "")

                if not actions_df.empty:
                    ad_actions = actions_df[
                        (actions_df["creative_key"] == cid) |
                        (actions_df["creative_id"] == creative_id)
                    ]
                else:
                    ad_actions = pd.DataFrame(columns=actions_df.columns)

                action_by_date = {}
                for _, ar in ad_actions.iterrows():
                    action_by_date[str(ar["action_date"])] = str(ar["action"]).strip()

                # 3컬럼: 좌/중/우 + 중간 여백
                tl_left, gap1, tl_mid, gap2, tl_right = st.columns([3, 0.4, 3, 0.4, 3])
                with tl_left:
                    st.markdown("<div class='tl-panel'>", unsafe_allow_html=True)
                    st.markdown("<div class='tl-wrap'>", unsafe_allow_html=True)
                    weekday_cols = st.columns(7)
                    weekday_labels = ["일", "월", "화", "수", "목", "금", "토"]
                    for col, lbl in zip(weekday_cols, weekday_labels):
                        col.markdown(f"<div class='tl-note'><strong>{lbl}</strong></div>", unsafe_allow_html=True)

                    # 요일 정렬을 위한 빈 칸 보정
                    offset = (start.weekday() + 1) % 7  # Sunday=0
                    cells = [""] * offset + [d.isoformat() for d in dates]
                    while len(cells) % 7 != 0:
                        cells.append("")

                    for row_start in range(0, len(cells), 7):
                        cols = st.columns(7)
                        for col, d_str in zip(cols, cells[row_start:row_start + 7]):
                            if not d_str:
                                col.markdown("<div class='tl-note'></div>", unsafe_allow_html=True)
                                continue
                            d = datetime.fromisoformat(d_str).date()
                            act = action_by_date.get(d_str, "").strip()
                            icon = "⬜"
                            if act == "증액":
                                icon = "🟦"
                            elif act == "보류":
                                icon = "🟨"
                            elif act == "종료":
                                icon = "🟥"
                            label = f"{icon}\n{d.strftime('%m/%d')}"
                            with col:
                                cls = "tl-cell-selected" if d_str == selected_date else "tl-cell"
                                st.markdown(f"<div class='{cls}'>", unsafe_allow_html=True)
                                key_id = f"tl_{item['name']}_{r['AdGroup']}_{cid}_{d_str}_{idx}"
                                if st.button(label, key=key_id, on_click=_set_selected_date, args=(cid, d_str)):
                                    pass
                                st.markdown("</div>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                with tl_mid:
                    st.markdown("<div class='tl-panel'>", unsafe_allow_html=True)
                    if selected_date:
                        st.caption(f"선택된 날짜: {selected_date}")
                    else:
                        st.caption("선택된 날짜: 없음")
                    if selected_date:
                        existing = ad_actions[ad_actions["action_date"] == selected_date]
                        existing_action = existing["action"].iloc[0] if not existing.empty else ""
                        existing_note = existing["note"].iloc[0] if not existing.empty else ""
                    else:
                        existing_action = ""
                        existing_note = ""

                    form_key = f"act_form_{item['name']}_{r['AdGroup']}_{cid}_{selected_date or 'none'}_{idx}"
                    with st.form(key=form_key):
                        action = st.selectbox(
                            "구분",
                            ["증액", "보류", "종료", "유지"],
                            index=["증액", "보류", "종료", "유지"].index(existing_action)
                            if existing_action in ["증액", "보류", "종료", "유지"] else 3
                        )
                        note = st.text_area("상세 내용", value=existing_note, height=140)
                        btn_cols = st.columns([1, 1, 6])
                        with btn_cols[0]:
                            submitted = st.form_submit_button("저장")
                        with btn_cols[1]:
                            do_delete = st.form_submit_button("삭제")

                        if do_delete:
                            if selected_date:
                                try:
                                    delete_action(action_date=selected_date, creative_key=cid)
                                    st.session_state["actions_cache"] = None
                                    st.success("삭제 완료")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"삭제 실패: {e}")
                            else:
                                st.info("날짜를 먼저 선택하세요.")
                        if submitted:
                            if not selected_date:
                                st.info("날짜를 먼저 선택하세요.")
                            else:
                                try:
                                    upsert_action(
                                        action_date=selected_date,
                                        creative_id=creative_id,
                                        creative_key=cid,
                                        campaign=str(r.get("Campaign", "")),
                                        adgroup=str(r.get("AdGroup", "")),
                                        action=action,
                                        note=note,
                                        author="",
                                    )
                                    st.session_state["actions_cache"] = None
                                    st.success("저장 완료")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"저장 실패: {e}")
                    st.markdown("</div>", unsafe_allow_html=True)
                    st.markdown("</div>", unsafe_allow_html=True)

                with tl_right:
                    st.markdown("<div class='tl-panel'>", unsafe_allow_html=True)
                    st.markdown("<div style='font-size: 1.1rem; font-weight: 700; margin-bottom: 6px;'>조치 추천</div>", unsafe_allow_html=True)
                    title_style = f"color:{inactive_color};" if is_inactive else ""
                    detail_style = f"color:{inactive_color};" if is_inactive else ""
                    st.markdown(f"<div style='{title_style}'><strong>{r['Diag_Title']}</strong></div>", unsafe_allow_html=True)
                    detail_txt = str(r.get("Diag_Detail", ""))
                    st.markdown(f"<div style='{detail_style} font-size: 0.85rem; margin-bottom: 6px;'>{detail_txt}</div>", unsafe_allow_html=True)

                    def _safe(v):
                        if v is None or v == np.inf or (isinstance(v, float) and np.isinf(v)):
                            return None
                        return float(v)

                    def _pct_change(a, b):
                        if a in (None, 0) or b is None:
                            return None
                        return (b - a) / a

                    def _trend_icon(v):
                        if v is None:
                            return "➖"
                        if v > 0:
                            return "📈"
                        if v < 0:
                            return "📉"
                        return "➖"

                    def _trend_label(v):
                        if v is None:
                            return "보합"
                        if v > 0:
                            return "상승"
                        if v < 0:
                            return "하락"
                        return "보합"

                    cpa_14 = _safe(r.get("CPA_14"))
                    cpa_7 = _safe(r.get("CPA_7"))
                    cpa_3 = _safe(r.get("CPA_3"))

                    def _cpa_dot(v):
                        if v is None:
                            return "⚪"
                        if v <= 80000:
                            return "🔵"
                        if v >= 120000:
                            return "🔴"
                        return "⚪"

                    cpa_flow_text = f"{_cpa_dot(cpa_14)}➡{_cpa_dot(cpa_7)}➡{_cpa_dot(cpa_3)}"
                    st.markdown("**CPA 흐름 (14→7→3)**")
                    st.markdown(cpa_flow_text)

                    cpm_7 = _safe(r.get("CPM_7"))
                    cpm_3 = _safe(r.get("CPM_3"))
                    cpm_change = _pct_change(cpm_7, cpm_3)
                    cpm_label = _trend_label(cpm_change)
                    cpm_icon = _trend_icon(cpm_change)
                    cpm_pct = f"{cpm_change*100:,.0f}%" if cpm_change is not None else "-"
                    st.markdown(f"**CPM 추세 (3d vs 7d)**  \n{cpm_icon} {cpm_label} ({cpm_pct})")

                    ctr_7 = _safe(r.get("CTR_7"))
                    ctr_3 = _safe(r.get("CTR_3"))
                    ctr_change = _pct_change(ctr_7, ctr_3)
                    ctr_label = _trend_label(ctr_change)
                    ctr_icon = _trend_icon(ctr_change)
                    ctr_pct = f"{ctr_change*100:,.0f}%" if ctr_change is not None else "-"
                    st.markdown(f"**CTR 추세 (3d vs 7d)**  \n{ctr_icon} {ctr_label} ({ctr_pct})")

                    cvr_7 = _safe(r.get("CVR_7"))
                    cvr_3 = _safe(r.get("CVR_3"))
                    cvr_change = _pct_change(cvr_7, cvr_3)
                    cvr_label = _trend_label(cvr_change)
                    cvr_icon = _trend_icon(cvr_change)
                    cvr_pct = f"{cvr_change*100:,.0f}%" if cvr_change is not None else "-"
                    st.markdown(f"**CVR 추세 (3d vs 7d)**  \n{cvr_icon} {cvr_label} ({cvr_pct})")

                    # 간단 규칙 기반 스토리
                    story = "데이터가 부족해 명확한 결론을 내리기 어렵습니다."
                    if cpm_change is not None and ctr_change is not None:
                        if cpm_change < 0 and ctr_change < 0:
                            story = "CPM/CTR이 함께 내려가는 흐름입니다. 기존 타겟 소진 후 확장 구간일 가능성이 있어 2~3일 관망이 합리적입니다."
                        elif cpm_change > 0 and ctr_change > 0:
                            story = "CPM/CTR이 함께 상승합니다. 타겟 정교화 또는 학습 재수렴 신호일 수 있어 성과 지표와 함께 확인하세요."
                    st.markdown("**🤖 AI 분석 코멘트 (스토리)**")
                    st.caption(story)
                    unique_key = f"btn_{item['name']}_{r['Creative_ID']}_{idx}"
                    if st.button("분석하기", key=unique_key):
                        st.session_state['chart_target_creative'] = str(r.get('Creative_ID', ''))
                        st.session_state['chart_target_adgroup'] = r['AdGroup']
                        st.session_state['chart_target_campaign'] = r['Campaign']
                        st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("<div class='sec-divider'></div>", unsafe_allow_html=True)
else:
    st.info("진단 데이터 부족")

# -----------------------------------------------------------------------------
# 5. 추세 그래프 & 상세 표 & 성별/연령 분석
# -----------------------------------------------------------------------------
st.markdown("---")
st.subheader("2. 지표별 추세 및 상세 분석")

target_creative = st.session_state['chart_target_creative']
target_adgroup = st.session_state['chart_target_adgroup']
target_campaign = st.session_state['chart_target_campaign']

trend_df = target_df.copy()
demog_df = pd.DataFrame()
is_specific = False

has_selection = (target_creative is not None and str(target_creative) != "") or bool(target_adgroup) or bool(target_campaign)
if has_selection:
    if target_creative and 'Creative_ID' in trend_df.columns:
        trend_df['Creative_ID'] = trend_df['Creative_ID'].astype(str)
        trend_df = trend_df[trend_df['Creative_ID'] == str(target_creative)]
    else:
        if target_adgroup:
            trend_df = trend_df[trend_df['AdGroup'] == target_adgroup]
        if target_campaign:
            trend_df = trend_df[trend_df['Campaign'] == target_campaign]

    sel_row = trend_df
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

    # 날짜 필터로 인해 비어있는 경우, 전체 데이터에서 재시도
    if trend_df.empty and not df_raw.empty:
        full_df = df_raw.copy()
        if target_creative:
            if "Creative_ID" in full_df.columns:
                full_df['Creative_ID'] = full_df['Creative_ID'].astype(str)
            trend_df = full_df[full_df['Creative_ID'] == str(target_creative)]
        else:
            if target_adgroup:
                full_df = full_df[full_df['AdGroup'] == target_adgroup]
            if target_campaign:
                full_df = full_df[full_df['Campaign'] == target_campaign]
            trend_df = full_df
        if not trend_df.empty:
            st.warning("선택한 날짜 범위에 데이터가 없어, 전체 기간 데이터를 표시합니다.")

    if st.button("전체 목록으로 차트 초기화"):
        st.session_state['chart_target_creative'] = None
        st.session_state['chart_target_adgroup'] = None
        st.session_state['chart_target_campaign'] = None
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
    default=['Conversions', 'CPM', 'CTR', 'Impressions']
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
            male_y = -male_data['Conversions']
            female_y = female_data['Conversions']
            fig_conv.add_trace(go.Bar(y=male_data['Age'], x=male_y, name='남성', orientation='h', marker_color='#9EB9F3'))
            fig_conv.add_trace(go.Bar(y=female_data['Age'], x=female_y, name='여성', orientation='h', marker_color='#F8C8C8'))
            fig_conv.update_layout(
                barmode='overlay',
                height=380,
                margin=dict(l=20, r=20, t=20, b=20),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                xaxis=dict(title="전환수", zeroline=True, zerolinewidth=1, zerolinecolor="#999", tickformat=","),
                yaxis=dict(title="연령", categoryorder="category ascending")
            )
            left, right = st.columns([1, 1])
            with left:
                st.plotly_chart(fig_conv, use_container_width=True)
            with right:
                st.markdown("**CPA**")
                st.dataframe(
                    demog_agg.pivot_table(index='Gender', columns='Age', values='CPA', aggfunc='sum', fill_value=0).style.format("{:,.0f}"),
                    use_container_width=True
                )
                st.markdown("**비용**")
                st.dataframe(
                    demog_agg.pivot_table(index='Gender', columns='Age', values='Cost', aggfunc='sum', fill_value=0).style.format("{:,.0f}"),
                    use_container_width=True
                )
else:
    st.warning("설정된 기간 내에 데이터가 없습니다.")
