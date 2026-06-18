from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


KST = ZoneInfo("Asia/Seoul")


def kst_now() -> datetime:
    return datetime.now(KST)


def kst_today() -> date:
    return kst_now().date()
