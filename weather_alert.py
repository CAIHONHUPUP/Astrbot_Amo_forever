# -*- coding: utf-8 -*-
"""明天天气变坏时的提醒文案（纯逻辑，无 astrbot 依赖，便于单测）。"""

from __future__ import annotations

from typing import List, Optional

THUNDER_WORDS = ("雷", "冰雹")
SNOW_WORDS = ("雪", "冻雨")
RAIN_WORDS = ("雨",)

FIELDS = ("fxDate", "textDay", "textNight", "tempMax", "tempMin")


def parse_daily(payload: Optional[dict]) -> List[dict]:
    """把和风 /v7/weather/{n}d 的响应整理成按日期排列的列表。"""
    daily = (payload or {}).get("daily")
    if not isinstance(daily, list):
        return []
    items = []
    for row in daily:
        if not isinstance(row, dict):
            continue
        item = {key: str(row.get(key) or "") for key in FIELDS}
        if not item["fxDate"]:
            continue
        items.append(item)
    items.sort(key=lambda x: x["fxDate"])
    return items


def _day_text(day: dict) -> str:
    parts = [str((day or {}).get("textDay") or ""), str((day or {}).get("textNight") or "")]
    return " ".join(part for part in parts if part)


def _to_int(value) -> Optional[int]:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def evaluate(day_today: Optional[dict], day_tomorrow: Optional[dict], min_temp_drop: int = 8) -> str:
    """明天的天气变坏就返回一句提醒；正常返回空串。

    day_* 来自 parse_daily()，至少要有 textDay / textNight / tempMax。
    """
    tomorrow_text = _day_text(day_tomorrow or {})
    if not tomorrow_text:
        return ""

    parts = []
    if any(word in tomorrow_text for word in THUNDER_WORDS):
        parts.append("明天雷雨，别在外面乱跑")
    elif any(word in tomorrow_text for word in SNOW_WORDS):
        parts.append("明天有雪，路滑，慢点走")
    elif any(word in tomorrow_text for word in RAIN_WORDS):
        parts.append("明天有雨，伞别忘了")

    today_max = _to_int((day_today or {}).get("tempMax"))
    tomorrow_max = _to_int((day_tomorrow or {}).get("tempMax"))
    if today_max is not None and tomorrow_max is not None:
        drop = today_max - tomorrow_max
        if drop >= max(1, int(min_temp_drop)):
            parts.append("明天降温 %d 度，多穿件衣服" % drop)

    if not parts:
        return ""
    return "；".join(parts) + "。"
