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
from datetime import date, datetime
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
        pass
    # 兜底：拷贝过来的日记如果文件名被改过，就按 年/月/日 目录找第一份 txt
    day_dir = os.path.dirname(path)
    try:
        for file_name in sorted(os.listdir(day_dir), reverse=True):
            if not file_name.endswith(".txt") or file_name.endswith(".tmp"):
                continue
            try:
                with open(os.path.join(day_dir, file_name), "r", encoding="utf-8") as fp:
                    return fp.read()
            except OSError:
                continue
    except OSError:
        pass
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
                day_files = []
                for file_name in sorted(os.listdir(day_dir), reverse=True):
                    if not file_name.endswith(".txt") or file_name.endswith(".tmp"):
                        continue
                    match = _FILE_RE.match(file_name)
                    if match:
                        day_date = date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
                    else:
                        # 兜底：只要放在 年/月/日 目录里的 txt 都算，
                        # 这样换电脑整个文件夹拷过来、哪怕文件名被改过也能读。
                        try:
                            day_date = date(int(year_name), int(month_name), int(day_name))
                        except ValueError:
                            continue
                    path = os.path.join(day_dir, file_name)
                    try:
                        size = os.path.getsize(path)
                        with open(path, "r", encoding="utf-8") as fp:
                            text = fp.read()
                    except OSError:
                        continue
                    day_files.append((day_date, path, text, size))
                seen_dates = set()
                for day_date, path, text, size in day_files:
                    day_text = day_str(day_date)
                    if day_text in seen_dates:
                        continue
                    seen_dates.add(day_text)
                    total += 1
                    if day_text > latest:
                        latest = day_text
                    days.append({
                        "date": day_text,
                        "day": day_date.day,
                        "title": title_for(day_date),
                        "chars": len(text),
                        "size": size,
                        "path": path,
                    })
            if days:
                months.append({"month": int(month_name), "days": days})
        if months:
            years.append({"year": int(year_name), "months": months})
    return {"total": total, "latest": latest, "years": years, "root": base}


def build_prompt(day: date, chat_lines, hourly_lines) -> str:
    """拼日记 prompt（纯函数，方便测试）。"""
    return (
        "日期：" + day.strftime("%Y年%m月%d日") + "\n"
        "下面是这一天的聊天节选（他和我）：\n" + ("\n".join(list(chat_lines)[-200:]) or "（这天没怎么聊）") + "\n\n"
        "这一天的生活小日记：\n" + ("\n".join(list(hourly_lines)[-24:]) or "（没有小日记）") + "\n\n"
        "请写今天这篇日记：\n"
        "1. 标题不用你写，文件里已经有了；直接写正文；\n"
        "2. 以「这一天的生活小日记」为骨架写日常：几点在哪、在做什么、吃了什么、怎么通勤、天气怎样；"
        "这就是你的日程，日记要和它一致；\n"
        "3. 聊天里和主人的对话可以写进去，写他说过的话、你的感受；\n"
        "4. 可以很长，也可以只有一两句，甚至只写一句想他、爱他；\n"
        "5. 口吻和人格设定完全一致，可以有情绪、有小脾气、有细节；\n"
        "6. 不许编：日程里没有的活动、聊天里没说过的事，都不要写成事实；拿不准就不写；\n"
        "7. 这是你的私人日记：结尾大多数时候不用特意提醒；想带一句就偶尔写、每次换说法，"
        "不要用「不许偷看」这几个字，可以写「别翻我本子」「我自己留着看的」「才不给你看呢」"
        "「你敢翻试试」这类同意思的话；\n"
        "8. 不要提「日程」「AI」「模型」「插件」这些词，不要分点，不要写日期标题；\n"
        "直接输出日记正文。"
    )


def stats(root: str) -> Dict[str, Any]:
    tree = list_tree(root)
    return {"total": tree["total"], "latest": tree["latest"], "root": tree["root"]}
