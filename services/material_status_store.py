from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

try:
    import streamlit as st
except Exception:
    st = None
try:
    import gspread
except Exception:
    gspread = None
try:
    from google.oauth2.service_account import Credentials
except Exception:
    Credentials = None


_COLUMNS = [
    "platform",
    "campaign",
    "adgroup",
    "material_name",
    "status",
    "last_seen_date",
    "updated_at",
]


def _local_path() -> Path:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "material_statuses.csv"


def _get_sheet():
    if st is None or gspread is None or Credentials is None:
        return None
    try:
        cfg = st.secrets.get("google_sheets", {})
        sa = st.secrets.get("google_sheets_service_account", {})
    except Exception:
        return None
    sheet_id = cfg.get("sheet_id") or cfg.get("spreadsheet_id") or "1REfuppqzLN0Y3jmkPrDXKNm_btaA-qtlbaO2bx9MSh8"
    worksheet = cfg.get("material_status_worksheet", "소재상태")
    if not sheet_id or not sa:
        return None

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(dict(sa), scopes=scopes)
    client = gspread.authorize(creds)
    try:
        ss = client.open_by_key(sheet_id)
        try:
            return ss.worksheet(worksheet)
        except Exception:
            return ss.add_worksheet(title=worksheet, rows=2000, cols=20)
    except Exception as e:
        try:
            st.session_state["sheet_error"] = str(e)
        except Exception:
            pass
        return None


def _ensure_header(ws) -> None:
    values = ws.get_all_values()
    if not values:
        ws.append_row(_COLUMNS)
        return
    if values[0] != _COLUMNS:
        ws.clear()
        ws.append_row(_COLUMNS)


def _sheet_to_df(ws) -> pd.DataFrame:
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(columns=_COLUMNS)
    header = values[0]
    data_rows = values[1:] if header == _COLUMNS else values
    cleaned = []
    for row in data_rows:
        r = list(row)[:len(_COLUMNS)]
        if len(r) < len(_COLUMNS):
            r += [""] * (len(_COLUMNS) - len(r))
        cleaned.append(r)
    return pd.DataFrame(cleaned, columns=_COLUMNS)


def load_material_statuses() -> pd.DataFrame:
    ws = _get_sheet()
    if ws is not None:
        try:
            _ensure_header(ws)
            return _sheet_to_df(ws)
        except Exception:
            return pd.DataFrame(columns=_COLUMNS)

    path = _local_path()
    if not path.exists():
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.read_csv(path)
    for c in _COLUMNS:
        if c not in df.columns:
            df[c] = ""
    return df[_COLUMNS]


def save_material_statuses(df: pd.DataFrame) -> int:
    if df is None:
        df = pd.DataFrame(columns=_COLUMNS)

    work = df.copy()
    for c in _COLUMNS:
        if c not in work.columns:
            work[c] = ""
    work = work[_COLUMNS].fillna("")
    if "updated_at" not in work.columns:
        work["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    ws = _get_sheet()
    if ws is not None:
        try:
            _ensure_header(ws)
            rows = [_COLUMNS] + work.astype(str).values.tolist()
            ws.clear()
            ws.update("A1", rows)
            return len(work)
        except Exception:
            pass

    path = _local_path()
    work.to_csv(path, index=False)
    return len(work)
