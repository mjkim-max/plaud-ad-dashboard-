from __future__ import annotations

from datetime import datetime
from pathlib import Path

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
    "action_date",
    "creative_id",
    "creative_key",
    "campaign",
    "adgroup",
    "action",
    "note",
    "author",
    "updated_at",
]


def _store_path() -> Path:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "creative_actions.csv"


def _get_sheet():
    if st is None or gspread is None or Credentials is None:
        return None
    try:
        cfg = st.secrets.get("google_sheets", {})
        sa = st.secrets.get("google_sheets_service_account", {})
    except Exception:
        return None
    sheet_id = cfg.get("sheet_id") or cfg.get("spreadsheet_id") or "1REfuppqzLN0Y3jmkPrDXKNm_btaA-qtlbaO2bx9MSh8"
    worksheet = cfg.get("worksheet", "광고성과관리")
    if not sheet_id or not sa:
        return None
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(dict(sa), scopes=scopes)
    client = gspread.authorize(creds)
    try:
        ss = client.open_by_key(sheet_id)
        return ss.worksheet(worksheet)
    except Exception as e:
        try:
            st.session_state["sheet_error"] = str(e)
        except Exception:
            pass
        return None


def _sheet_to_df(ws) -> pd.DataFrame:
    values = ws.get_all_values()
    if not values:
        return pd.DataFrame(columns=_COLUMNS)
    header = values[0]
    # If header doesn't match expected, treat all rows as data
    if header != _COLUMNS:
        data_rows = values
    else:
        data_rows = values[1:]
    cleaned = []
    for row in data_rows:
        r = list(row)[:len(_COLUMNS)]
        if len(r) < len(_COLUMNS):
            r += [""] * (len(_COLUMNS) - len(r))
        cleaned.append(r)
    return pd.DataFrame(cleaned, columns=_COLUMNS)


def _ensure_sheet_header(ws) -> None:
    existing = ws.get_all_values()
    if not existing:
        ws.append_row(_COLUMNS)
        return
    if existing[0] != _COLUMNS:
        ws.insert_row(_COLUMNS, index=1)


def load_actions() -> pd.DataFrame:
    ws = _get_sheet()
    if ws is not None:
        try:
            _ensure_sheet_header(ws)
            df = _sheet_to_df(ws)
            # Backfill creative_key if missing/empty
            if "creative_key" in df.columns:
                for i, row in df.iterrows():
                    if not str(row.get("creative_key", "")).strip():
                        cid = str(row.get("creative_id", "")).strip()
                        camp = str(row.get("campaign", "")).strip()
                        adg = str(row.get("adgroup", "")).strip()
                        df.at[i, "creative_key"] = cid if cid else f"{camp}|{adg}"
            return df
        except Exception:
            return pd.DataFrame(columns=_COLUMNS)
    path = _store_path()
    if not path.exists():
        return pd.DataFrame(columns=_COLUMNS)
    df = pd.read_csv(path)
    for col in _COLUMNS:
        if col not in df.columns:
            df[col] = ""
    return df[_COLUMNS]


def upsert_action(
    *,
    action_date: str,
    creative_id: str,
    creative_key: str,
    campaign: str,
    adgroup: str,
    action: str,
    note: str,
    author: str,
) -> None:
    ws = _get_sheet()
    if ws is not None:
        _ensure_sheet_header(ws)
        df = _sheet_to_df(ws)
        mask = (df["action_date"] == action_date) & (df["creative_key"] == creative_key)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if mask.any():
            idx = df[mask].index[0]
            row_idx = idx + 2  # 1-based + header
            values = [
                action_date,
                creative_id,
                creative_key,
                campaign,
                adgroup,
                action,
                note,
                author,
                now,
            ]
            ws.update(f"A{row_idx}:I{row_idx}", [values])
        else:
            ws.append_row([
                action_date,
                creative_id,
                creative_key,
                campaign,
                adgroup,
                action,
                note,
                author,
                now,
            ])
        return

    df = load_actions()
    mask = (df["action_date"] == action_date) & (df["creative_key"] == creative_key)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if mask.any():
        df.loc[mask, ["creative_id", "campaign", "adgroup", "action", "note", "author", "updated_at"]] = [
            creative_id,
            campaign,
            adgroup,
            action,
            note,
            author,
            now,
        ]
    else:
        df = pd.concat(
            [
                df,
                pd.DataFrame(
                    [
                        {
                            "action_date": action_date,
                            "creative_id": creative_id,
                            "creative_key": creative_key,
                            "campaign": campaign,
                            "adgroup": adgroup,
                            "action": action,
                            "note": note,
                            "author": author,
                            "updated_at": now,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
    df.to_csv(_store_path(), index=False)


def delete_action(*, action_date: str, creative_key: str) -> None:
    ws = _get_sheet()
    if ws is not None:
        df = _sheet_to_df(ws)
        mask = (df["action_date"] == action_date) & (df["creative_key"] == creative_key)
        if mask.any():
            row_idx = df[mask].index[0] + 2
            ws.delete_rows(row_idx)
        return

    df = load_actions()
    mask = (df["action_date"] == action_date) & (df["creative_key"] == creative_key)
    df = df[~mask]
    df.to_csv(_store_path(), index=False)
