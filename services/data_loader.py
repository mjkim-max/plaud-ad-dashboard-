import os
from datetime import timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import streamlit as st
try:
    from dotenv import load_dotenv
except Exception:  # optional dependency
    def load_dotenv(path=None, *args, **kwargs):  # type: ignore[override]
        # Minimal .env loader fallback (KEY=VALUE per line)
        if not path:
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())
            return True
        except Exception:
            return False

from services.meta_parser import parse_meta_actions, parse_meta_action_values
from services.time_utils import kst_now, kst_today
# .env를 프로젝트 루트(app.py 있는 폴더)에서 로드
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# Meta 광고계정 ID (환경변수 우선)
def _get_meta_token() -> str:
    try:
        if "ACCESS_TOKEN" in st.secrets:
            return str(st.secrets["ACCESS_TOKEN"])
        for section in ("general", "secrets", "meta"):
            if section in st.secrets and "ACCESS_TOKEN" in st.secrets[section]:
                return str(st.secrets[section]["ACCESS_TOKEN"])
    except Exception:
        pass
    token = os.getenv("ACCESS_TOKEN")
    if token:
        return token
    return ""


def get_meta_token_info() -> dict:
    """Return non-sensitive token info for debugging."""
    try:
        if "ACCESS_TOKEN" in st.secrets:
            t = str(st.secrets["ACCESS_TOKEN"])
            return {"source": "secrets", "length": len(t), "keys": list(st.secrets.keys()), "error": ""}
        for section in ("general", "secrets", "meta"):
            if section in st.secrets and "ACCESS_TOKEN" in st.secrets[section]:
                t = str(st.secrets[section]["ACCESS_TOKEN"])
                return {"source": f"secrets:{section}", "length": len(t), "keys": list(st.secrets.keys()), "error": ""}
    except Exception:
        token = os.getenv("ACCESS_TOKEN")
        if token:
            return {"source": "env", "length": len(token), "keys": [], "error": "st.secrets 접근 실패"}
        return {"source": "missing", "length": 0, "keys": [], "error": "st.secrets 접근 실패"}
    token = os.getenv("ACCESS_TOKEN")
    if token:
        return {"source": "env", "length": len(token), "keys": list(st.secrets.keys()), "error": ""}
    return {"source": "missing", "length": 0, "keys": list(st.secrets.keys()), "error": ""}


def _get_meta_ad_account_id() -> str:
    try:
        if "META_AD_ACCOUNT_ID" in st.secrets:
            return str(st.secrets["META_AD_ACCOUNT_ID"])
    except Exception:
        pass
    acc = os.getenv("META_AD_ACCOUNT_ID")
    if acc:
        return acc
    return "732978580670026"


def get_meta_token() -> str:
    """Public accessor so every Meta call path can use the same resolved token source."""
    return _get_meta_token()


# Meta 광고계정 ID (환경변수/Secrets 우선)
META_AD_ACCOUNT_ID = _get_meta_ad_account_id()


