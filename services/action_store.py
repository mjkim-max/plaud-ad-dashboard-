from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd


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


def load_actions() -> pd.DataFrame:
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
    df = load_actions()
    mask = (df["action_date"] == action_date) & (df["creative_key"] == creative_key)
    df = df[~mask]
    df.to_csv(_store_path(), index=False)
