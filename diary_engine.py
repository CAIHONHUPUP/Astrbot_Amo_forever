# -*- coding: utf-8 -*-
"""大肥鱼的日记：每天一篇 txt，按 年 / 月 / 日 文件夹存放。

目录结构：
    日记根目录/
        2026/
            11/
                08/
                    我的日记2026年11月08日.txt

文件第一行是标题「我的日记YYYY年MM月DD日」，空一行后是正文。
这里只负责落盘、读取和目录汇总，不碰人格和模型；生成在 amo 主插件里。
"""

from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

DEFAULT_DIR = r"D:\dafeiyu\日记"
TITLE_PREFIX = "我的日记"
_FILE_RE = re.compile(r"^我的日记(\d{4})年(\d{2})月(\d{2})日\.txt$")


def parse_day(value: Any) -> Optional[date]:
    """把 '2026-11-08' / '2026/11/8' / date / datetime 统一成 date。"""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    text = text.replace("/", "-").replace(".", "-").replace("年", "-").replace("月", "-").replace("日", "")
    parts = [part for part in text.split("-") if part]
    if len(parts) != 3:
        return None
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (TypeError, ValueError):
        return None


def day_str(day: date) -> str:
    return day.strftime("%Y-%m-%d")


def title_for(day: date) -> str:
    return "%s%d年%02d月%02d日" % (TITLE_PREFIX, day.year, day.month, day.day)


def diary_root(root: str = "") -> str:
    return str(root or DEFAULT_DIR)


def diary_path(root: str, day: date) -> str:
    base = diary_root(root)
    return os.path.join(
        base, "%04d" % day.year, "%02d" % day.month, "%02d" % day.day,
        "%s.txt" % title_for(day),
    )


def write_diary(root: str, day: date, text: str) -> str:
    """写入一天的日记（原子替换），返回文件路径。"""
    body = str(text or "").strip()
    path = diary_path(root, day)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    content = title_for(day) + "\n\n" + body + "\n"
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(content)
    os.replace(tmp, path)
    return path


def read_diary(root: str, day: date) -> str:
    path = diary_path(root, day)
    try:
        with open(path, "r", encoding="utf-8") as fp:
            return fp.read()
    except OSError:
        return ""


def list_tree(root: str) -> Dict[str, Any]:
    """按 年 → 月 → 日 汇总已写的日记。"""
    base = diary_root(root)
    years: List[Dict[str, Any]] = []
    total = 0
    latest = ""
    try:
        names = os.listdir(base)
    except OSError:
        names = []
    for year_name in sorted([n for n in names if re.match(r"^\d{4}$", n)], reverse=True):
        year_dir = os.path.join(base, year_name)
        if not os.path.isdir(year_dir):
            continue
        months: List[Dict[str, Any]] = []
        for month_name in sorted([n for n in os.listdir(year_dir) if re.match(r"^\d{2}$", n)], reverse=True):
            month_dir = os.path.join(year_dir, month_name)
            if not os.path.isdir(month_dir):
                continue
            days: List[Dict[str, Any]] = []
            for day_name in sorted([n for n in os.listdir(month_dir) if re.match(r"^\d{2}$", n)], reverse=True):
                day_dir = os.path.join(month_dir, day_name)
                if not os.path.isdir(day_dir):
                    continue
                for file_name in sorted(os.listdir(day_dir), reverse=True):
                    match = _FILE_RE.match(file_name)
                    if not match:
                        continue
                    path = os.path.join(day_dir, file_name)
                    try:
                        size = os.path.getsize(path)
                        with open(path, "r", encoding="utf-8") as fp:
                            text = fp.read()
                    except OSError:
                        continue
                    total += 1
                    day_text = day_str(date(int(match.group(1)), int(match.group(2)), int(match.group(3))))
                    if day_text > latest:
                        latest = day_text
                    days.append({
                        "date": day_text,
                        "day": int(match.group(3)),
                        "title": title_for(date(int(match.group(1)), int(match.group(2)), int(match.group(3)))),
                        "chars": len(text),
                        "size": size,
                        "path": path,
                    })
            if days:
                months.append({"month": int(month_name), "days": days})
        if months:
            years.append({"year": int(year_name), "months": months})
    return {"total": total, "latest": latest, "years": years, "root": base}


def stats(root: str) -> Dict[str, Any]:
    tree = list_tree(root)
    return {"total": tree["total"], "latest": tree["latest"], "root": tree["root"]}


def recent_days(root: str, limit: int = 30) -> List[date]:
    """最近已经写过的日期（从新到旧），给面板显示用。"""
    tree = list_tree(root)
    out: List[date] = []
    for year in tree["years"]:
        for month in year["months"]:
            for day in month["days"]:
                parsed = parse_day(day["date"])
                if parsed:
                    out.append(parsed)
    return out[:max(1, int(limit))]
