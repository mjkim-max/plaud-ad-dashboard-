from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd


_TABLE = "meta_video_daily"
_COLUMNS = [
    "snapshot_date",
    "video_key",
    "video_id",
    "video_url",
    "material_name",
    "campaign",
    "adgroup",
    "ad_id",
    "status",
    "cost",
    "conversion_value",
    "roas",
]


def _db_path() -> Path:
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "video_materials.db"


def _init_db(path: Path) -> None:
    with sqlite3.connect(path) as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                snapshot_date TEXT NOT NULL,
                video_key TEXT NOT NULL,
                video_id TEXT,
                video_url TEXT,
                material_name TEXT,
                campaign TEXT,
                adgroup TEXT,
                ad_id TEXT NOT NULL,
                status TEXT,
                cost REAL DEFAULT 0,
                conversion_value REAL DEFAULT 0,
                roas REAL DEFAULT 0,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (snapshot_date, ad_id, video_key)
            )
            """
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_video_key ON {_TABLE} (video_key)"
        )
        conn.execute(
            f"CREATE INDEX IF NOT EXISTS idx_{_TABLE}_snapshot_date ON {_TABLE} (snapshot_date)"
        )
        conn.commit()


def upsert_meta_video_daily(df: pd.DataFrame, db_path: Optional[str] = None) -> int:
    if df is None or df.empty:
        return 0

    path = Path(db_path) if db_path else _db_path()
    _init_db(path)

    work = df.copy()
    for col in _COLUMNS:
        if col not in work.columns:
            work[col] = ""

    work["snapshot_date"] = pd.to_datetime(work["snapshot_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    work["cost"] = pd.to_numeric(work["cost"], errors="coerce").fillna(0.0)
    work["conversion_value"] = pd.to_numeric(work["conversion_value"], errors="coerce").fillna(0.0)
    work["roas"] = pd.to_numeric(work["roas"], errors="coerce").fillna(0.0)
    work["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    rows = []
    for _, r in work.iterrows():
        if not str(r.get("snapshot_date", "")).strip():
            continue
        ad_id = str(r.get("ad_id", "")).strip()
        video_key = str(r.get("video_key", "")).strip()
        if not ad_id or not video_key:
            continue
        rows.append(
            (
                str(r.get("snapshot_date", "")),
                video_key,
                str(r.get("video_id", "")),
                str(r.get("video_url", "")),
                str(r.get("material_name", "")),
                str(r.get("campaign", "")),
                str(r.get("adgroup", "")),
                ad_id,
                str(r.get("status", "")),
                float(r.get("cost", 0.0) or 0.0),
                float(r.get("conversion_value", 0.0) or 0.0),
                float(r.get("roas", 0.0) or 0.0),
                str(r.get("updated_at", "")),
            )
        )

    if not rows:
        return 0

    with sqlite3.connect(path) as conn:
        conn.executemany(
            f"""
            INSERT OR REPLACE INTO {_TABLE} (
                snapshot_date, video_key, video_id, video_url, material_name,
                campaign, adgroup, ad_id, status, cost, conversion_value, roas, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    return len(rows)


def load_meta_video_daily(days: int = 180, db_path: Optional[str] = None) -> pd.DataFrame:
    path = Path(db_path) if db_path else _db_path()
    _init_db(path)

    query = f"""
        SELECT snapshot_date, video_key, video_id, video_url, material_name,
               campaign, adgroup, ad_id, status, cost, conversion_value, roas
        FROM {_TABLE}
    """
    params = []
    if days and days > 0:
        since = (datetime.now().date() - timedelta(days=days - 1)).isoformat()
        query += " WHERE snapshot_date >= ?"
        params.append(since)
    query += " ORDER BY snapshot_date DESC, video_key ASC"

    with sqlite3.connect(path) as conn:
        df = pd.read_sql_query(query, conn, params=params)

    if df.empty:
        return df

    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"], errors="coerce")
    for col in ("cost", "conversion_value", "roas"):
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    return df