def _num(v):
    if v is None or v == "":
        return 0.0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _build_meta_df(raw: list[dict], since: str, *, use_breakdowns: bool) -> pd.DataFrame:
    rows = []
    for r in raw:
        date_start = r.get("date_start") or since
        campaign_name = r.get("campaign_name") or r.get("name") or ""
        adset_name = r.get("adset_name") or ""
        ad_name = r.get("ad_name") or r.get("ad_id") or ""

        rows.append({
            "Date": date_start,
            "Campaign": campaign_name,
            "AdGroup": adset_name,
            "Creative_ID": ad_name,
            "Ad_ID": r.get("ad_id") or "",
            "Cost": _num(r.get("spend")),
            "Impressions": _num(r.get("impressions")),
            "Clicks": _num(r.get("clicks")),
            "Conversions": parse_meta_actions(r.get("actions")),
            "Conversion_Value": parse_meta_action_values(r.get("action_values")),
            "Status": "Unknown",
            "Platform": "Meta",
            "Gender": (r.get("gender") or "Unknown") if use_breakdowns else "Unknown",
            "Age": (r.get("age") or "Unknown") if use_breakdowns else "Unknown",
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    return df


def _finalize_meta_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    num_cols = ['Cost', 'Impressions', 'Clicks', 'Conversions', 'Conversion_Value']
    for col in num_cols:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace(',', '').replace('nan', '0')
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    if 'Gender' not in df.columns:
        df['Gender'] = 'Unknown'
    if 'Age' not in df.columns:
        df['Age'] = 'Unknown'
    df['Gender'] = df['Gender'].fillna('Unknown')
    df['Age'] = df['Age'].fillna('Unknown')
    df['Gender'] = df['Gender'].replace({'male': '남성', 'female': '여성', 'Male': '남성', 'Female': '여성'})
    return df


@st.cache_data(ttl=600)
def load_meta_from_api(since: str, until: str, use_breakdowns: bool = False):
    """
    Meta Marketing API로 인사이트 조회 후 앱 형식 DataFrame 반환.
    since/until: YYYY-MM-DD. 캐시 10분.
    breakdowns 실패 시 자동으로 breakdown 없이 재시도.
    """
    token = _get_meta_token()
    if not token:
        return pd.DataFrame()

    try:
        from meta_api import fetch_insights
    except ImportError:
        return pd.DataFrame()

    try:
        from meta_api import fetch_ad_effective_statuses
    except Exception:
        fetch_ad_effective_statuses = None

    raw = []
    try:
        raw = fetch_insights(
            META_AD_ACCOUNT_ID,
            since=since,
            until=until,
            token=token,
            level="ad",
            use_breakdowns=use_breakdowns,
        )
    except Exception:
        if use_breakdowns:
            return pd.DataFrame()
        try:
            raw = fetch_insights(
                META_AD_ACCOUNT_ID, since=since, until=until, token=token, level="ad", use_breakdowns=False
            )
        except Exception as e:
            try:
                st.session_state["meta_api_error"] = str(e)[:300]
            except Exception:
                pass
            return pd.DataFrame()

    if not raw:
        return pd.DataFrame()

    df = _build_meta_df(raw, since, use_breakdowns=use_breakdowns)
    if df.empty:
        return df

    # 최근 7일 내 지출 있는 광고만 상태 조회
    if not use_breakdowns:
        try:
            recent_cutoff = kst_today() - timedelta(days=6)
            df_recent = df[(df["Date"].dt.date >= recent_cutoff) & (df["Cost"] > 0)]
            ad_ids = sorted({str(v) for v in df_recent["Ad_ID"].dropna().tolist() if str(v)})
        except Exception:
            ad_ids = []

        if fetch_ad_effective_statuses and ad_ids:
            try:
                status_map = fetch_ad_effective_statuses(META_AD_ACCOUNT_ID, ad_ids, token=token)
                df["Status"] = df["Ad_ID"].map(status_map).fillna("Unknown")
            except Exception:
                pass

    return _finalize_meta_df(df)


def diagnose_meta_no_data() -> str:
    """
    Meta 데이터가 0건일 때 원인 진단. (원본 _diagnose_meta_no_data를 모듈로 이동)
    """
    load_dotenv(_env_path)
    token = _get_meta_token()
    if not token:
        return "**ACCESS_TOKEN**이 읽히지 않습니다. Streamlit Cloud라면 **Secrets**에 `ACCESS_TOKEN`을 넣었는지 확인하세요. 로컬이면 `.env` 파일명을 다시 확인하세요."
    if token.strip() in ("your_meta_access_token_here", "여기에_토큰_붙여넣기", "paste_token_here"):
        return "**.env**에 아직 예시 값이 들어 있습니다. 실제 토큰으로 바꾼 뒤 **Streamlit을 중지했다가 다시 실행**해 주세요. (브라우저 새로고침만으로는 반영되지 않습니다)"
    def _redact(s: str) -> str:
        if not s:
            return s
        s = s.replace("access_token=", "access_token=REDACTED")
        return s

    try:
        from meta_api import fetch_insights
    except ImportError:
        return "**meta_api** 모듈을 찾을 수 없습니다. (meta_api.py가 app.py와 같은 폴더에 있는지 확인)"

    today = kst_today()
    since = (today - timedelta(days=14)).isoformat()
    until = today.isoformat()
    try:
        raw = fetch_insights(
            META_AD_ACCOUNT_ID, since=since, until=until, token=token, level="ad", use_breakdowns=False
        )
    except Exception as e:
        err = _redact(str(e).strip())
        try:
            st.session_state["meta_api_error"] = err[:300]
        except Exception:
            pass
        if "401" in err or "Unauthorized" in err or "access token" in err.lower():
            return "토큰이 만료되었거나 권한이 없습니다. Graph API Explorer에서 새 토큰을 발급하고 **ads_read** 권한을 체크하세요."
        if "400" in err or "Bad Request" in err:
            if "your_meta_access_token" in err or (token and "your_meta_access_token" in token):
                return "**.env**의 ACCESS_TOKEN이 예시 값(**your_meta_access_token_here**)입니다. Graph API Explorer에서 발급한 **실제 토큰**으로 바꿔 주세요."
            return f"API 요청 형식 오류: {err[:200]}"
        if "403" in err or "Permission" in err.lower():
            return "광고계정 접근 권한이 없습니다. 앱에 **ads_read** 권한이 있는지, 해당 계정이 앱에 연결돼 있는지 확인하세요."
        return f"API 오류: {err[:250]}"

    if not raw:
        return "최근 14일 동안 해당 광고계정에 인사이트 데이터가 없습니다. (계정 ID·기간·실제 광고 집행 여부 확인)"

    return "원인을 특정하지 못했습니다. 터미널 로그를 확인해 보세요."


@st.cache_data(ttl=600)
def load_main_data():
    load_dotenv(_env_path)
    meta_fetched_at = None
    today = kst_today()
    base_since = (today - timedelta(days=14)).isoformat()
    base_until = today.isoformat()
    try:
        df_meta = load_meta_from_api(since=base_since, until=base_until, use_breakdowns=False)
        if df_meta.empty:
            return pd.DataFrame(), None, pd.DataFrame()
        df_meta_demographics = load_meta_from_api(since=base_since, until=base_until, use_breakdowns=True)
        meta_fetched_at = kst_now()
    except Exception:
        return pd.DataFrame(), None, pd.DataFrame()

    return df_meta, meta_fetched_at, df_meta_demographics
