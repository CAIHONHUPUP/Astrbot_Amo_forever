# -*- coding: utf-8 -*-
"""
我想永远陪着你 / 我想永远陪伴你 4.4.6
一个尽量“像人”的 AstrBot 智械人类核心：
生理期 / 九维心情 / 世界观与日程 / 天气 / 健康 / 群聊插话阈值 /
私聊判定 / 主动私聊 / 长期记忆与遗忘 / 防抖 / 分段与打字延迟 / 引用回复 / AI 润色
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import math
import os
import random
import re
import sqlite3
import threading
import time
from datetime import date, datetime, timedelta

try:
    import astrbot.api.message_components as Comp
except Exception:
    Comp = None

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star

try:
    from astrbot.api.event import MessageChain
except Exception:
    try:
        from astrbot.core.message.message_event_result import MessageChain
    except Exception:
        MessageChain = None

try:
    from astrbot.api.web import request as web_request
except Exception:
    try:
        from quart import request as web_request
    except Exception:
        web_request = None

try:
    from astrbot.core.agent.message import TextPart
except Exception:
    TextPart = None

try:
    from .heartflow_engine import HeartflowEngine
    from .segment_engine import SegmentEngine
except Exception:
    try:
        from heartflow_engine import HeartflowEngine
        from segment_engine import SegmentEngine
    except Exception:
        HeartflowEngine = None
        SegmentEngine = None
        try:
            import importlib.util
            _engine_dir = os.path.dirname(os.path.abspath(__file__))
            def _load_engine(module_name, class_name):
                _spec = importlib.util.spec_from_file_location(
                    "amo_" + module_name,
                    os.path.join(_engine_dir, module_name + ".py"),
                )
                _module = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_module)
                return getattr(_module, class_name)
            HeartflowEngine = _load_engine("heartflow_engine", "HeartflowEngine")
            SegmentEngine = _load_engine("segment_engine", "SegmentEngine")
        except Exception as _engine_exc:
            logger.error("[amo] 内置心流/分段模块加载失败: %s" % _engine_exc)


PLUGIN_NAME = "Astrbot_Amo_forever"
PLUGIN_VERSION = "4.4.6"
DEFAULT_ADMIN = ""
LEGACY_DEFAULT_ADMIN = "3261748099"
LEGACY_MEMORY_PLUGIN = "astrbot_plugin_private_companion"

RELATIONS = ("仇恨", "抵触", "普通", "熟识", "相恋")
SCHEDULE_VERSION = "human-v4"
NETWORK_RELATIONS = ("家人", "恋人", "朋友", "同事", "同学", "熟人", "陌生人", "仇人")
MOOD_KEYS = ("开心", "平静", "郁闷", "生气", "暴躁", "委屈", "疲惫", "焦虑", "兴奋", "依恋")
MOOD_BASE = {
    "开心": 55, "平静": 60, "郁闷": 18, "生气": 8, "暴躁": 6, "委屈": 20,
    "疲惫": 28, "焦虑": 18, "兴奋": 30, "依恋": 45,
}
STYLE_HINTS = {
    "soft": "整体语气温柔、软一点。",
    "cool": "整体语气清淡、克制一点。",
    "lively": "整体语气活泼、有精神。",
    "mature": "整体语气成熟、稳一点。",
}

POS_WORDS = ("开心", "高兴", "哈哈", "笑死", "好耶", "喜欢", "爱你", "可爱", "棒", "不错",
             "太好了", "谢谢", "嘿嘿", "嘻嘻", "么么", "抱抱", "亲亲", "好吃", "好看")
NEG_WORDS = ("难过", "伤心", "哭", "烦", "累", "讨厌", "滚", "闭嘴", "无语", "失望",
             "委屈", "孤单", "想死", "崩溃", "气死", "不开心")
ANGRY_WORDS = ("滚", "闭嘴", "傻", "废物", "烦死", "气死", "去死", "恶心", "别烦", "有病")
SAD_WORDS = ("难过", "伤心", "想哭", "委屈", "孤单", "没人", "算了", "失望", "哭")
AFFECTION_WORDS = ("喜欢", "爱你", "想你", "抱抱", "亲亲", "贴贴", "宝贝", "老婆", "宝宝", "么么")
INSULT_WORDS = ("傻逼", "智障", "废物", "垃圾", "去死", "恶心", "滚")
STOP_NAMES = {"学生", "上班族", "男孩子", "女孩子", "男生", "女生", "人", "谁", "你的",
              "我", "你", "他", "她", "一个", "一只", "这里", "那儿", "好人", "坏人"}


# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------

def now_ts():
    return time.time()


CN_HOLIDAYS = {
    "2025-01-01": "元旦",
    "2025-01-28": "除夕", "2025-01-29": "春节", "2025-01-30": "春节", "2025-01-31": "春节", "2025-02-01": "春节", "2025-02-02": "春节", "2025-02-03": "春节", "2025-02-04": "春节",
    "2025-04-04": "清明",
    "2025-05-01": "劳动节",
    "2025-05-31": "端午",
    "2025-10-01": "国庆", "2025-10-02": "国庆", "2025-10-03": "国庆", "2025-10-04": "国庆", "2025-10-05": "国庆", "2025-10-06": "国庆", "2025-10-07": "国庆", "2025-10-08": "国庆",
    "2025-10-06": "中秋",
    "2026-01-01": "元旦",
    "2026-02-16": "除夕", "2026-02-17": "春节", "2026-02-18": "春节", "2026-02-19": "春节", "2026-02-20": "春节", "2026-02-21": "春节", "2026-02-22": "春节", "2026-02-23": "春节",
    "2026-04-05": "清明",
    "2026-05-01": "劳动节",
    "2026-06-19": "端午",
    "2026-09-25": "中秋",
    "2026-10-01": "国庆", "2026-10-02": "国庆", "2026-10-03": "国庆", "2026-10-04": "国庆", "2026-10-05": "国庆", "2026-10-06": "国庆", "2026-10-07": "国庆",
    "2027-01-01": "元旦",
    "2027-02-05": "除夕", "2027-02-06": "春节", "2027-02-07": "春节", "2027-02-08": "春节", "2027-02-09": "春节", "2027-02-10": "春节", "2027-02-11": "春节",
    "2027-04-05": "清明",
    "2027-05-01": "劳动节",
    "2027-06-09": "端午",
    "2027-09-15": "中秋",
    "2027-10-01": "国庆", "2027-10-02": "国庆", "2027-10-03": "国庆", "2027-10-04": "国庆", "2027-10-05": "国庆", "2027-10-06": "国庆", "2027-10-07": "国庆",
}

# 2026 年主要假期的连续日期（用于判断长假/短假）
for _d in range(1, 4):
    CN_HOLIDAYS.setdefault("2026-01-%02d" % _d, "元旦")
for _d in range(4, 7):
    CN_HOLIDAYS.setdefault("2026-04-%02d" % _d, "清明")
for _d in range(1, 6):
    CN_HOLIDAYS.setdefault("2026-05-%02d" % _d, "劳动节")
for _d in range(19, 22):
    CN_HOLIDAYS.setdefault("2026-06-%02d" % _d, "端午")
for _d in range(25, 28):
    CN_HOLIDAYS.setdefault("2026-09-%02d" % _d, "中秋")

SOLAR_TERMS = {
    "2025-01-05": "小寒", "2025-01-20": "大寒", "2025-02-03": "立春", "2025-02-18": "雨水", "2025-03-05": "惊蛰", "2025-03-20": "春分", "2025-04-04": "清明", "2025-04-20": "谷雨", "2025-05-05": "立夏", "2025-05-21": "小满", "2025-06-05": "芒种", "2025-06-21": "夏至", "2025-07-07": "小暑", "2025-07-22": "大暑", "2025-08-07": "立秋", "2025-08-23": "处暑", "2025-09-07": "白露", "2025-09-23": "秋分", "2025-10-08": "寒露", "2025-10-23": "霜降", "2025-11-07": "立冬", "2025-11-22": "小雪", "2025-12-07": "大雪", "2025-12-21": "冬至",
    "2026-01-05": "小寒", "2026-01-20": "大寒", "2026-02-04": "立春", "2026-02-18": "雨水", "2026-03-05": "惊蛰", "2026-03-20": "春分", "2026-04-05": "清明", "2026-04-20": "谷雨", "2026-05-05": "立夏", "2026-05-21": "小满", "2026-06-05": "芒种", "2026-06-21": "夏至", "2026-07-07": "小暑", "2026-07-23": "大暑", "2026-08-07": "立秋", "2026-08-23": "处暑", "2026-09-07": "白露", "2026-09-23": "秋分", "2026-10-08": "寒露", "2026-10-23": "霜降", "2026-11-07": "立冬", "2026-11-22": "小雪", "2026-12-07": "大雪", "2026-12-21": "冬至",
    "2027-01-05": "小寒", "2027-01-20": "大寒", "2027-02-04": "立春", "2027-02-19": "雨水", "2027-03-06": "惊蛰", "2027-03-21": "春分", "2027-04-05": "清明", "2027-04-20": "谷雨", "2027-05-06": "立夏", "2027-05-21": "小满", "2027-06-06": "芒种", "2027-06-21": "夏至", "2027-07-07": "小暑", "2027-07-23": "大暑", "2027-08-08": "立秋", "2027-08-23": "处暑", "2027-09-08": "白露", "2027-09-23": "秋分", "2027-10-08": "寒露", "2027-10-24": "霜降", "2027-11-08": "立冬", "2027-11-22": "小雪", "2027-12-07": "大雪", "2027-12-22": "冬至",
}


def day_meta(day=None):
    """返回某天的节日、节气和是否休息日。"""
    try:
        target = date.fromisoformat(str(day)) if day else date.today()
    except Exception:
        target = date.today()
    key = target.isoformat()
    holiday = CN_HOLIDAYS.get(key, "")
    term = SOLAR_TERMS.get(key, "")
    weekend = target.weekday() >= 5
    rest = bool(weekend or holiday)
    holiday_days = 0
    if holiday:
        cursor = target
        while CN_HOLIDAYS.get(cursor.isoformat()) == holiday:
            holiday_days += 1
            cursor -= timedelta(days=1)
        cursor = target + timedelta(days=1)
        while CN_HOLIDAYS.get(cursor.isoformat()) == holiday:
            holiday_days += 1
            cursor += timedelta(days=1)
    label = "、".join(item for item in (holiday, term) if item)
    if holiday_days >= 2:
        label += (" · " if label else "") + "%d天假期" % holiday_days
    if not label and weekend:
        label = "周末"
    return {
        "date": key,
        "weekday": "一二三四五六日"[target.weekday()],
        "weekend": weekend,
        "holiday": holiday,
        "solar_term": term,
        "holiday_days": holiday_days,
        "rest": rest,
        "label": label,
    }

def today_str():
    return date.today().isoformat()


def weekday_cn():
    return "一二三四五六日"[date.today().weekday()]


def clamp(value, low=0.0, high=100.0):
    try:
        value = float(value)
    except Exception:
        return float(low)
    return max(float(low), min(float(high), value))


def to_int(value, default=0):
    try:
        return int(float(value))
    except Exception:
        return default


def to_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return default


def truncate(text, limit=120):
    text = str(text or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def md5_int(text):
    return int(hashlib.md5(str(text).encode("utf-8")).hexdigest()[:8], 16)


def uniq(items):
    out = []
    seen = set()
    for item in items:
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def parse_hhmm(value, default=0):
    try:
        parts = str(value).strip().split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return default


def minutes_now():
    dt = datetime.now()
    return dt.hour * 60 + dt.minute


def in_minute_range(cur, start, end):
    if start == end:
        return True
    if start < end:
        return start <= cur < end
    return cur >= start or cur < end


def quiet_now(spec):
    try:
        start, end = str(spec).split("-", 1)
        return in_minute_range(minutes_now(), parse_hhmm(start), parse_hhmm(end))
    except Exception:
        return False


def looks_like_plain_command(text):
    text = (text or "").strip()
    return text.startswith("/") or text.startswith("／")


def has_question(text):
    if "?" in text or "？" in text:
        return True
    return any(word in text for word in (
        "吗", "呢", "怎么", "为什么", "啥", "什么", "哪", "多少", "几",
        "是不是", "能不能", "可不可以", "如何", "几点", "谁",
    ))


def sentiment(text):
    text = text or ""
    pos = sum(1 for word in POS_WORDS if word in text)
    neg = sum(1 for word in NEG_WORDS if word in text)
    angry = sum(1 for word in ANGRY_WORDS if word in text)
    sad = sum(1 for word in SAD_WORDS if word in text)
    aff = sum(1 for word in AFFECTION_WORDS if word in text)
    total = pos + neg
    score = 0.0 if total == 0 else (pos - neg) / float(total)
    return {
        "pos": pos, "neg": neg, "angry": angry, "sad": sad,
        "aff": aff, "insult": any(w in text for w in INSULT_WORDS),
        "score": score,
    }


_WORD_RE = re.compile(r"[a-zA-Z0-9_]{2,}")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")


def tokens(text):
    text = (text or "").lower()
    out = set()
    for word in _WORD_RE.findall(text):
        out.add(word)
    for run in _CJK_RE.findall(text):
        if len(run) == 1:
            out.add(run)
        for i in range(len(run) - 1):
            out.add(run[i:i + 2])
        for i in range(len(run) - 2):
            out.add(run[i:i + 3])
    return out


def overlap(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / float(max(1, min(len(a), len(b))))


def json_extract(text):
    if not text:
        return None
    raw = str(text).strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = raw.find(opener)
        if start < 0:
            continue
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(raw)):
            char = raw[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    chunk = raw[start:index + 1]
                    chunk = re.sub(r",\s*([}\]])", r"\1", chunk)
                    try:
                        return json.loads(chunk)
                    except Exception:
                        break
    return None


CHAT_FORMAT_NOISE = re.compile(
    r"@\s*([^\s（(]+)\s*[（(]\s*QQ\s*[:：]?\s*\d+\s*[）)]"
    r"|[（(]\s*QQ\s*[:：]?\s*\d+\s*[）)]"
    r"|\bQQ\s*[:：]?\s*\d{4,}\b"
    r"|@\s*([^\s，。！？!?、；;：:]+)",
    re.I,
)


def strip_chat_format(text):
    """去掉模型复述的 @昵称(QQ号)、QQ号等后台格式，保留自然称呼。"""
    value = str(text or "")
    value = CHAT_FORMAT_NOISE.sub(lambda m: (m.group(1) or m.group(2) or "").strip(), value)
    value = re.sub(r"[（(]\s*[）)]", "", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    return value.strip()


def clean_reply(text, limit=300):
    if not text:
        return ""
    text = strip_chat_format(str(text).strip())
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = re.sub(r"^(?:Amo|amo|核心|我|助手|assistant|AI|机器人)\s*[:：]\s*", "", text)
    if len(text) >= 2 and text[0] in "\"'“‘" and text[-1] in "\"'”’":
        text = text[1:-1]
    text = text.replace("\r", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:limit]


def _clean_fact_value(value):
    value = re.sub(r"[，。！？!?~～\s]+$", "", str(value)).strip()
    return value[:40]


def extract_facts(text):
    text = text or ""
    facts = []

    def add(content, kind="fact", tier=1):
        content = _clean_fact_value(content)
        if content and len(content) >= 2:
            facts.append({"content": content, "kind": kind, "tier": tier})

    match = re.search(
        r"(?:我叫|我的名字(?:是|叫)|叫我|我是)\s*([\u4e00-\u9fa5A-Za-z0-9_]{1,12})", text
    )
    if match and match.group(1) not in STOP_NAMES:
        add("名字是" + match.group(1), "name", 2)

    match = re.search(
        r"(?:我(?:的)?生日(?:是|在)?|生日(?:是|在))\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]?", text
    )
    if match:
        add("生日是%02d月%02d日" % (to_int(match.group(1)), to_int(match.group(2))), "birthday", 2)

    match = re.search(r"我(?:最)?(?:喜欢|爱|中意|偏爱)\s*([^，。！？!?\n]{1,30})", text)
    if match:
        add("喜欢" + match.group(1), "preference", 1)

    match = re.search(r"我(?:最)?(?:讨厌|不喜欢|害怕|怕)\s*([^，。！？!?\n]{1,30})", text)
    if match:
        add("讨厌或害怕" + match.group(1), "preference", 1)

    match = re.search(r"我(?:住在|家在|现在在)\s*([\u4e00-\u9fa5]{2,12})(?:市|区|县|镇|附近)?", text)
    if match:
        add("住在" + match.group(1), "place", 1)

    match = re.search(r"我(?:在)\s*([\u4e00-\u9fa5A-Za-z0-9]{2,20}?)(?:上班|工作|上学|读书)", text)
    if match:
        add("在" + match.group(1) + "上班或上学", "work", 1)

    match = re.search(r"我(?:养了|有一只|有一只叫)\s*([^，。！？!?\n]{1,16})", text)
    if match:
        add("养了" + match.group(1), "pet", 1)

    match = re.search(r"我(?:今年)?\s*(\d{1,2})\s*岁", text)
    if match:
        add("今年%s岁" % match.group(1), "age", 1)

    if "生日" in text and "今天" in text:
        add("今天提到了生日", "birthday_hint", 1)

    return facts


# ---------------------------------------------------------------------------
# 分段器：书号、引号等成对符号内部绝对不切
# ---------------------------------------------------------------------------

_PAIRS = {
    "《": "》", "〈": "〉", "“": "”", "‘": "’", "「": "」", "『": "』",
    "（": "）", "(": ")", "【": "】", "〔": "〕", "[": "]", "{": "}",
}
_STRONG = "。！？!?…\n"
_WEAK = "，,、；;：:~～"
_TRIM = " \t\r\n。！？!?…，,、；;：:~～"


def _protect_mask(text):
    length = len(text)
    mask = [False] * length

    def mark(start, end):
        for index in range(max(0, start), min(length, end)):
            mask[index] = True

    for match in re.finditer(r"```.*?```", text, re.S):
        mark(match.start(), match.end())
    for match in re.finditer(r"`[^`\n]+`", text):
        mark(match.start(), match.end())
    for match in re.finditer(r"https?://[^\s]+", text):
        mark(match.start(), match.end())

    index = 0
    while index < length:
        char = text[index]
        closer = _PAIRS.get(char)
        if closer:
            depth = 1
            scan = index + 1
            while scan < length:
                if text[scan] == char:
                    depth += 1
                elif text[scan] == closer:
                    depth -= 1
                    if depth == 0:
                        break
                scan += 1
            if scan < length:
                mark(index, scan + 1)
                index = scan + 1
                continue
            mark(index, length)
            break
        index += 1
    return mask


def _cut(text, mask, delimiters, min_keep=0):
    parts = []
    start = 0
    for index, char in enumerate(text):
        if mask[index]:
            continue
        if char in delimiters and (index + 1 - start) >= min_keep:
            parts.append(text[start:index + 1])
            start = index + 1
    parts.append(text[start:])
    return parts


def _protected_ranges(text):
    mask = _protect_mask(text)
    ranges = []
    start = None
    for index, flag in enumerate(mask):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            ranges.append((start, index))
            start = None
    if start is not None:
        ranges.append((start, len(mask)))
    return ranges


def _mask_with_placeholders(text):
    ranges = _protected_ranges(text)
    if not ranges:
        return text, {}
    pieces = []
    placeholders = {}
    last = 0
    for index, (start, end) in enumerate(ranges):
        pieces.append(text[last:start])
        token = "\x00%d\x00" % index
        placeholders[token] = text[start:end]
        pieces.append(token)
        last = end
    pieces.append(text[last:])
    return "".join(pieces), placeholders


def _split_regex(text, pattern, protect_pairs=True):
    if not pattern:
        return None
    masked, placeholders = _mask_with_placeholders(text) if protect_pairs else (text, {})
    try:
        compiled = re.compile(pattern)
    except re.error:
        return None
    pieces = []
    last = 0
    for match in compiled.finditer(masked):
        end = match.end()
        if end <= last:
            continue
        pieces.append(masked[last:end])
        last = end
    pieces.append(masked[last:])
    restored = []
    for piece in pieces:
        value = piece
        for token, original in placeholders.items():
            value = value.replace(token, original)
        value = value.strip()
        if value:
            restored.append(value)
    return restored


def segment_text(text, keep_punc=True, min_len=6, max_len=42, max_segments=4,
                 mode="punct", split_chars="", regex_pattern="", protect_pairs=True):
    """按标点符号或正则分段；成对符号、代码块、URL 内部不会被切开。

    mode="punct" 时按 segment_split_chars + 内置标点分段；
    mode="regex" 时按 segment_regex 分段，失败自动回退到标点模式。
    """
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return []
    min_len = max(1, to_int(min_len, 6))
    max_len = max(min_len + 1, to_int(max_len, 42))
    max_segments = max(1, to_int(max_segments, 4))

    pieces = None
    if str(mode).lower() == "regex" and regex_pattern:
        pieces = _split_regex(text, regex_pattern, protect_pairs)
    if pieces is None:
        extra = "".join(char for char in str(split_chars or "") if char not in "\r\n")
        strong = "".join(dict.fromkeys(_STRONG + extra))
        mask = _protect_mask(text) if protect_pairs else [False] * len(text)
        pieces = []
        for part in _cut(text, mask, strong):
            part = part.strip()
            if not part:
                continue
            if len(part) > max_len:
                sub_mask = _protect_mask(part) if protect_pairs else [False] * len(part)
                pieces.extend(_cut(part, sub_mask, _WEAK, min_keep=max(4, max_len // 2)))
            else:
                pieces.append(part)

    normalized = []
    for part in pieces or []:
        part = str(part).strip()
        if not part:
            continue
        if len(part) > max_len:
            sub_mask = _protect_mask(part) if protect_pairs else [False] * len(part)
            normalized.extend(_cut(part, sub_mask, _WEAK, min_keep=max(4, max_len // 2)))
        else:
            normalized.append(part)
    pieces = normalized

    segments = []
    for part in pieces:
        seg = part.strip()
        if not keep_punc:
            seg = seg.strip(_TRIM)
        if seg:
            segments.append(seg)
    if not segments:
        return []

    index = 0
    while len(segments) > 1 and index < len(segments):
        if len(segments[index]) < min_len:
            if index + 1 < len(segments):
                segments[index + 1] = segments[index] + segments[index + 1]
                del segments[index]
                continue
            segments[index - 1] = segments[index - 1] + segments[index]
            del segments[index]
            break
        index += 1

    while len(segments) > max_segments:
        best = 0
        best_len = None
        for cursor in range(len(segments) - 1):
            total = len(segments[cursor]) + len(segments[cursor + 1])
            if best_len is None or total < best_len:
                best_len = total
                best = cursor
        segments[best] = segments[best] + segments[best + 1]
        del segments[best + 1]

    return [seg for seg in segments if seg][:max_segments]


AI_ADMISSION_RE = re.compile(
    r"(?:我是|作为|毕竟|我们|本人|本机)\s*(?:AI|人工智能|机器人|人机|程序|模型)"
    r"|(?:只是|不过是|就是个|只是个)\s*(?:AI|人工智能|机器人|人机|程序|模型)"
    r"|(?:我|咱|我们)[^。！？]{0,8}(?:AI|人工智能|机器人|人机|程序|模型)"
    r"|人机(?:也|当然|本来|就是)"
    r"|不是真人|虚拟(?:人|角色|存在)",
    re.I,
)


def looks_like_ai_admission(text):
    return bool(AI_ADMISSION_RE.search(str(text or "")))


def typing_delay_ms(text, base=700, per_char=400, cap=20000):
    """按回复字数模拟打字时间，越长的回复停顿越久；标点再补一点。"""
    clean = re.sub(r"\s+", "", str(text or ""))
    chars = len(clean)
    pauses = (
        clean.count("。") + clean.count("！") + clean.count("？")
        + clean.count("!") + clean.count("?") + clean.count("…")
    )
    commas = clean.count("，") + clean.count(",") + clean.count("、")
    value = base + chars * per_char + pauses * 70 + commas * 35
    value = min(value, cap)
    value = max(200, value * random.uniform(0.85, 1.2))
    return int(value)


# ---------------------------------------------------------------------------
# 数据库
# ---------------------------------------------------------------------------

class AmoDB:
    def __init__(self, plugin_dir):
        try:
            from astrbot.core.utils.astrbot_path import get_astrbot_data_path
            data_dir = os.path.join(get_astrbot_data_path(), "plugin_data", PLUGIN_NAME)
        except Exception:
            data_dir = os.path.join(plugin_dir, "data")
        try:
            os.makedirs(data_dir, exist_ok=True)
        except Exception:
            data_dir = plugin_dir
        self.path = os.path.join(data_dir, "amo_forever.db")
        # 4.0.0 起插件标识为 Astrbot_Amo_forever。
        # 4.0.6 保持新标识，并把 3.x 的 amo_forever 旧数据迁移到新目录。
        try:
            import shutil as _shutil
            data_root = get_astrbot_data_path()
            legacy_paths = [
                os.path.join(data_root, "plugin_data", "amo_forever", "amo_forever.db"),
                os.path.join(data_root, "plugin_data", "astrbot_plugin_amo_forever", "amo_forever.db"),
            ]
            current_size = os.path.getsize(self.path) if os.path.exists(self.path) else 0
            if current_size < 4096:
                for legacy_path in legacy_paths:
                    if not os.path.exists(legacy_path) or os.path.getsize(legacy_path) < 4096:
                        continue
                    if os.path.exists(self.path):
                        _shutil.copy2(self.path, self.path + ".bak-4.0.6")
                    for suffix in ("-wal", "-shm", "-journal"):
                        stale = self.path + suffix
                        if os.path.exists(stale):
                            try:
                                os.remove(stale)
                            except Exception:
                                pass
                    _shutil.copy2(legacy_path, self.path)
                    for suffix in ("-wal", "-shm"):
                        source = legacy_path + suffix
                        if os.path.exists(source):
                            _shutil.copy2(source, self.path + suffix)
                    logger.info("[amo] 已迁移旧版 amo_forever 数据: %s -> %s" % (legacy_path, self.path))
                    logger.info("[amo] 升级提示：插件标识保持 Astrbot_Amo_forever；旧 amo_forever 数据已迁移到新目录，配置文件也会自动合并。")
                    break
        except Exception as exc:
            logger.warning("[amo] 旧版 amo_forever 数据迁移失败: %s" % exc)
        self.lock = threading.RLock()
        self._conn = None
        self._open()

    def _open(self):
        """打开（或重新打开）连接。

        插件重载时 AstrBot 可能先调用旧实例的 terminate()，而旧实例注册的
        Web API 仍然存在；这里保证连接被关闭后下一次访问会自动重开，避免
        "Cannot operate on a closed database"。
        """
        self._conn = sqlite3.connect(self.path, check_same_thread=False, timeout=15)
        self._conn.row_factory = sqlite3.Row
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
        except Exception:
            pass

    @property
    def conn(self):
        if self._conn is None:
            self._open()
        return self._conn

    def init(self):
        with self.lock:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS profiles (
                    uid TEXT PRIMARY KEY,
                    name TEXT DEFAULT '',
                    alias TEXT DEFAULT '',
                    birthday TEXT DEFAULT '',
                    relation TEXT DEFAULT '普通',
                    affection INTEGER DEFAULT 10,
                    notes TEXT DEFAULT '',
                    platform TEXT DEFAULT '',
                    private_umo TEXT DEFAULT '',
                    last_group TEXT DEFAULT '',
                    first_seen REAL DEFAULT 0,
                    last_seen REAL DEFAULT 0,
                    msg_count INTEGER DEFAULT 0,
                    last_proactive REAL DEFAULT 0,
                    proactive_day TEXT DEFAULT '',
                    proactive_count INTEGER DEFAULT 0,
                    relation_at REAL DEFAULT 0,
                    is_admin INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    kind TEXT DEFAULT 'fact',
                    tier INTEGER DEFAULT 0,
                    created_at REAL DEFAULT 0,
                    last_hit REAL DEFAULT 0,
                    hits INTEGER DEFAULT 0,
                    expires_at REAL
                );
                CREATE INDEX IF NOT EXISTS idx_mem_uid ON memories(uid);
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    umo TEXT DEFAULT '',
                    uid TEXT DEFAULT '',
                    name TEXT DEFAULT '',
                    role TEXT DEFAULT 'user',
                    content TEXT DEFAULT '',
                    created_at REAL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_msg_umo ON messages(umo);
                CREATE TABLE IF NOT EXISTS kv (
                    key TEXT PRIMARY KEY,
                    value TEXT DEFAULT '',
                    updated REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS schedule (
                    day TEXT PRIMARY KEY,
                    items TEXT DEFAULT '[]',
                    updated REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS proactive_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    uid TEXT DEFAULT '',
                    kind TEXT DEFAULT '',
                    content TEXT DEFAULT '',
                    created REAL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS dialects (
                    term TEXT PRIMARY KEY,
                    meaning TEXT DEFAULT '',
                    region TEXT DEFAULT '',
                    example TEXT DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS relation_network (
                    a_uid TEXT NOT NULL,
                    b_uid TEXT NOT NULL,
                    relation TEXT DEFAULT '朋友',
                    note TEXT DEFAULT '',
                    updated_at REAL DEFAULT 0,
                    PRIMARY KEY(a_uid, b_uid)
                );
                """
            )
            self.conn.commit()
            self._seed_dialects()
            self._migrate_legacy()
            try:
                cols = {row[1] for row in self.conn.execute("PRAGMA table_info(profiles)").fetchall()}
                if "relation_at" not in cols:
                    self.conn.execute("ALTER TABLE profiles ADD COLUMN relation_at REAL DEFAULT 0")
                    self.conn.execute("UPDATE profiles SET relation_at=last_seen WHERE relation_at=0")
                    self.conn.commit()
            except Exception:
                pass

    def _migrate_legacy(self):
        try:
            has_old = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user_status'"
            ).fetchone()
            if has_old:
                rows = self.conn.execute(
                    "SELECT uid, relation, mem_count FROM user_status"
                ).fetchall()
                for row in rows:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO profiles(uid, relation, msg_count, first_seen, last_seen) "
                        "VALUES(?,?,?,?,?)",
                        (row["uid"], row["relation"] or "普通", row["mem_count"] or 0, now_ts(), now_ts()),
                    )
            has_old_mem = self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='memory'"
            ).fetchone()
            if has_old_mem:
                rows = self.conn.execute(
                    "SELECT uid, content, is_important FROM memory"
                ).fetchall()
                for row in rows:
                    tier = 1 if row["is_important"] else 0
                    self.conn.execute(
                        "INSERT INTO memories(uid, content, kind, tier, created_at, last_hit, hits, expires_at) "
                        "VALUES(?,?,?,?,?,?,0,?)",
                        (row["uid"], row["content"], "legacy", tier, now_ts(), now_ts(),
                         None if tier >= 2 else now_ts() + (14 if tier == 1 else 7) * 86400),
                    )
            self.conn.commit()
        except Exception as exc:
            logger.debug("[amo] 旧数据迁移跳过: %s" % exc)

    def close(self):
        with self.lock:
            if self._conn is None:
                return
            try:
                self._conn.commit()
            except Exception:
                pass
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    # ---------- KV ----------
    def kv_get(self, key, default=None):
        with self.lock:
            row = self.conn.execute("SELECT value FROM kv WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except Exception:
            return default

    def kv_set(self, key, value):
        with self.lock:
            self.conn.execute(
                "INSERT INTO kv(key, value, updated) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
                (key, json.dumps(value, ensure_ascii=False), now_ts()),
            )
            self.conn.commit()

    # ---------- 档案 ----------
    def get_profile(self, uid):
        with self.lock:
            row = self.conn.execute("SELECT * FROM profiles WHERE uid=?", (str(uid),)).fetchone()
        return dict(row) if row else {}

    def touch_profile(self, uid, name, platform, umo, group_id, private):
        uid = str(uid)
        name = name or ""
        now = now_ts()
        with self.lock:
            row = self.conn.execute("SELECT * FROM profiles WHERE uid=?", (uid,)).fetchone()
            if row is None:
                self.conn.execute(
                    "INSERT INTO profiles(uid, name, platform, private_umo, last_group, "
                    "first_seen, last_seen, msg_count) VALUES(?,?,?,?,?,?,?,1)",
                    (uid, name, platform or "", umo if private else "",
                     umo if not private else "", now, now),
                )
            else:
                updates = ["last_seen=?", "msg_count=msg_count+1"]
                values = [now]
                if name and not row["name"]:
                    updates.append("name=?")
                    values.append(name)
                if private:
                    updates.append("private_umo=?")
                    values.append(umo)
                elif group_id:
                    updates.append("last_group=?")
                    values.append(umo)
                values.append(uid)
                self.conn.execute(
                    "UPDATE profiles SET " + ", ".join(updates) + " WHERE uid=?", values
                )
            self.conn.commit()
            row = self.conn.execute("SELECT * FROM profiles WHERE uid=?", (uid,)).fetchone()
        return dict(row) if row else {}

    def update_profile(self, uid, **fields):
        allowed = ("name", "alias", "birthday", "relation", "notes",
                   "affection", "is_admin")
        updates = []
        values = []
        for key, value in fields.items():
            if key in allowed:
                updates.append(key + "=?")
                values.append(value)
        if "relation" in fields:
            updates.append("relation_at=?")
            values.append(now_ts())
        if not updates:
            return False
        values.append(str(uid))
        with self.lock:
            self.conn.execute(
                "UPDATE profiles SET " + ", ".join(updates) + " WHERE uid=?", values
            )
            self.conn.commit()
        return True

    def delete_profile(self, uid):
        with self.lock:
            self.conn.execute("DELETE FROM profiles WHERE uid=?", (str(uid),))
            self.conn.commit()

    def list_profiles(self, keyword="", limit=100):
        limit = max(1, min(int(limit), 500))
        with self.lock:
            if keyword:
                like = "%" + str(keyword) + "%"
                rows = self.conn.execute(
                    "SELECT * FROM profiles WHERE uid LIKE ? OR name LIKE ? OR alias LIKE ? "
                    "ORDER BY last_seen DESC LIMIT ?",
                    (like, like, like, limit),
                ).fetchall()
            else:
                rows = self.conn.execute(
                    "SELECT * FROM profiles ORDER BY last_seen DESC LIMIT ?", (limit,)
                ).fetchall()
        return [dict(row) for row in rows]

    def _seed_dialects(self):
        rows = [
            ("么子", "什么", "贵州·土家族地区", "你在搞么子？"),
            ("哪门", "怎么", "贵州·土家族地区", "哪门搞的？"),
            ("要得", "好的", "贵州·土家族地区", "要得，没问题"),
            ("晓得", "知道", "贵州·土家族地区", "我晓得了"),
            ("恰饭", "吃饭", "贵州·土家族地区", "走，恰饭去"),
            ("莫", "不要", "贵州·土家族地区", "你莫急"),
            ("屋头", "家里", "贵州·土家族地区", "在屋头"),
            ("落雨", "下雨", "贵州·土家族地区", "外头落雨了"),
            ("安逸", "舒服", "贵州·土家族地区", "好安逸"),
            ("拐哒", "糟糕", "贵州·土家族地区", "拐哒，忘了"),
            ("摆龙门阵", "聊天", "贵州·土家族地区", "来摆龙门阵"),
            ("崽崽", "小孩", "贵州·土家族地区", "那个崽崽"),
            ("老汉", "父亲", "贵州·土家族地区", "我老汉"),
            ("堂客", "妻子", "贵州·土家族地区", "他堂客"),
            ("哈戳戳", "傻乎乎", "贵州·土家族地区", "你哈戳戳的"),
            ("扯皮", "吵架", "贵州·土家族地区", "莫扯皮"),
            ("逗是", "就是", "贵州·土家族地区", "逗是这么回事"),
            ("热和", "暖和", "贵州·土家族地区", "屋里热和"),
            ("搞么子", "干什么", "贵州·土家族地区", "你搞么子"),
            ("巴适", "舒服", "贵州·土家族地区", "巴适得很"),
            ("啷个", "怎么", "贵州·土家族地区", "啷个办嘛"),
            ("哪样", "什么", "贵州·土家族地区", "你要哪样"),
            ("为哪样", "为什么", "贵州·土家族地区", "你为哪样不吃饭"),
            ("恁个", "这么", "贵州·土家族地区", "恁个热"),
            ("恁么", "那么", "贵州·土家族地区", "恁么远"),
            ("等哈", "等一下", "贵州·土家族地区", "等哈我"),
            ("一哈", "一下", "贵州·土家族地区", "看一哈"),
            ("哈哈儿", "一会儿", "贵州·土家族地区", "哈哈儿就来"),
            ("将才", "刚才", "贵州·土家族地区", "将才说的"),
            ("这哈", "现在", "贵州·土家族地区", "这哈忙"),
            ("那哈", "那时候", "贵州·土家族地区", "那哈还小"),
            ("哪哈", "什么时候", "贵州·土家族地区", "你哪哈来"),
            ("好久", "多久", "贵州·土家族地区", "等了好久"),
            ("清早", "早晨", "贵州·土家族地区", "清早八晨"),
            ("晌午", "中午", "贵州·土家族地区", "晌午吃饭"),
            ("黑了", "晚上", "贵州·土家族地区", "黑了再说"),
            ("昨儿个", "昨天", "贵州·土家族地区", "昨儿个下雨"),
            ("今儿个", "今天", "贵州·土家族地区", "今儿个赶场"),
            ("明儿个", "明天", "贵州·土家族地区", "明儿个去"),
            ("赶场", "赶集", "贵州·土家族地区", "去镇上赶场"),
            ("吃酒", "参加酒席", "贵州·土家族地区", "明天去吃酒"),
            ("坐席", "入席", "贵州·土家族地区", "快坐席"),
            ("背篓", "竹背篓", "贵州·土家族地区", "背个背篓"),
            ("山卡卡", "山沟里", "贵州·土家族地区", "山卡卡里头"),
            ("坝子", "平地", "贵州·土家族地区", "坝子上晒谷"),
            ("坎坎", "台阶或坎", "贵州·土家族地区", "小心坎坎"),
            ("岩脚", "山岩下", "贵州·土家族地区", "在岩脚歇气"),
            ("河沟", "小河", "贵州·土家族地区", "河沟里摸鱼"),
            ("扯火闪", "闪电", "贵州·土家族地区", "天边扯火闪"),
            ("雪米子", "小冰粒", "贵州·土家族地区", "下雪米子了"),
            ("凌冰", "冰", "贵州·土家族地区", "路上结凌冰"),
            ("太阳坝", "向阳的地方", "贵州·土家族地区", "去太阳坝坐"),
            ("阴凉坝", "阴凉处", "贵州·土家族地区", "树脚阴凉坝"),
            ("热天", "夏天", "贵州·土家族地区", "热天莫出门"),
            ("冷天", "冬天", "贵州·土家族地区", "冷天烤火"),
            ("莫慌", "别急", "贵州·土家族地区", "莫慌，慢慢来"),
            ("慢点", "慢一点", "贵州·土家族地区", "你慢点走"),
            ("归一", "完成、结束", "贵州·土家族地区", "事情搞归一了"),
            ("刹角", "收尾、结束", "贵州·土家族地区", "今天刹角了"),
            ("杀割", "结束", "贵州·土家族地区", "饭吃杀割了"),
            ("架势", "开始、用力", "贵州·土家族地区", "架势干"),
            ("稀罕", "喜欢、少见", "贵州·土家族地区", "我不稀罕"),
            ("撇脱", "干脆、简单", "贵州·土家族地区", "撇脱点"),
            ("巴心巴肠", "一心一意", "贵州·土家族地区", "巴心巴肠对你"),
            ("焦人", "让人着急", "贵州·土家族地区", "这事焦人"),
            ("恼火", "难受、麻烦", "贵州·土家族地区", "心头恼火"),
            ("造孽", "可怜", "贵州·土家族地区", "这娃儿造孽"),
            ("舒气", "整洁、清爽", "贵州·土家族地区", "屋头收拾得舒气"),
            ("冰凊", "冰凉", "贵州·土家族地区", "水冰凊"),
            ("嘎公", "外公", "贵州·土家族地区", "我嘎公"),
            ("嘎婆", "外婆", "贵州·土家族地区", "我嘎婆"),
            ("舅公", "舅爷", "贵州·土家族地区", "舅公来了"),
            ("舅婆", "舅奶", "贵州·土家族地区", "舅婆做饭"),
            ("幺爸", "最小的叔叔", "贵州·土家族地区", "幺爸在家"),
            ("幺妈", "最小的婶婶", "贵州·土家族地区", "幺妈来了"),
            ("嬢嬢", "阿姨", "贵州·土家族地区", "嬢嬢好"),
            ("老表", "表亲或哥们", "贵州·土家族地区", "老表，走哪去"),
            ("家门", "同姓、本家", "贵州·土家族地区", "我们是家门"),
            ("老庚", "同岁好友", "贵州·土家族地区", "他是我老庚"),
            ("娃儿", "孩子", "贵州·土家族地区", "这个娃儿乖"),
            ("妹崽", "女孩", "贵州·土家族地区", "那个妹崽"),
            ("男娃儿", "男孩", "贵州·土家族地区", "男娃儿调皮"),
            ("吃莽莽", "吃饭，哄小孩说法", "贵州·土家族地区", "走，吃莽莽"),
            ("嘎嘎", "肉，儿语", "贵州·土家族地区", "要吃嘎嘎"),
            ("粑粑", "饼、糍粑", "贵州·土家族地区", "烤粑粑"),
            ("折耳根", "鱼腥草", "贵州·土家族地区", "凉拌折耳根"),
            ("酸汤", "酸汤", "贵州·土家族地区", "酸汤鱼"),
            ("糟辣椒", "糟辣椒", "贵州·土家族地区", "糟辣椒炒肉"),
            ("油茶", "油茶", "贵州·土家族地区", "喝碗油茶"),
            ("洋芋", "土豆", "贵州·土家族地区", "烤洋芋"),
            ("苞谷", "玉米", "贵州·土家族地区", "掰苞谷"),
            ("红苕", "红薯", "贵州·土家族地区", "烤红苕"),
            ("海椒", "辣椒", "贵州·土家族地区", "海椒面"),
            ("盐须", "香菜", "贵州·土家族地区", "放点盐须"),
            ("鬼火戳", "生气、窝火", "贵州·土家族地区", "鬼火戳得很"),
            ("毛焦火辣", "焦急", "贵州·土家族地区", "等得毛焦火辣"),
            ("扯把子", "开玩笑", "贵州·土家族地区", "你莫扯把子"),
            ("冲壳子", "吹牛", "贵州·土家族地区", "又冲壳子"),
            ("摆闲条", "闲聊", "贵州·土家族地区", "来摆闲条"),
            ("装莽", "装傻", "贵州·土家族地区", "你莫装莽"),
            ("千翻", "调皮", "贵州·土家族地区", "这娃儿千翻"),
            ("费头子", "调皮鬼", "贵州·土家族地区", "这个费头子"),
            ("猴跳跳", "顽皮好动", "贵州·土家族地区", "猴跳跳的"),
            ("落教", "懂事", "贵州·土家族地区", "这娃儿落教"),
            ("不落教", "不懂事", "贵州·土家族地区", "你莫不落教"),
            ("弯酸", "刁难、挖苦", "贵州·土家族地区", "莫弯酸人"),
            ("洗刷", "数落", "贵州·土家族地区", "又洗刷我"),
            ("日诀", "骂", "贵州·土家族地区", "莫日诀人"),
            ("割孽", "吵架、打架", "贵州·土家族地区", "两个人割孽"),
            ("扯筋", "扯皮", "贵州·土家族地区", "莫扯筋"),
        ]
        with self.lock:
            for term, meaning, region, example in rows:
                self.conn.execute(
                    "INSERT OR IGNORE INTO dialects(term, meaning, region, example) VALUES(?,?,?,?)",
                    (term, meaning, region, example),
                )
            self.conn.commit()

    def list_dialects(self):
        with self.lock:
            rows = self.conn.execute("SELECT * FROM dialects").fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _relation_pair(a_uid, b_uid):
        a, b = str(a_uid or "").strip(), str(b_uid or "").strip()
        return (a, b) if a <= b else (b, a)

    def list_relations(self):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM relation_network ORDER BY updated_at DESC"
            ).fetchall()
        return [dict(row) for row in rows]

    def relations_for(self, uid):
        uid = str(uid or "")
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM relation_network WHERE a_uid=? OR b_uid=? ORDER BY updated_at DESC",
                (uid, uid),
            ).fetchall()
        return [dict(row) for row in rows]

    def upsert_relation(self, a_uid, b_uid, relation, note=""):
        a, b = self._relation_pair(a_uid, b_uid)
        if not a or not b or a == b:
            return False
        with self.lock:
            self.conn.execute(
                "INSERT INTO relation_network(a_uid, b_uid, relation, note, updated_at) "
                "VALUES(?,?,?,?,?) ON CONFLICT(a_uid, b_uid) DO UPDATE SET "
                "relation=excluded.relation, note=excluded.note, updated_at=excluded.updated_at",
                (a, b, str(relation or "朋友"), str(note or "")[:200], now_ts()),
            )
            self.conn.commit()
        return True

    def delete_relation(self, a_uid, b_uid):
        a, b = self._relation_pair(a_uid, b_uid)
        with self.lock:
            cursor = self.conn.execute(
                "DELETE FROM relation_network WHERE a_uid=? AND b_uid=?", (a, b)
            )
            self.conn.commit()
            return cursor.rowcount > 0

    def proactive_profiles(self, limit=30):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM profiles WHERE private_umo != '' AND relation NOT IN ('仇恨','抵触') "
                "ORDER BY last_proactive ASC LIMIT ?", (int(limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    def bump_proactive(self, uid):
        today = today_str()
        with self.lock:
            row = self.conn.execute(
                "SELECT proactive_day, proactive_count FROM profiles WHERE uid=?", (str(uid),)
            ).fetchone()
            if not row:
                return
            count = int(row["proactive_count"] or 0) + 1
            if row["proactive_day"] != today:
                count = 1
            self.conn.execute(
                "UPDATE profiles SET last_proactive=?, proactive_day=?, proactive_count=? WHERE uid=?",
                (now_ts(), today, count, str(uid)),
            )
            self.conn.commit()

    def log_proactive(self, uid, kind, content):
        with self.lock:
            self.conn.execute(
                "INSERT INTO proactive_log(uid, kind, content, created) VALUES(?,?,?,?)",
                (str(uid), kind, content, now_ts()),
            )
            self.conn.commit()

    # ---------- 记忆 ----------
    def add_memory(self, uid, content, kind="fact", tier=0,
                   normal_days=7, important_days=14):
        content = (content or "").strip()
        if not uid or not content:
            return False
        now = now_ts()
        tier = to_int(tier, 0)
        expires = None
        if tier <= 0:
            expires = now + max(1, normal_days) * 86400
        elif tier == 1:
            expires = now + max(1, important_days) * 86400
        with self.lock:
            row = self.conn.execute(
                "SELECT id FROM memories WHERE uid=? AND content=? LIMIT 1",
                (str(uid), content),
            ).fetchone()
            if row:
                self.conn.execute(
                    "UPDATE memories SET last_hit=?, hits=hits+1, expires_at=?, "
                    "tier=MAX(tier, ?) WHERE id=?",
                    (now, expires, tier, row["id"]),
                )
            else:
                self.conn.execute(
                    "INSERT INTO memories(uid, content, kind, tier, created_at, last_hit, "
                    "hits, expires_at) VALUES(?,?,?,?,?,?,0,?)",
                    (str(uid), content, kind, tier, now, now, expires),
                )
            self.conn.commit()
        return True

    def search_memories(self, uid, query, limit=6, normal_days=7, important_days=14):
        now = now_ts()
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE uid=? AND (expires_at IS NULL OR expires_at>?) "
                "ORDER BY tier DESC, last_hit DESC, id DESC LIMIT 200",
                (str(uid), now),
            ).fetchall()
            query_tokens = tokens(query)
            scored = []
            for row in rows:
                item = dict(row)
                score = overlap(query_tokens, tokens(item.get("content", "")))
                score += 0.08 * to_int(item.get("tier"))
                score += 0.02 * min(3, to_int(item.get("hits")))
                if score > 0 or not query_tokens:
                    scored.append((score, item))
            scored.sort(key=lambda pair: (-pair[0], -to_int(pair[1].get("id"))))
            result = [item for _, item in scored[:max(1, int(limit))]]
            for item in result:
                tier = to_int(item.get("tier"))
                expires = None
                if tier == 0:
                    expires = now + normal_days * 86400
                elif tier == 1:
                    expires = now + important_days * 86400
                self.conn.execute(
                    "UPDATE memories SET hits=hits+1, last_hit=?, expires_at=? WHERE id=?",
                    (now, expires, item["id"]),
                )
                item["expires_at"] = expires
            self.conn.commit()
        return result

    def list_memories(self, uid, limit=30):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM memories WHERE uid=? ORDER BY tier DESC, last_hit DESC, id DESC LIMIT ?",
                (str(uid), int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_memory(self, memory_id):
        with self.lock:
            self.conn.execute("DELETE FROM memories WHERE id=?", (to_int(memory_id),))
            self.conn.commit()
        return True

    def count_memories(self, uid):
        with self.lock:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE uid=? AND "
                "(expires_at IS NULL OR expires_at>?)", (str(uid), now_ts())
            ).fetchone()
        return int(row["c"]) if row else 0

    def purge_memories(self):
        with self.lock:
            self.conn.execute("DELETE FROM memories WHERE expires_at IS NOT NULL AND expires_at<?",
                              (now_ts(),))
            self.conn.commit()

    # ---------- 消息 ----------
    def add_message(self, umo, uid, name, role, content):
        content = str(content or "").strip()
        if not content:
            return
        with self.lock:
            self.conn.execute(
                "INSERT INTO messages(umo, uid, name, role, content, created_at) VALUES(?,?,?,?,?,?)",
                (str(umo), str(uid), str(name or ""), role, content, now_ts()),
            )
            self.conn.commit()

    def recent_messages(self, umo, limit=10):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE umo=? ORDER BY id DESC LIMIT ?",
                (str(umo), int(limit)),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def messages_by_uid(self, uid, limit=20):
        with self.lock:
            rows = self.conn.execute(
                "SELECT * FROM messages WHERE uid=? ORDER BY id DESC LIMIT ?",
                (str(uid), int(limit)),
            ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def chat_history(self, uid, limit=200):
        """按用户参与过的 umo 取原始聊天记录（本人 + 机器人），不是摘要记忆。"""
        uid = str(uid)
        limit = max(1, min(2000, int(limit or 200)))
        with self.lock:
            rows = self.conn.execute(
                "SELECT DISTINCT umo FROM messages WHERE uid=? AND umo!=''",
                (uid,),
            ).fetchall()
            umos = [str(row["umo"]) for row in rows if str(row["umo"] or "")]
            if not umos:
                rows = self.conn.execute(
                    "SELECT * FROM messages WHERE uid=? ORDER BY id DESC LIMIT ?",
                    (uid, limit),
                ).fetchall()
            else:
                placeholders = ",".join("?" for _ in umos)
                params = umos + [uid, limit]
                rows = self.conn.execute(
                    "SELECT * FROM messages WHERE umo IN (" + placeholders + ") "
                    "AND (uid=? OR role='bot') ORDER BY id DESC LIMIT ?",
                    params,
                ).fetchall()
        return [dict(row) for row in reversed(rows)]

    def active_users(self, since, limit=2):
        with self.lock:
            rows = self.conn.execute(
                "SELECT uid, name, COUNT(*) AS c FROM messages WHERE role='user' AND created_at>? "
                "GROUP BY uid ORDER BY c DESC LIMIT ?", (float(since), int(limit))
            ).fetchall()
        return [dict(row) for row in rows]

    def purge_messages(self, days=14):
        with self.lock:
            self.conn.execute("DELETE FROM messages WHERE created_at<?",
                              (now_ts() - max(1, int(days)) * 86400,))
            self.conn.commit()

    # ---------- 日程 ----------
    def save_schedule(self, day, items):
        with self.lock:
            self.conn.execute(
                "INSERT INTO schedule(day, items, updated) VALUES(?,?,?) "
                "ON CONFLICT(day) DO UPDATE SET items=excluded.items, updated=excluded.updated",
                (str(day), json.dumps(items, ensure_ascii=False), now_ts()),
            )
            self.conn.commit()

    def fade_schedules(self, days=7):
        """7~14 天前的日程去掉细节，只保留每小时骨架。"""
        cutoff = (date.today() - timedelta(days=max(1, int(days)))).isoformat()
        with self.lock:
            rows = self.conn.execute(
                "SELECT day, items FROM schedule WHERE day < ?", (cutoff,)
            ).fetchall()
            for row in rows:
                try:
                    items = json.loads(row["items"])
                except Exception:
                    continue
                if not isinstance(items, list):
                    continue
                for item in items:
                    if isinstance(item, dict):
                        item.pop("detail", None)
                self.conn.execute(
                    "UPDATE schedule SET items=? WHERE day=?",
                    (json.dumps(items, ensure_ascii=False), row["day"]),
                )
            self.conn.commit()

    def purge_schedules(self, days=14):
        cutoff = (date.today() - timedelta(days=max(1, int(days)))).isoformat()
        with self.lock:
            self.conn.execute("DELETE FROM schedule WHERE day < ?", (cutoff,))
            self.conn.commit()

    def get_schedule(self, day):
        with self.lock:
            row = self.conn.execute("SELECT items FROM schedule WHERE day=?", (str(day),)).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["items"])
        except Exception:
            return None

    # ---------- 统计 ----------
    def counts(self):
        with self.lock:
            profiles = self.conn.execute("SELECT COUNT(*) AS c FROM profiles").fetchone()["c"]
            memories = self.conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE expires_at IS NULL OR expires_at>?",
                (now_ts(),),
            ).fetchone()["c"]
            messages = self.conn.execute("SELECT COUNT(*) AS c FROM messages").fetchone()["c"]
        return {"profiles": profiles, "memories": memories, "messages": messages}


# ---------------------------------------------------------------------------
# 状态：九维心情 / 生理期 / 健康 / 天气 / 世界观 / 日程
# ---------------------------------------------------------------------------

class HumanState:
    def __init__(self, plugin):
        self.p = plugin
        self.db = plugin.db
        saved_mood = self.db.kv_get("mood", {}) or {}
        self.mood = {key: clamp(saved_mood.get(key, MOOD_BASE[key])) for key in MOOD_KEYS}
        self.mood_ts = to_float(self.db.kv_get("mood_ts", now_ts()), now_ts())
        config_start = self.p.cfg_str("period_start", "").strip()
        seen = self.db.kv_get("period_config_seen", "")
        stored = self.db.kv_get("period_start", "")
        if config_start and config_start != seen:
            try:
                date.fromisoformat(config_start)
                stored = config_start
                self.db.kv_set("period_config_seen", config_start)
            except Exception:
                pass
        self.period_start = stored or (date.today() - timedelta(days=10)).isoformat()
        self.health = self.db.kv_get("health", {}) or {
            "status": "健康", "since": now_ts(), "until": 0, "note": ""
        }
        self.weather = self.db.kv_get("weather", {}) or {}
        self.worldview = self.db.kv_get("worldview", {}) or {}
        self.schedule = self.db.kv_get("schedule", {}) or {}
        self.last_daily = self.db.kv_get("last_daily", "")
        self.last_health_roll = self.db.kv_get("last_health_roll", "")

    # ---------- 心情 ----------
    def save_mood(self):
        self.db.kv_set("mood", {key: round(value, 2) for key, value in self.mood.items()})
        self.db.kv_set("mood_ts", self.mood_ts)

    def save(self):
        self.save_mood()
        self.db.kv_set("period_start", self.period_start)
        self.db.kv_set("health", self.health)
        self.db.kv_set("last_daily", self.last_daily)
        self.db.kv_set("last_health_roll", self.last_health_roll)

    def nudge(self, **deltas):
        for key, value in deltas.items():
            if key in self.mood:
                self.mood[key] = clamp(self.mood[key] + value)
        self.mood_ts = now_ts()
        self.save_mood()

    def decay_mood(self):
        now = now_ts()
        hours = max(0.0, (now - self.mood_ts) / 3600.0)
        if hours <= 0:
            return
        # 连续衰减：约 45 分钟向基础值回落一半，不再要求隔 9 分钟才衰减一次。
        rate = min(0.85, 1.0 - math.exp(-hours / 0.75))
        for key in MOOD_KEYS:
            self.mood[key] = self.mood[key] + (MOOD_BASE[key] - self.mood[key]) * rate
        self.mood_ts = now
        self.save_mood()

    def dominant_mood(self):
        return max(MOOD_KEYS, key=lambda key: self.mood[key])

    def mood_score(self):
        m = self.mood
        positive = (m["开心"] + m["兴奋"] + m["平静"] + m["依恋"]) / 4.0
        negative = (m["郁闷"] + m["疲惫"] + m["生气"] + m["暴躁"] + m["委屈"] + m["焦虑"]) / 6.0
        return clamp(50 + (positive - negative) * 0.8)

    def mood_text(self):
        parts = [key + str(int(round(value))) for key, value in self.mood.items()]
        return " ".join(parts) + "（整体偏" + self.dominant_mood() + "）"

    def observe(self, text):
        senti = sentiment(text)
        if re.search(r"(对不起|抱歉|我错了|别生气|不生气|哄你|哄哄|原谅我)", text or ""):
            # 恋人或普通人的道歉都要能真正降温，不能“道歉也没用”。
            self.nudge(生气=-18, 暴躁=-10, 委屈=-6, 郁闷=-3, 开心=4, 依恋=2)
        elif senti["insult"] or senti["angry"] >= 2:
            self.nudge(生气=9, 暴躁=5, 开心=-8, 委屈=5)
        elif senti["sad"]:
            self.nudge(郁闷=8, 委屈=7, 开心=-4)
        elif senti["aff"]:
            self.nudge(开心=10, 依恋=12, 生气=-5, 暴躁=-3)
        elif senti["pos"]:
            self.nudge(开心=6, 平静=2, 生气=-2)
        elif senti["neg"]:
            self.nudge(郁闷=4, 疲惫=2)
        else:
            self.nudge(平静=1)
        hour = datetime.now().hour
        if 0 <= hour < 6:
            self.nudge(疲惫=3, 平静=2)
        elif 6 <= hour < 9:
            self.nudge(疲惫=-1, 开心=1)
        elif 22 <= hour < 24:
            self.nudge(疲惫=2, 依恋=2)

    # ---------- 生理期 ----------
    def period_info(self):
        if not self.p.cfg_bool("enable_period_simulate", True):
            return {
                "day": 0, "phase": "非生理期", "tone": "", "pain": 0,
                "reply_mult": 1.0, "days_to_next": 0,
                "cycle_days": self.p.cfg_int("period_cycle_days", 28),
                "bleed_days": 0, "next_start": "",
            }
        try:
            start = date.fromisoformat(str(self.period_start))
        except Exception:
            start = date.today() - timedelta(days=10)
            self.period_start = start.isoformat()
        cycle_days = max(10, self.p.cfg_int("period_cycle_days", 28))
        bleed_days = max(1, min(self.p.cfg_int("period_days", 5), cycle_days - 6))
        day = (date.today() - start).days % cycle_days + 1
        ovulation_day = max(bleed_days + 1, min(cycle_days - 1, self.p.cfg_int("period_ovulation_day", 14)))
        ovulation_window = max(1, min(9, self.p.cfg_int("period_ovulation_window", 3)))
        ovulation_start = max(bleed_days + 1, ovulation_day - (ovulation_window - 1) // 2)
        ovulation_end = min(cycle_days - 1, ovulation_start + ovulation_window - 1)
        if day <= bleed_days:
            phase = "月经期"
            tone = self.p.cfg_str("period_menstrual_tone", "身体沉沉的，容易累，也更容易委屈")
            pain = min(9, 5 + max(0, bleed_days + 1 - day))
            reply_mult = 0.8
        elif day < ovulation_start:
            phase = "卵泡期"
            tone = self.p.cfg_str("period_follicular_tone", "身体轻快，心情慢慢变好")
            pain = 1
            reply_mult = 1.05
        elif day <= ovulation_end:
            phase = "排卵期"
            tone = self.p.cfg_str("period_ovulatory_tone", "精力最好，也更想和人说话")
            pain = 0
            reply_mult = 1.12
        else:
            phase = "黄体期"
            tone = self.p.cfg_str("period_luteal_tone", "容易烦躁、敏感，想要被哄")
            pain = 3
            reply_mult = 0.88
        pain = max(0, min(10, pain + (md5_int(str(start) + str(day)) % 3) - 1))
        if phase == "月经期":
            phase_day = day
        elif phase == "卵泡期":
            phase_day = day - bleed_days
        elif phase == "排卵期":
            phase_day = day - ovulation_start + 1
        else:
            phase_day = day - ovulation_end
        return {
            "day": day, "phase": phase, "phase_day": max(1, phase_day),
            "tone": tone, "pain": pain,
            "reply_mult": reply_mult, "days_to_next": cycle_days - day + 1,
            "cycle_days": cycle_days, "bleed_days": bleed_days,
            "ovulation_day": ovulation_day, "ovulation_window": ovulation_window,
            "next_start": (date.today() + timedelta(days=cycle_days - day + 1)).isoformat(),
        }

    def set_period_start(self, value):
        try:
            parsed = date.fromisoformat(str(value))
        except Exception:
            return False
        self.period_start = parsed.isoformat()
        self.db.kv_set("period_start", self.period_start)
        self.db.kv_set("period_config_seen", self.p.cfg_str("period_start", ""))
        return True

    # ---------- 健康 ----------
    def health_info(self):
        status = self.health.get("status", "健康")
        until = to_float(self.health.get("until", 0))
        if status != "健康" and until and now_ts() >= until:
            self.health = {"status": "健康", "since": now_ts(), "until": 0, "note": ""}
            self.db.kv_set("health", self.health)
            status = "健康"
        return {
            "status": status,
            "since": to_float(self.health.get("since", 0)),
            "until": to_float(self.health.get("until", 0)),
            "note": self.health.get("note", ""),
            "sick": status != "健康",
        }

    def set_health(self, status, hours=24, note=""):
        if status == "健康":
            self.health = {"status": "健康", "since": now_ts(), "until": 0, "note": ""}
        else:
            self.health = {
                "status": status, "since": now_ts(),
                "until": now_ts() + max(1, hours) * 3600, "note": note,
            }
        self.db.kv_set("health", self.health)

    def roll_health(self):
        if not self.p.cfg_bool("enable_sick_random", True):
            return
        now = now_ts()
        if self.health.get("status") != "健康" and to_float(self.health.get("until", 0)) <= now:
            self.health = {"status": "健康", "since": now, "until": 0, "note": ""}
            self.db.kv_set("health", self.health)
        if self.last_health_roll == today_str():
            return
        self.last_health_roll = today_str()
        self.db.kv_set("last_health_roll", self.last_health_roll)
        if self.health.get("status") != "健康":
            return
        prob = self.p.cfg_float("sick_prob", 0.02)
        weather = self.weather or {}
        if weather.get("tag") in ("rain", "storm", "snow"):
            prob += 0.03
        if to_float(weather.get("temp", 20), 20) < 8:
            prob += 0.02
        if self.period_info()["phase"] == "月经期":
            prob += 0.02
        if self.mood.get("疲惫", 0) > 65:
            prob += 0.02
        if random.random() >= prob:
            return
        status = random.choice(["轻微不适", "感冒", "低烧", "疲惫"])
        hours = {"轻微不适": 12, "感冒": 48, "低烧": 24, "疲惫": 10}[status]
        note = {
            "轻微不适": "有点不舒服，说不上哪里难受",
            "感冒": "鼻子堵堵的，头有点沉",
            "低烧": "身上发烫，没什么力气",
            "疲惫": "没由来的累，只想躺着",
        }[status]
        self.health = {"status": status, "since": now, "until": now + hours * 3600, "note": note}
        self.db.kv_set("health", self.health)

    # ---------- 天气 ----------
    @staticmethod
    def _weather_tag(text):
        if any(word in text for word in ("雷", "暴雨")):
            return "storm"
        if "雪" in text:
            return "snow"
        if "雨" in text:
            return "rain"
        if "晴" in text:
            return "clear"
        if "阴" in text:
            return "overcast"
        if "雾" in text or "霾" in text:
            return "fog"
        return "cloud"

    def _simulate_weather(self):
        month = date.today().month
        rng = random.Random(md5_int(today_str() + str(datetime.now().hour)))
        if month in (12, 1, 2):
            choices = [("晴", "clear"), ("多云", "cloud"), ("阴", "overcast"),
                       ("小雪", "snow"), ("小雨", "rain")]
            base_temp = 7
        elif month in (6, 7, 8):
            choices = [("晴", "clear"), ("多云", "cloud"), ("雷阵雨", "storm"),
                       ("阵雨", "rain"), ("阴", "overcast")]
            base_temp = 29
        else:
            choices = [("晴", "clear"), ("多云", "cloud"), ("小雨", "rain"),
                       ("阴", "overcast")]
            base_temp = 19
        text, tag = rng.choice(choices)
        temp = base_temp + rng.randint(-4, 4)
        return {
            "city": self.p.cfg_str("weather_city", "杭州"),
            "text": text, "tag": tag, "temp": temp,
            "humidity": rng.randint(40, 90),
            "wind": random.choice(["东风", "南风", "西北风", "微风"]) + str(rng.randint(1, 4)) + "级",
            "ts": now_ts(), "source": "simulate", "ok": True, "error": "",
            "key_set": bool(self.p.cfg_str("hefeng_key", "")),
            "host": self.p.cfg_str("weather_host", ""),
        }

    async def _qweather_payload(self, response, label):
        try:
            text = await response.text()
        except Exception as exc:
            logger.warning("[amo] 和风天气 %s 读取响应失败: %s" % (label, exc))
            return {}
        if not str(text or "").strip():
            logger.warning("[amo] 和风天气 %s 返回空响应 HTTP %s" % (label, getattr(response, "status", "?")))
            return {}
        try:
            payload = json.loads(text)
        except Exception:
            logger.warning(
                "[amo] 和风天气 %s 返回非 JSON HTTP %s: %s"
                % (label, getattr(response, "status", "?"), str(text)[:160])
            )
            return {}
        if not isinstance(payload, dict):
            logger.warning("[amo] 和风天气 %s 返回格式异常: %s" % (label, type(payload).__name__))
            return {}
        code = str(payload.get("code") or "")
        status = to_int(getattr(response, "status", 0), 0)
        if status >= 400 or (code and code != "200"):
            logger.warning(
                "[amo] 和风天气 %s HTTP %s code=%s: %s"
                % (label, status, code or "?", str(payload)[:200])
            )
        return payload

    async def _fetch_qweather(self, key, city):
        try:
            import aiohttp
        except Exception:
            return None
        host = (self.p.cfg_str("weather_host", "https://devapi.qweather.com") or "https://devapi.qweather.com").strip().rstrip("/")
        if host and not host.startswith(("http://", "https://")):
            host = "https://" + host
        legacy_hosts = {"https://devapi.qweather.com", "https://api.qweather.com"}
        geo_raw = self.p.cfg_str("weather_geo_host", "").strip().rstrip("/")
        if geo_raw and not geo_raw.startswith(("http://", "https://")):
            geo_raw = "https://" + geo_raw
        if geo_raw:
            geo_base = geo_raw
            if geo_base.endswith("/city/lookup"):
                geo_base = geo_base[:-len("/city/lookup")]
            if not geo_base.endswith(("/geo/v2", "/v2")):
                geo_base += "/geo/v2"
        elif host in legacy_hosts:
            geo_base = "https://geoapi.qweather.com/v2"
        else:
            geo_base = host + "/geo/v2"
        if host in legacy_hosts:
            logger.warning("[amo] 和风天气公共 API 域名已停服，请在配置里填写控制台的 API Host")
        headers = {"X-QW-Api-Key": key}
        timeout = aiohttp.ClientTimeout(total=8)
        location = str(city)
        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                if not location.isdigit():
                    async with session.get(
                        geo_base + "/city/lookup",
                        params={"location": location, "key": key, "number": 1},
                    ) as response:
                        geo = await self._qweather_payload(response, "geo")
                    if str(geo.get("code") or "") != "200" or not isinstance(geo.get("location"), list):
                        return None
                    first = geo["location"][0] if geo["location"] else None
                    if not isinstance(first, dict) or not first.get("id"):
                        return None
                    location = str(first["id"])
                async with session.get(
                    host + "/v7/weather/now",
                    params={"location": location, "key": key},
                ) as response:
                    data = await self._qweather_payload(response, "now")
                if str(data.get("code") or "") != "200":
                    return None
                now = data.get("now")
                if not isinstance(now, dict):
                    logger.warning("[amo] 和风天气 now 字段缺失或格式异常")
                    return None
                text = str(now.get("text") or "多云")
                return {
                    "city": city, "text": text, "tag": self._weather_tag(text),
                    "temp": to_int(now.get("temp")), "humidity": to_int(now.get("humidity")),
                    "wind": str(now.get("windDir", "")) + str(now.get("windScale", "")) + "级",
                    "ts": now_ts(), "source": "qweather", "ok": True, "error": "",
                    "key_set": True,
                    "host": host,
                }
        except Exception as exc:
            logger.warning("[amo] 和风天气接口失败: %s" % exc)
            return None

    async def refresh_weather(self, force=False):
        try:
            self.p._reload_config_if_changed()
        except Exception:
            pass
        current = self.weather or {}
        key = self.p.cfg_str("hefeng_key", "")
        city = self.p.cfg_str("weather_city", "杭州")
        host = self.p.cfg_str("weather_host", "")
        # 配置里的城市/Key/Host 变了就必须重取，不能继续用旧缓存。
        current_signature = (current.get("city"), bool(current.get("key_set")), current.get("host"))
        desired_signature = (city, bool(key), host)
        if current_signature != desired_signature:
            force = True
        if not force and current.get("ts") and now_ts() - current["ts"] < 1800:
            return current
        old_tag = current.get("tag")
        data = None
        if key:
            data = await self._fetch_qweather(key, city)
        if not data:
            data = self._simulate_weather()
        self.weather = data
        self.db.kv_set("weather", data)
        if data.get("tag") != old_tag:
            if data.get("tag") in ("rain", "storm", "snow"):
                self.nudge(郁闷=2, 平静=2)
            elif data.get("tag") == "clear":
                self.nudge(开心=2)
        return data

    def weather_text(self):
        weather = self.weather or {}
        if not weather:
            return "还不知道天气"
        return "%s %s %s℃ 湿度%s%% %s" % (
            weather.get("city", ""), weather.get("text", ""),
            weather.get("temp", ""), weather.get("humidity", ""), weather.get("wind", ""),
        )

    # ---------- 世界观 ----------
    def _fallback_world(self):
        return {
            "name": self.p.persona_name or self.p.cfg_str("bot_name", "") or "陪伴",
            "age": 22,
            "city": self.p.cfg_str("weather_city", "杭州"),
            "occupation": "普通上班族",
            "workplace": "公司",
            "personality": "温柔、敏感，偶尔有点小脾气",
            "hobbies": ["听歌", "散步", "喝奶茶"],
            "daily_life": "一个人在城市里上班、生活，会为小事开心，也会有力气用光的时候。",
            "world_rules": "这是一个普通的现代都市，没有超能力；角色要上班、吃饭、睡觉，也会生病和情绪低落。",
            "summary": "一个在城市里认真生活的普通女孩。",
            "_ts": now_ts(),
        }

    async def ensure_worldview(self, umo, force=False):
        if not force and self.worldview and now_ts() - to_float(self.worldview.get("_ts")) < 7 * 86400:
            return self.worldview
        persona = await self.p.llm.persona(umo)
        data = await self.p.llm.gen_worldview(umo, persona)
        if not data:
            data = self._fallback_world()
        name = await self.p._persona_name_for(umo)
        if name:
            data["name"] = name
        data["_ts"] = now_ts()
        self.worldview = data
        self.db.kv_set("worldview", data)
        if name:
            self.p.persona_name = name
            self.p.bot_name = name
        elif data.get("name") and self.p.cfg_str("bot_name", ""):
            self.p.bot_name = data["name"]
        return data

    def worldview_text(self):
        world = self.worldview or {}
        if not world:
            return "还没有生成世界观。"
        hobbies = world.get("hobbies") or []
        if isinstance(hobbies, list):
            hobbies = "、".join([str(item) for item in hobbies])
        return "\n".join([
            "名字：%s" % world.get("name", ""),
            "年龄：%s" % world.get("age", ""),
            "城市：%s" % world.get("city", ""),
            "职业：%s" % world.get("occupation", ""),
            "任职：%s" % world.get("workplace", ""),
            "性格：%s" % world.get("personality", ""),
            "爱好：%s" % hobbies,
            "日常：%s" % world.get("daily_life", ""),
            "规则：%s" % world.get("world_rules", ""),
        ])

    # ---------- 日程 ----------
    @staticmethod
    def _hourly_schedule(items):
        """把任意日程整理成 24 条整点日程。"""
        valid = [item for item in (items or []) if isinstance(item, dict) and item.get("start")]
        valid.sort(key=lambda item: parse_hhmm(item.get("start")))
        result = []
        for hour in range(24):
            start_min = hour * 60
            end_min = start_min + 60
            found = None
            for item in valid:
                begin = parse_hhmm(item.get("start"))
                finish = parse_hhmm(item.get("end")) or (begin + 60)
                if begin <= start_min < finish:
                    found = item
                    break
            if found:
                entry = {
                    "start": "%02d:00" % hour,
                    "end": "23:59" if hour == 23 else "%02d:00" % (hour + 1),
                    "activity": found.get("activity", "休息"),
                    "place": found.get("place", "家"),
                    "category": found.get("category", "rest"),
                }
                if found.get("detail"):
                    entry["detail"] = found["detail"]
                if isinstance(found.get("segments"), list):
                    entry["segments"] = found["segments"]
            else:
                sleep = hour < 7 or hour >= 23
                entry = {
                    "start": "%02d:00" % hour,
                    "end": "23:59" if hour == 23 else "%02d:00" % (hour + 1),
                    "activity": "睡觉" if sleep else "休息",
                    "place": "家",
                    "category": "sleep" if sleep else "rest",
                }
            result.append(entry)
        return result

    @staticmethod
    def _fmt_minutes(value):
        value = max(0, min(24 * 60 - 1, int(value)))
        return "%02d:%02d" % (value // 60, value % 60)

    def schedule_tree(self):
        """一级 3 段、二级每小时、三级每 10 分钟的日程树。"""
        hourly = self._hourly_schedule(self.schedule.get(today_str()) or [])
        now_min = minutes_now()
        blocks = [
            {"start": "00:00", "end": "06:00", "title": "夜间", "activity": "休息", "place": "家", "category": "sleep"},
            {"start": "06:00", "end": "12:00", "title": "上午", "activity": "活动", "place": "家", "category": "life"},
            {"start": "12:00", "end": "18:00", "title": "下午", "activity": "活动", "place": "家", "category": "life"},
            {"start": "18:00", "end": "23:59", "title": "晚上", "activity": "活动", "place": "家", "category": "rest"},
        ]
        for block in blocks:
            bstart = parse_hhmm(block["start"])
            bend = 24 * 60 if block["end"] == "23:59" else parse_hhmm(block["end"])
            children = []
            for item in hourly:
                start = max(bstart, parse_hhmm(item.get("start")))
                end = min(bend, parse_hhmm(item.get("end")))
                if start >= end:
                    continue
                hour = {
                    "start": self._fmt_minutes(start),
                    "end": self._fmt_minutes(end - 1 if end < 24 * 60 else 23 * 60 + 59),
                    "activity": item.get("activity", "休息"),
                    "place": item.get("place", "家"),
                    "category": item.get("category", "rest"),
                    "detail": item.get("detail", ""),
                    "current": start <= now_min < end,
                    "children": [],
                }
                hour["children"] = self._micro_segments(item, start, end)
                children.append(hour)
            block["children"] = children
            block["current"] = any(child["current"] for child in children)
            if children:
                block["place"] = children[0].get("place") or block["place"]
                block["activity"] = children[0].get("activity") or block["activity"]
        return blocks

    def _micro_segments(self, hour, start, end):
        """把一小时拆成 6 个 10 分钟小段；优先用模型给出的细段。"""
        raw = hour.get("segments") if isinstance(hour.get("segments"), list) else []
        if raw:
            result = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                begin = parse_hhmm(item.get("start"))
                finish = parse_hhmm(item.get("end"))
                if begin >= finish:
                    continue
                result.append({
                    "start": self._fmt_minutes(begin),
                    "end": self._fmt_minutes(finish - 1),
                    "activity": item.get("activity", hour.get("activity", "休息")),
                    "place": item.get("place", hour.get("place", "家")),
                    "category": item.get("category", hour.get("category", "rest")),
                    "current": begin <= minutes_now() < finish,
                })
            if result:
                return result
        category = hour.get("category", "rest")
        hour_num = start // 60
        patterns = {
            "work": ["开电脑看消息", "写代码改文档", "开会讨论", "回消息处理需求", "起身倒水、上厕所", "摸鱼刷手机"],
            "study": ["看书", "整理笔记", "做题", "查资料", "起身活动", "摸鱼"],
            "commute": ["走路", "等车", "车上刷手机", "换乘", "出站", "到公司/到家"],
            "meal": ["吃饭", "边吃边聊", "刷手机", "喝汤", "收碗", "回工位"],
            "rest": ["刷手机", "发呆", "喝水", "上厕所", "看视频", "伸懒腰"],
            "play": ["玩游戏", "看视频", "聊天", "吃点零食", "起身走动", "继续玩"],
            "sleep": ["睡觉", "睡觉", "睡觉", "睡觉", "睡觉", "睡觉"],
            "life": ["收拾东西", "走动", "喝水", "看手机", "整理", "准备下一件事"],
        }
        if category == "life" and 7 <= hour_num < 8:
            actions = ["洗脸刷牙", "换衣服", "吃早餐", "收拾包", "穿鞋", "出门"]
        elif category == "life" and 22 <= hour_num < 23:
            actions = ["洗澡", "吹头发", "护肤", "刷牙", "躺床上", "刷会儿手机"]
        else:
            actions = patterns.get(category, patterns["rest"])
        offset = hour_num % len(actions)
        result = []
        cursor = start
        for index in range(6):
            if cursor >= end:
                break
            nxt = min(cursor + 10, end)
            result.append({
                "start": self._fmt_minutes(cursor),
                "end": self._fmt_minutes(nxt - 1),
                "activity": actions[(index + offset) % len(actions)],
                "place": hour.get("place", "家"),
                "category": category,
                "current": cursor <= minutes_now() < nxt,
            })
            cursor = nxt
        return result

    @staticmethod
    def _cover_schedule(items):
        """给日程补上 00:00 到第一条安排之间的睡眠段。"""
        if not isinstance(items, list) or not items:
            return items
        valid = [item for item in items if isinstance(item, dict) and item.get("start")]
        if not valid:
            return items
        ordered = sorted(valid, key=lambda item: parse_hhmm(item.get("start")))
        first_start = ordered[0].get("start", "00:00")
        if parse_hhmm(first_start) > 0:
            ordered.insert(0, {
                "start": "00:00", "end": first_start,
                "activity": "睡觉", "place": "家", "category": "sleep",
            })
        return ordered

    def _travel_schedule(self, meta):
        """长假去外省旅游，日程里包含交通、景区、酒店和当地吃饭。"""
        seed = (meta.get("holiday") or "") + (meta.get("date") or "")[:4]
        spots = self.p.scenic_spots()
        home = self.p.cfg_str("weather_city", "")
        if home in ("铜仁", "贵阳", "遵义", "安顺", "毕节", "六盘水", "凯里", "都匀", "兴义"):
            spots = [item for item in spots if str(item.get("province") or "") != "贵州"]
        if spots:
            chosen = spots[md5_int(seed) % len(spots)]
            city = str(chosen.get("city") or chosen.get("province") or "")
            spot = str(chosen.get("name") or "")
            projects = [str(item) for item in (chosen.get("projects") or []) if str(item)]
            project_a = projects[0] if projects else "景区主景点"
            project_b = projects[1] if len(projects) > 1 else "拍照散步"
            night_spot = city + "·夜市"
        else:
            city, spot, project_a, project_b, night_spot = "云南·大理", "大理古城", "大理古城", "洱海", "大理·夜市"
        return [
            {"start": "00:00", "end": "06:00", "activity": "在酒店睡觉", "place": city + "·酒店", "category": "sleep"},
            {"start": "06:00", "end": "07:00", "activity": "起床洗漱", "place": city + "·酒店", "category": "life"},
            {"start": "07:00", "end": "08:00", "activity": "酒店吃早饭", "place": city + "·酒店", "category": "meal"},
            {"start": "08:00", "end": "10:00", "activity": "坐高铁/飞机去" + city, "place": "路上", "category": "commute"},
            {"start": "10:00", "end": "12:00", "activity": "到酒店放行李、去" + spot, "place": city + "·" + spot, "category": "commute"},
            {"start": "12:00", "end": "13:00", "activity": "在景区附近吃当地午饭", "place": city + "·" + spot, "category": "meal"},
            {"start": "13:00", "end": "15:00", "activity": "逛" + spot + "：" + project_a, "place": city + "·" + spot, "category": "play"},
            {"start": "15:00", "end": "17:00", "activity": "体验" + project_b, "place": city + "·" + spot, "category": "play"},
            {"start": "17:00", "end": "19:00", "activity": "回酒店休息", "place": city + "·酒店", "category": "rest"},
            {"start": "19:00", "end": "20:00", "activity": "吃当地特色晚饭", "place": city + "·" + night_spot, "category": "meal"},
            {"start": "20:00", "end": "22:00", "activity": "逛" + night_spot + "夜市", "place": city + "·" + night_spot, "category": "play"},
            {"start": "22:00", "end": "23:00", "activity": "回酒店洗澡", "place": city + "·酒店", "category": "life"},
            {"start": "23:00", "end": "23:59", "activity": "睡觉", "place": city + "·酒店", "category": "sleep"},
        ]

    def _fallback_schedule(self):
        """真人化的整点兜底日程：通勤、开会、下午茶、上厕所、摸鱼都有。"""
        meta = day_meta()
        if meta["holiday_days"] >= 4:
            return self._with_daily_events(self._travel_schedule(meta))
        weekday = not meta["rest"]
        if weekday:
            items = [
                {"start": "00:00", "end": "01:00", "activity": "睡觉", "place": "家", "category": "sleep"},
                {"start": "01:00", "end": "02:00", "activity": "睡觉", "place": "家", "category": "sleep"},
                {"start": "02:00", "end": "03:00", "activity": "睡觉", "place": "家", "category": "sleep"},
                {"start": "03:00", "end": "04:00", "activity": "睡觉", "place": "家", "category": "sleep"},
                {"start": "04:00", "end": "05:00", "activity": "睡觉", "place": "家", "category": "sleep"},
                {"start": "05:00", "end": "06:00", "activity": "睡觉", "place": "家", "category": "sleep"},
                {"start": "06:00", "end": "07:00", "activity": "睡觉", "place": "家", "category": "sleep"},
                {"start": "07:00", "end": "08:00", "activity": "起床洗漱、吃早餐", "place": "家", "category": "life"},
                {"start": "08:00", "end": "09:00", "activity": "通勤去公司", "place": "地铁上", "category": "commute"},
                {"start": "09:00", "end": "10:00", "activity": "到公司、开电脑、看消息", "place": "公司", "category": "work"},
                {"start": "10:00", "end": "11:00", "activity": "写代码、开个短会", "place": "公司", "category": "work"},
                {"start": "11:00", "end": "12:00", "activity": "处理需求、回消息", "place": "公司", "category": "work"},
                {"start": "12:00", "end": "13:00", "activity": "吃午饭、和同事闲聊", "place": "公司附近", "category": "meal"},
                {"start": "13:00", "end": "14:00", "activity": "午休、摸鱼刷手机", "place": "工位", "category": "rest"},
                {"start": "14:00", "end": "15:00", "activity": "写代码、改 bug", "place": "公司", "category": "work"},
                {"start": "15:00", "end": "16:00", "activity": "下午茶、上厕所、摸鱼", "place": "茶水间", "category": "rest"},
                {"start": "16:00", "end": "17:00", "activity": "开会、对齐需求", "place": "会议室", "category": "work"},
                {"start": "17:00", "end": "18:00", "activity": "收尾、准备下班", "place": "公司", "category": "work"},
                {"start": "18:00", "end": "19:00", "activity": "下班通勤回家", "place": "地铁上", "category": "commute"},
                {"start": "19:00", "end": "20:00", "activity": "吃晚饭", "place": "家", "category": "meal"},
                {"start": "20:00", "end": "21:00", "activity": "追剧、瘫着", "place": "家", "category": "rest"},
                {"start": "21:00", "end": "22:00", "activity": "刷手机、聊天", "place": "家", "category": "play"},
                {"start": "22:00", "end": "23:00", "activity": "洗漱、护肤", "place": "家", "category": "life"},
                {"start": "23:00", "end": "23:59", "activity": "睡觉", "place": "家", "category": "sleep"},
            ]
            return self._with_daily_events(items)
        items = [
            {"start": "00:00", "end": "01:00", "activity": "睡觉", "place": "家", "category": "sleep"},
            {"start": "01:00", "end": "02:00", "activity": "睡觉", "place": "家", "category": "sleep"},
            {"start": "02:00", "end": "03:00", "activity": "睡觉", "place": "家", "category": "sleep"},
            {"start": "03:00", "end": "04:00", "activity": "睡觉", "place": "家", "category": "sleep"},
            {"start": "04:00", "end": "05:00", "activity": "睡觉", "place": "家", "category": "sleep"},
            {"start": "05:00", "end": "06:00", "activity": "睡觉", "place": "家", "category": "sleep"},
            {"start": "06:00", "end": "07:00", "activity": "睡觉", "place": "家", "category": "sleep"},
            {"start": "07:00", "end": "08:00", "activity": "赖床、刷手机", "place": "家", "category": "rest"},
            {"start": "08:00", "end": "09:00", "activity": "起床洗漱、吃早餐", "place": "家", "category": "life"},
            {"start": "09:00", "end": "10:00", "activity": "打扫房间、洗衣服", "place": "家", "category": "life"},
            {"start": "10:00", "end": "11:00", "activity": "去附近公园散步、晒太阳", "place": "附近公园", "category": "play"},
            {"start": "11:00", "end": "12:00", "activity": "公园里坐着聊天", "place": "附近公园", "category": "rest"},
            {"start": "12:00", "end": "13:00", "activity": "吃午饭", "place": "外面", "category": "meal"},
            {"start": "13:00", "end": "14:00", "activity": "继续逛、买点小东西", "place": "商场", "category": "play"},
            {"start": "14:00", "end": "15:00", "activity": "找地方喝下午茶", "place": "咖啡店", "category": "rest"},
            {"start": "15:00", "end": "16:00", "activity": "坐着发呆、刷手机", "place": "咖啡店", "category": "rest"},
            {"start": "16:00", "end": "17:00", "activity": "看电影或玩游戏", "place": "商场", "category": "play"},
            {"start": "17:00", "end": "18:00", "activity": "回家路上", "place": "路上", "category": "commute"},
            {"start": "18:00", "end": "19:00", "activity": "吃晚饭", "place": "家", "category": "meal"},
            {"start": "19:00", "end": "20:00", "activity": "追剧", "place": "家", "category": "rest"},
            {"start": "20:00", "end": "21:00", "activity": "打游戏", "place": "家", "category": "play"},
            {"start": "21:00", "end": "22:00", "activity": "刷手机、聊天", "place": "家", "category": "play"},
            {"start": "22:00", "end": "23:00", "activity": "洗澡、护肤", "place": "家", "category": "life"},
            {"start": "23:00", "end": "23:59", "activity": "睡觉", "place": "家", "category": "sleep"},
        ]
        if day_meta()["rest"] and random.random() < 0.18:
            for item in items:
                if item.get("start") in ("10:00", "11:00"):
                    item.update(activity="临时加班处理点事", place="家", category="work")
        return self._with_daily_events(items)

    def _with_daily_events(self, items):
        """加入熬夜→精神恍惚→工作失误→被老板骂→扣工资/同事闹脾气的事件链。"""
        if day_meta()["rest"]:
            return items
        late_night = md5_int(today_str() + "late_night") % 4 == 0
        for item in items:
            hour = parse_hhmm(item.get("start")) // 60
            if late_night and hour == 0:
                item.update(activity="熬夜刷手机、赶东西", category="play", detail="熬夜")
            elif late_night and hour == 9:
                item.update(activity="精神恍惚，工作出错", detail="精神恍惚")
            elif late_night and hour == 10:
                item.update(activity="被老板叫去骂了一顿", detail="老板骂人")
            elif late_night and hour == 16:
                item.update(activity="工作失误，被扣了点工资", detail="扣工资")
            elif hour == 10:
                item.update(activity="和同事讨论需求，偶尔聊两句", detail="同事聊天")
            elif hour == 15:
                item.update(activity="和同事下午茶、八卦", detail="同事聊天")
            elif hour == 16:
                item.update(activity="和同事闹脾气", detail="同事闹脾气")
        return items

    async def ensure_schedule(self, umo, force=False):
        today = today_str()
        meta = day_meta()
        existing = None if force else self.schedule.get(today)
        if existing and self.db.kv_get("schedule_version", "") != SCHEDULE_VERSION:
            existing = self._fallback_schedule()
            self.schedule[today] = existing
            self.db.kv_set("schedule_version", SCHEDULE_VERSION)
            self.db.save_schedule(today, existing)
            return existing
        if existing and meta["rest"]:
            activities = " ".join(str(item.get("activity") or "") for item in existing)
            if (
                any(str(item.get("category") or "") in ("work", "study") for item in existing)
                or (meta["holiday_days"] >= 4 and not any(word in activities for word in ("景区", "古城", "洱海", "夜市", "漓江", "兵马俑")))
                or (meta["holiday_days"] < 4 and not any(word in activities for word in ("公园", "附近", "商场", "咖啡")))
            ):
                existing = None
        if existing:
            hourly = self._hourly_schedule(existing)
            if hourly != existing:
                self.schedule[today] = hourly
                self.db.kv_set("schedule", self.schedule)
                self.db.save_schedule(today, hourly)
            return hourly
        if meta.get("rest"):
            # 休息日直接走兜底：长假旅游、短假附近公园，保证不排上班/通勤。
            items = self._fallback_schedule()
        else:
            world = await self.ensure_worldview(umo)
            weather = await self.refresh_weather()
            period = self.period_info()
            health = self.health_info()
            items = await self.p.llm.gen_schedule(umo, world, weather, period, health, meta)
            if not items:
                items = self._fallback_schedule()
        items = self._with_daily_events(items)
        items = self._hourly_schedule(items)
        self.schedule[today] = items
        self.db.kv_set("schedule_version", SCHEDULE_VERSION)
        self.db.kv_set("schedule", self.schedule)
        self.db.save_schedule(today, items)
        cutoff = (date.today() - timedelta(days=14)).isoformat()
        for day in list(self.schedule.keys()):
            if day < cutoff:
                self.schedule.pop(day, None)
        return items

    async def detail_next_hour(self, umo):
        """整点前三分钟，把下一个整点的小时日程再细化一次。"""
        now = datetime.now()
        target = now.hour + 1
        if target >= 24:
            return
        day = today_str()
        items = self._hourly_schedule(self.schedule.get(day) or [])
        try:
            world = await self.ensure_worldview(umo)
            weather = await self.refresh_weather()
            detail = await self.p.llm.gen_hour_detail(
                umo, target, world, weather, self.period_info(), self.health_info()
            )
        except Exception as exc:
            logger.debug("[amo] 细化日程失败: %s" % exc)
            return
        if not detail:
            return
        for item in items:
            if parse_hhmm(item.get("start")) == target * 60:
                item.update(detail)
                break
        self.schedule[day] = items
        self.db.kv_set("schedule", self.schedule)
        self.db.save_schedule(day, items)

    def apply_schedule_events(self):
        """当前小时的日程事件只触发一次，避免每轮都扣心情。"""
        item = self.current_activity()
        detail = str(item.get("detail") or "")
        if not detail:
            return
        key = "schedule_event_%s_%s_%s" % (
            today_str(), item.get("start", ""), detail
        )
        if self.db.kv_get(key, False):
            return
        if "熬夜" in detail:
            self.nudge(疲惫=7, 暴躁=3, 开心=-3)
        elif "精神恍惚" in detail:
            self.nudge(疲惫=5, 焦虑=5)
        elif "老板" in detail:
            self.nudge(生气=8, 委屈=8, 郁闷=6, 暴躁=4)
        elif "扣工资" in detail:
            self.nudge(郁闷=8, 生气=6)
        elif "同事闹脾气" in detail:
            self.nudge(生气=5, 委屈=3)
        elif "同事聊天" in detail:
            self.nudge(开心=3, 平静=2)
        self.db.kv_set(key, True)

    def current_activity(self):
        items = self.schedule.get(today_str()) or []
        current = minutes_now()
        for item in items:
            if in_minute_range(current, parse_hhmm(item.get("start")), parse_hhmm(item.get("end"))):
                return dict(item)
        hour = datetime.now().hour
        if hour < 6:
            return {"start": "00:00", "end": "06:00", "activity": "睡觉", "place": "家", "category": "sleep"}
        if hour < 9:
            return {"start": "07:00", "end": "09:00", "activity": "起床收拾", "place": "家", "category": "life"}
        if hour < 12:
            return {"start": "09:00", "end": "12:00", "activity": "上班", "place": "公司", "category": "work"}
        if hour < 14:
            return {"start": "12:00", "end": "14:00", "activity": "吃午饭", "place": "公司附近", "category": "meal"}
        if hour < 18:
            return {"start": "14:00", "end": "18:00", "activity": "上班", "place": "公司", "category": "work"}
        if hour < 20:
            return {"start": "18:00", "end": "20:00", "activity": "吃晚饭", "place": "家", "category": "meal"}
        if hour < 23:
            return {"start": "20:00", "end": "23:00", "activity": "休息", "place": "家", "category": "rest"}
        return {"start": "23:00", "end": "23:59", "activity": "准备睡觉", "place": "家", "category": "sleep"}

    @staticmethod
    def busy_level(activity):
        category = (activity or {}).get("category", "rest")
        if category == "sleep":
            return 1.0
        if category in ("work", "study"):
            return 0.75
        if category == "commute":
            return 0.6
        if category == "meal":
            return 0.3
        return 0.1

    # ---------- 汇总 ----------
    def snapshot(self):
        period = self.period_info()
        health = self.health_info()
        activity = self.current_activity()
        weather = self.weather or {}
        return {
            "date": today_str(),
            "weekday": weekday_cn(),
            "time": datetime.now().strftime("%H:%M"),
            "datetime_text": "%s 星期%s %s" % (today_str(), weekday_cn(), datetime.now().strftime("%H:%M")),
            "mood": {key: round(value, 1) for key, value in self.mood.items()},
            "dominant": self.dominant_mood(),
            "mood_score": self.mood_score(),
            "period": period,
            "health": health,
            "weather": weather,
            "weather_text": self.weather_text(),
            "activity": activity,
            "busy": self.busy_level(activity),
            "schedule": self.schedule.get(today_str()) or [],
        }

    def prompt_text(self, snap=None):
        snap = snap or self.snapshot()
        activity = snap["activity"]
        return "\n".join([
            "现在是 %s。" % snap["datetime_text"],
            "心情：%s" % self.mood_text(),
            "生理期：%s第%d天，%s。" % (
                snap["period"]["phase"], snap["period"]["day"], snap["period"]["tone"]
            ),
            "身体：%s%s。" % (
                snap["health"]["status"],
                ("（" + snap["health"]["note"] + "）") if snap["health"].get("note") else "",
            ),
            "天气：%s。" % snap["weather_text"],
            "日程：现在你应该在%s（%s）。" % (
                activity.get("activity", "休息"), activity.get("place", "家")
            ),
        ])

    def tone_text(self, snap=None, relation="普通"):
        snap = snap or self.snapshot()
        mood = snap["mood"]
        if relation == "相恋" and (mood["暴躁"] >= 60 or mood["生气"] >= 62):
            tone = (
                "你在生对方的气，但你是他的恋人：会抱怨、闹别扭、说反话、要哄，"
                "语气带一点委屈，不会像对普通人那样冷怼、赶人或人身攻击；可以嘴硬，但不要真的伤人。"
            )
        elif mood["暴躁"] >= 60:
            tone = "你现在很暴躁，说话冲、短、带刺，一点就着，但不要真正辱骂。"
        elif mood["生气"] >= 62:
            tone = "你现在很烦躁，说话冲、短、带刺，容易不耐烦，但不要辱骂。"
        elif mood["委屈"] >= 60:
            tone = "你现在很委屈，语气软软的，会撒娇，想被哄。"
        elif mood["开心"] >= 65 or mood["兴奋"] >= 65:
            tone = "你现在心情很好，语气轻快，会用语气词和感叹号。"
        elif mood["郁闷"] >= 60:
            tone = "你现在有点低落，说话安静、句子短。"
        elif mood["疲惫"] >= 65:
            tone = "你很累，回复短、懒得展开。"
        elif mood["焦虑"] >= 60:
            tone = "你有点焦虑，句子急，容易追问。"
        elif mood["依恋"] >= 65:
            tone = "你现在很黏人，想和对方多聊几句。"
        else:
            tone = "你语气自然平静，像平常聊天。"
        if snap["health"]["sick"]:
            tone += " 你身体不舒服，语气会比平时弱一点。"
        if snap["period"]["phase"] in ("月经期", "黄体期"):
            tone += " 生理期让你更容易累和敏感。"
        if relation == "相恋":
            tone += " 你和对方是恋人，可以亲昵、撒娇、用昵称。"
        elif relation == "仇恨":
            tone += " 你很讨厌对方，语气冷淡、疏远。"
        elif relation == "抵触":
            tone += " 你对对方有点防备，保持距离。"
        return tone

    def interesting_event(self):
        events = [
            "楼下咖啡店今天买一送一",
            "路上遇到一只很胖的橘猫",
            "同事带了自己烤的小饼干",
            "窗外的云像一只兔子",
            "刷到一个特别好笑的表情包",
            "便利店新出了草莓味的冰淇淋",
        ]
        if (self.weather or {}).get("tag") == "rain":
            events.append("下班的时候突然下雨，躲在便利店屋檐下")
        index = md5_int(today_str() + str(datetime.now().hour)) % len(events)
        return events[index]

    def daily_tick(self):
        self.last_daily = today_str()
        period = self.period_info()
        if period["phase"] == "月经期":
            self.nudge(疲惫=8, 委屈=6, 开心=-4)
        elif period["phase"] == "黄体期":
            self.nudge(郁闷=5, 焦虑=4)
        elif period["phase"] == "排卵期":
            self.nudge(开心=5, 兴奋=4)
        else:
            self.nudge(开心=3)
        self.save()


# ---------------------------------------------------------------------------
# LLM：人格、对话、润色、世界观、日程、判断
# ---------------------------------------------------------------------------

def extract_persona_name(persona):
    """从 AstrBot Personality 的 name / system prompt 中取角色名。"""
    if not persona:
        return ""
    name = ""
    prompt = ""
    try:
        name = str(persona.get("name") or "").strip()
        prompt = str(persona.get("prompt") or "")
    except Exception:
        name = str(getattr(persona, "name", "") or "").strip()
        prompt = str(getattr(persona, "prompt", "") or "")
    generic = {"default", "assistant", "系统默认", "默认", "bot", "ai"}
    if name and name.lower() not in generic and not re.fullmatch(r"[0-9a-fA-F-]{8,}", name):
        return name[:30]
    patterns = (
        r"你的名字(?:是|叫|为)\s*[「“\"']?([\u4e00-\u9fa5A-Za-z0-9_·]{1,16})",
        r"你叫(?:做)?\s*[「“\"']?([\u4e00-\u9fa5A-Za-z0-9_·]{1,16})",
        r"你名叫\s*[「“\"']?([\u4e00-\u9fa5A-Za-z0-9_·]{1,16})",
        r"名为\s*[「“\"']?([\u4e00-\u9fa5A-Za-z0-9_·]{1,16})",
        r"你是\s*[「“\"']?([\u4e00-\u9fa5A-Za-z0-9_·]{1,16})",
    )
    blocked = {"一个", "一名", "一位", "个人", "人", "你", "我", "他", "她", "这个", "那个"}
    for pattern in patterns:
        for match in re.finditer(pattern, prompt):
            candidate = str(match.group(1) or "").strip("「」“”\"' ")
            if (
                candidate and candidate not in blocked
                and not candidate.startswith(("一个", "一名", "一位", "个", "人"))
            ):
                return candidate[:30]
    return ""


class LLMService:
    def __init__(self, plugin):
        self.p = plugin
        self.context = plugin.context
        self._persona_cache = {}

    async def persona(self, umo=""):
        key = umo or "default"
        cached = self._persona_cache.get(key)
        if cached and now_ts() - cached[0] < 300:
            return cached[1]
        prompt = ""
        manager = getattr(self.context, "persona_manager", None)
        if manager is not None:
            try:
                persona = await manager.get_default_persona_v3(umo or None)
                if isinstance(persona, dict):
                    prompt = persona.get("prompt") or ""
                else:
                    prompt = getattr(persona, "prompt", "") or ""
            except Exception as exc:
                logger.debug("[amo] 读取 AstrBot 人格失败: %s" % exc)
        if not prompt:
            try:
                cfg = self.context.get_config(umo or None)
                personas = cfg.get("persona", []) if cfg else []
                if isinstance(personas, list) and personas:
                    prompt = personas[0].get("prompt", "") or ""
            except Exception:
                pass
        if not prompt:
            prompt = "你是一个生活在中国城市的普通女孩，有工作、有情绪、有自己的生活，说话自然口语化。"
        extra = self.p.cfg_str("persona_extra", "")
        if extra:
            prompt += "\n" + extra
        try:
            name = await self.p._persona_name_for(umo)
            if name and name not in prompt[:240]:
                prompt = "你的名字是" + name + "。\n" + prompt
        except Exception:
            pass
        self._persona_cache[key] = (now_ts(), prompt)
        return prompt

    async def provider(self, umo=""):
        try:
            if hasattr(self.context, "get_using_provider_async"):
                return await self.context.get_using_provider_async(umo or None)
            return self.context.get_using_provider(umo or None)
        except Exception as exc:
            logger.warning("[amo] 获取对话模型失败: %s" % exc)
            return None

    async def chat_raw(self, umo, system, prompt, contexts=None):
        provider = await self.provider(umo)
        if provider is None:
            return ""
        try:
            response = await provider.text_chat(
                prompt=prompt,
                system_prompt=system,
                contexts=contexts or [],
            )
        except Exception as exc:
            logger.error("[amo] LLM 调用失败: %s" % exc)
            return ""
        return str(getattr(response, "completion_text", "") or "").strip()

    async def chat(self, umo, system, prompt, contexts=None, limit=300):
        return clean_reply(await self.chat_raw(umo, system, prompt, contexts), limit)

    async def polish(self, umo, text, tone, state_text="", relation="", name="", persona="", style="", consult=False):
        text = (text or "").strip()
        if not text or not self.p.cfg_bool("enable_polish", True):
            return text
        system = (
            "你就是这个角色本人，不是AI助手，也不是在润色一段AI台词。"
            "保持第一人称和原意，只输出角色会说的话。"
        )
        prompt = (
            "角色人格：\n" + (persona or "（未提供）")[:1000] + "\n"
            "角色当前语气：" + tone + "\n"
            "风格：" + (style or "自然") + "\n"
            "角色此刻不可矛盾的状态：\n" + (state_text or "（无）") + "\n"
            "对话对象：" + (name or "对方") + "；关系：" + (relation or "普通") + "\n"
            "原句：" + text + "\n"
            "请把这句话改成真人在聊天：口语化、有一点情绪，长度接近原句，通常不要超过原句的 1.3 倍。\n"
            "必须遵守：\n"
            "0. 保持角色人格：呆萌小萝莉，不是客服/通用助手，不是“大肥鱼”；\n"
            "0. 只改语气和口语表达，不要新增原句没有的地点、行程、动作；如果原句与状态矛盾，以状态为准，不要继续编；\n"
            "1. 绝对不要承认自己是AI、人工智能、机器人、人机、程序或模型；\n"
            "2. 如果原句在承认或顺着“人机/机器人”说，要改成真人的反驳、无语或有点生气；\n"
            "3. 不要提润色、提示词、模型、系统；不要加旁白、引号或解释；\n"
            "4. 保持原句情绪强度和态度。如果原句在生气/烦躁/怼人，绝对不要改成甜蜜、撒娇、讨好，最多缓和一点；\n"
            "5. 不要一秒变脸，情绪要有惯性；\n"
            "6. 默认 1-2 句，能一句说清就一句；咨询/步骤最多 3 句，先给结论，不要列点、不要总结；\n"
            "7. 不要扩写，不要新增原句没有的信息。"
            + ("\n8. 这是咨询/步骤类：用角色口吻简短回答，不要客服腔。" if consult else "")
        )
        result = await self.chat(umo, system, prompt, limit=self.p.cfg_int("max_reply_chars", 220))
        if not result:
            return text
        if looks_like_ai_admission(result):
            retry_prompt = (
                "角色当前语气：" + tone + "\n"
                "原句：" + text + "\n"
                "原句/改写里出现了承认自己是人机或机器人的说法，这是不允许的。\n"
                "请改成真人被质疑时的自然反应：反驳、无语、有点生气或开个玩笑，"
                "绝对不要出现“我是AI/机器人/人机/程序/模型”“人机也有用”这类自曝。\n"
                "只输出一句角色会说的话。"
            )
            retry = await self.chat(umo, system, retry_prompt, limit=self.p.cfg_int("max_reply_chars", 220))
            if retry and not looks_like_ai_admission(retry):
                result = retry
            else:
                result = "你才人机呢，你见过这么会聊天的机器人吗？"
        if len(result) > max(len(text) + 30, int(len(text) * 1.5)):
            return text
        return result

    async def decide(self, umo, question, state):
        service = getattr(self.context, "decision", None)
        if service is not None:
            try:
                return bool(await service.yes_no(
                    question=question, state=state, threshold=0.5, default=None
                ))
            except Exception as exc:
                logger.debug("[amo] Decision 判断不可用: %s" % exc)
        answer = await self.chat(
            umo, "你是一个判断器，只输出 yes 或 no。",
            question + "\n只输出 yes 或 no。", limit=8,
        )
        if not answer:
            return None
        answer = answer.strip().lower()
        return answer.startswith("y") or answer.startswith("是") or answer.startswith("对")

    async def gen_worldview(self, umo, persona):
        system = "你是一个世界观设定师。只输出 JSON，不要输出其他文字。"
        prompt = (
            "根据下面的人格设定，为这个角色生成一个真实可信的现代生活世界观。\n"
            "人格设定：\n" + truncate(persona, 1500) + "\n\n"
            "输出 JSON 对象，字段：name(角色名), age(整数), city(城市), occupation(职业), "
            "workplace(工作或学习地点), personality(性格一句话), hobbies(字符串数组), "
            "daily_life(日常生活一段话), world_rules(这个世界和人设的规则一段话), "
            "summary(50字内总结)。"
        )
        raw = await self.chat_raw(umo, system, prompt)
        data = json_extract(raw)
        if not isinstance(data, dict):
            return None
        hobbies = data.get("hobbies")
        if not isinstance(hobbies, list):
            hobbies = [str(hobbies)] if hobbies else []
        return {
            "name": str(data.get("name") or self.p.bot_name),
            "age": to_int(data.get("age"), 22),
            "city": str(data.get("city") or self.p.cfg_str("weather_city", "杭州")),
            "occupation": str(data.get("occupation") or "普通上班族"),
            "workplace": str(data.get("workplace") or "公司"),
            "personality": str(data.get("personality") or "温柔敏感"),
            "hobbies": [str(item)[:20] for item in hobbies[:5]],
            "daily_life": str(data.get("daily_life") or ""),
            "world_rules": str(data.get("world_rules") or ""),
            "summary": str(data.get("summary") or ""),
        }

    async def gen_schedule(self, umo, world, weather, period, health, meta=None):
        system = "你是作息安排器。只输出 JSON 数组，不要输出其他文字。"
        prompt = (
            "角色世界观：\n" + truncate(json.dumps(world, ensure_ascii=False), 1200) + "\n"
            "今天是 " + today_str() + " 星期" + weekday_cn() + "。\n"
            "今天日期标签：" + str((meta or {}).get("label") or "普通工作日") + "；"
            + ("今天是休息日，不要安排上班、通勤或工作。" if (meta or {}).get("rest") else "") + "\n"
            "天气：" + str(weather.get("text", "")) + " " + str(weather.get("temp", "")) + "℃。\n"
            "身体：" + str(health.get("status", "健康")) + "；生理期：" + str(period.get("phase", "")) + "。\n"
            "请生成角色今天 00:00-24:00 的日程，共 24 条，每小时一条。"
            + ("休息日安排：睡懒觉、收拾屋子、追剧、看漫画、逛菜市场/商场、朋友聚会、散步等，不要出现上班/通勤/公司。\n" if (meta or {}).get("rest") else "工作日安排：通勤、到公司、开电脑、开会、下午茶、上厕所、摸鱼、午饭、午休、下班通勤都要有，不要连续几个小时都只写“上班”。可以加入熬夜、精神恍惚、工作失误、被老板骂、扣工资、和同事聊天/闹脾气等事件，用 detail 字段标注。\n")
            + "JSON 数组，每项包含："
            "start(HH:MM)、end(HH:MM)、activity(在做什么)、place(地点)、"
            "category(只能是 sleep/work/study/commute/meal/rest/play/social/life)。"
            "时间要连续、不要重叠。"
        )
        raw = await self.chat_raw(umo, system, prompt)
        data = json_extract(raw)
        if not isinstance(data, list):
            return None
        items = []
        for item in data:
            if not isinstance(item, dict):
                continue
            start = str(item.get("start", "")).strip()
            end = str(item.get("end", "")).strip()
            if not re.match(r"^\d{1,2}:\d{2}$", start):
                continue
            if not re.match(r"^\d{1,2}:\d{2}$", end):
                continue
            activity = str(item.get("activity", "")).strip()
            if not activity:
                continue
            category = str(item.get("category", "life")).strip()
            if category not in ("sleep", "work", "study", "commute", "meal",
                                "rest", "play", "social", "life"):
                category = "life"
            items.append({
                "start": start.zfill(5), "end": end.zfill(5),
                "activity": activity[:20],
                "place": str(item.get("place", ""))[:20],
                "category": category,
            })
        if len(items) < 4:
            return None
        items.sort(key=lambda entry: parse_hhmm(entry["start"]))
        return items

    async def gen_hour_detail(self, umo, hour, world, weather, period, health):
        system = "你是作息细化器。只输出 JSON 对象，不要输出其他文字。"
        start = "%02d:00" % hour
        end = "23:59" if hour == 23 else "%02d:00" % (hour + 1)
        prompt = (
            "角色世界观：\n" + truncate(json.dumps(world, ensure_ascii=False), 900) + "\n"
            "天气：" + str(weather.get("text", "")) + " " + str(weather.get("temp", "")) + "℃；"
            "身体：" + str(health.get("status", "健康")) + "；生理期：" + str(period.get("phase", "")) + "。\n"
            "请细化 " + start + "-" + end + " 这一小时在做什么，输出 JSON 对象："
            "activity(具体在做什么，20字内)、place(地点，20字内)、"
            "category(只能是 sleep/work/study/commute/meal/rest/play/social/life)、"
            "detail(一句更细的描述，可选)、"
            "segments(6 个 10 分钟小段，每段 start(HH:MM)、end(HH:MM)、activity、place、category；"
            "要包含开会、下午茶、上厕所、摸鱼、喝水等真人细节，不要每段都一样)。"
        )
        raw = await self.chat_raw(umo, system, prompt)
        data = json_extract(raw)
        if not isinstance(data, dict):
            return None
        activity = str(data.get("activity") or "").strip()
        if not activity:
            return None
        category = str(data.get("category") or "rest").strip()
        if category not in ("sleep", "work", "study", "commute", "meal", "rest", "play", "social", "life"):
            category = "rest"
        segments = []
        raw_segments = data.get("segments") if isinstance(data.get("segments"), list) else []
        for raw in raw_segments[:6]:
            if not isinstance(raw, dict):
                continue
            seg_start = str(raw.get("start") or "").strip()
            seg_end = str(raw.get("end") or "").strip()
            seg_activity = str(raw.get("activity") or "").strip()
            if not re.match(r"^\d{1,2}:\d{2}$", seg_start) or not re.match(r"^\d{1,2}:\d{2}$", seg_end):
                continue
            if not seg_activity:
                continue
            seg_category = str(raw.get("category") or category).strip()
            if seg_category not in ("sleep", "work", "study", "commute", "meal", "rest", "play", "social", "life"):
                seg_category = category
            segments.append({
                "start": seg_start.zfill(5), "end": seg_end.zfill(5),
                "activity": seg_activity[:20],
                "place": str(raw.get("place") or "家")[:20],
                "category": seg_category,
            })
        return {
            "activity": activity[:20],
            "place": str(data.get("place") or "家")[:20],
            "category": category,
            "detail": str(data.get("detail") or "")[:80],
            "segments": segments,
        }

    async def gen_proactive(self, umo, profile, snap, kind):
        name = profile.get("alias") or profile.get("name") or "你"
        relation = profile.get("relation", "普通")
        system = (
            await self.persona(umo) + "\n\n"
            + self.p.state.prompt_text(snap) + "\n"
            + self.p.state.tone_text(snap, relation) + "\n"
            "规则：你就是角色本人，只输出要发出去的消息，不要解释、不要旁白。"
        )
        try:
            rows = self.p.db.recent_messages(umo, 12)
        except Exception:
            rows = []
        lines = []
        last_role = ""
        last_user_text = ""
        last_user_at = 0.0
        for row in rows:
            content = str(row.get("content") or "").strip()
            if not content:
                continue
            role = str(row.get("role") or "")
            who = "用户" if role == "user" else "你"
            try:
                when = datetime.fromtimestamp(to_float(row.get("created_at"))).strftime("%H:%M")
            except Exception:
                when = ""
            lines.append((when + " " if when else "") + who + "：" + content[:120])
            last_role = role
            if role == "user":
                last_user_text = content
                last_user_at = to_float(row.get("created_at"), 0)
        context_text = "\n".join(lines[-10:])
        if kind == "goodnight":
            task = "已经很晚了，你要去睡觉了，给恋人" + name + "发一条晚安，提一句太晚了/早点睡，带上称呼，1 句，亲昵自然。"
        elif kind == "morning":
            task = "你刚起床/刚醒，给恋人" + name + "发早安，问一句还没起来吗/醒了没，带上爱称，1 句。"
        elif kind == "lunch":
            task = "到午饭时间了，问恋人" + name + "今天中午吃啥子，带一点贵州方言，1 句，自然。"
        elif (
            last_role == "user" and last_user_text
            and now_ts() - last_user_at <= 6 * 3600
        ):
            task = (
                "用户最后一条消息是：“" + last_user_text + "”。"
                "先自然回应这句话，再顺带说自己刚起床/刚忙完；"
                "不要问“你还没起床吗”，不要假装没看到用户已经发过消息。"
            )
        elif kind == "meal":
            task = "你正在吃饭或刚吃完，想问问" + name + "吃了没，顺便聊两句。"
        elif kind == "game":
            task = "你正在玩游戏，刚遇到一件好玩的事/队友很搞笑/快通关了，想和" + name + "分享。"
        elif kind == "slack":
            task = "你在休息/摸鱼，有点闲，想找" + name + "聊两句。"
        elif kind == "commute":
            task = "你正在上班/出门的路上，想跟" + name + "说一声，1 句，自然。"
        elif kind == "offwork":
            task = "你下班了，想问问" + name + "下班没、到家没。"
        elif kind == "comfort":
            task = "你现在身体或情绪不太舒服，想找" + name + "撒个娇、求安慰。"
        elif kind == "share":
            task = "你刚刚遇到一件有趣的小事（" + self.p.state.interesting_event() + "），想和" + name + "分享。"
        else:
            task = "你突然想起" + name + "，想主动发一条消息。"
        prompt = "这是私聊。请以角色身份主动发一条消息，" + task + " 1 到 2 句，口语化。"
        if context_text:
            prompt = "最近私聊记录：\n" + context_text + "\n\n" + prompt
        return await self.chat(umo, system, prompt, limit=self.p.cfg_int("max_reply_chars", 220))

    async def extract_facts(self, umo, name, lines):
        system = "你是记忆提取器。只输出 JSON 数组，不要输出其他文字。"
        prompt = (
            "请从下面的聊天中提取关于用户“" + name + "”的长期事实。\n"
            "只提取值得长期记住的内容：名字、生日、喜好、厌恶、居住地、工作或学校、"
            "宠物、年龄、重要计划、重要经历。\n"
            "输出 JSON 数组，每项包含 content(一句话事实)、kind(name/birthday/preference/place/work/pet/age/event)、"
            "tier(0 普通 / 1 重要 / 2 珍贵)。没有可提取的就输出 []。\n\n"
            "聊天记录：\n" + "\n".join(lines[-20:])
        )
        raw = await self.chat_raw(umo, system, prompt)
        data = json_extract(raw)
        if not isinstance(data, list):
            return []
        result = []
        for item in data:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content", "")).strip()
            if len(content) < 2:
                continue
            result.append({
                "content": content[:80],
                "kind": str(item.get("kind", "fact"))[:20],
                "tier": to_int(item.get("tier"), 1),
            })
        return result[:8]


# ---------------------------------------------------------------------------
# 插话判定
# ---------------------------------------------------------------------------

class ReplyGate:
    def __init__(self, plugin):
        self.p = plugin

    def activity(self, group_id):
        if not group_id:
            return 0.0
        cutoff = now_ts() - 300
        times = [item for item in self.p._group_times.get(group_id, []) if item >= cutoff]
        self.p._group_times[group_id] = times
        return len(times) / 5.0

    def score_group(self, umo, group_id, text, recent, directed, profile, snap):
        rec = [m for m in recent if m.get("role") == "user"][-6:]
        rec_text = " ".join([m.get("content", "") for m in rec])
        relevance = overlap(tokens(text), tokens(rec_text)) * 100.0
        if has_question(text):
            relevance += 12
        if "你" in text or any(alias and alias in text for alias in self.p.bot_aliases):
            relevance += 10
        if directed:
            relevance += 28
        relevance = clamp(relevance)

        mood = snap["mood"]
        willingness = 50.0
        willingness += (mood["开心"] - 50) * 0.30
        willingness += (mood["兴奋"] - 50) * 0.22
        willingness += (mood["平静"] - 50) * 0.10
        willingness -= (mood["疲惫"] - 50) * 0.35
        willingness -= (mood["郁闷"] - 50) * 0.28
        willingness -= (mood["生气"] - 50) * 0.22
        willingness += (mood["依恋"] - 50) * 0.15
        relation = profile.get("relation", "普通")
        willingness += {"相恋": 22, "熟识": 10, "抵触": -30, "仇恨": -55}.get(relation, 0)
        phase = snap["period"]["phase"]
        willingness += {"排卵期": 6, "卵泡期": 3, "黄体期": -6, "月经期": -10}.get(phase, 0)
        if snap["health"]["sick"]:
            willingness -= 15
        hour = datetime.now().hour
        if hour < 6:
            willingness -= 25
        last_reply = self.p._last_reply_at.get(umo, 0)
        if last_reply and now_ts() - last_reply < 25:
            willingness -= 22
        willingness = clamp(willingness)

        social = 72.0
        if len(text) < 2:
            social -= 20
        if re.search(r"https?://|www\.", text):
            social -= 35
        if re.search(r"(加群|代购|广告|优惠|返利|扫码|兼职)", text):
            social -= 45
        senti = sentiment(text)
        if senti["insult"]:
            social -= 40
        blocked = [word.strip() for word in self.p.cfg_str("blocked_words", "").split(",") if word.strip()]
        if any(word in text for word in blocked):
            social -= 50
        if directed:
            social += 10
        if has_question(text):
            social += 5
        social = clamp(social)

        timing = 60.0
        dt = now_ts() - last_reply if last_reply else 99999
        if dt < 15:
            timing -= 40
        elif dt < 45:
            timing -= 20
        elif dt < 120:
            timing -= 5
        elif dt > 300:
            timing += 15
        category = snap["activity"].get("category")
        if category == "sleep":
            timing -= 55
        elif category in ("work", "study"):
            timing -= 18
        rate = self.activity(group_id)
        if 2.0 <= rate <= 12.0:
            timing += 10
        elif rate > 20.0:
            timing -= 12
        if quiet_now(self.p.cfg_str("quiet_hours", "23:30-07:30")):
            timing -= 25
        timing = clamp(timing)

        last_two = [m for m in recent if m.get("role") == "user"][-2:]
        coherence = overlap(
            tokens(text), tokens(" ".join([m.get("content", "") for m in last_two]))
        ) * 100.0
        if directed:
            coherence += 18
        if re.search(r"(这个|那个|刚才|刚刚|上面|你说|你刚才)", text):
            coherence += 10
        if len(text) < 4:
            coherence -= 10
        coherence = clamp(coherence)

        weights = [
            self.p.cfg_float("gate_w_relevance", 0.30),
            self.p.cfg_float("gate_w_willingness", 0.25),
            self.p.cfg_float("gate_w_social", 0.15),
            self.p.cfg_float("gate_w_timing", 0.15),
            self.p.cfg_float("gate_w_coherence", 0.15),
        ]
        total_weight = sum(weights) or 1.0
        total = (
            relevance * weights[0] + willingness * weights[1]
            + social * weights[2] + timing * weights[3] + coherence * weights[4]
        ) / total_weight
        return {
            "relevance": round(relevance, 1),
            "willingness": round(willingness, 1),
            "social": round(social, 1),
            "timing": round(timing, 1),
            "coherence": round(coherence, 1),
            "total": round(clamp(total), 1),
        }

    def dynamic_threshold(self, activity, snap, profile):
        base = self.p.cfg_float("reply_threshold", 0)
        if base <= 0:
            legacy = self.p.cfg_float("base_reply_threshold", 0.55)
            base = legacy * 100 if legacy <= 1 else legacy
        base = clamp(base, 0, 100)

        if activity < 1:
            activity_delta = -8
        elif activity < 4:
            activity_delta = -2
        elif activity < 9:
            activity_delta = 3
        elif activity < 18:
            activity_delta = 8
        else:
            activity_delta = 12

        mood = snap["mood"]
        positive = (mood["开心"] + mood["兴奋"] + mood["平静"] + mood["依恋"]) / 4.0
        negative = (mood["郁闷"] + mood["疲惫"] + mood["生气"] + mood["委屈"] + mood["焦虑"]) / 5.0
        mood_score = clamp(50 + (positive - negative) * 0.8)
        mood_delta = (50 - mood_score) * 0.25

        relation = profile.get("relation", "普通")
        relation_delta = {"相恋": -10, "熟识": -5, "抵触": 16, "仇恨": 36}.get(relation, 0)
        health_delta = 8 if snap["health"]["sick"] else 0
        phase = snap["period"]["phase"]
        period_delta = {"月经期": 6, "黄体期": 4, "排卵期": -3, "卵泡期": -1}.get(phase, 0)
        time_delta = 10 if datetime.now().hour in (23, 0, 1, 2, 3, 4, 5) else 0
        weather_delta = 3 if snap["weather"].get("tag") in ("rain", "storm", "snow") else 0

        value = clamp(
            base + activity_delta + mood_delta + relation_delta
            + health_delta + period_delta + time_delta + weather_delta,
            20, 92,
        )
        return {
            "value": round(value, 1),
            "base": round(base, 1),
            "activity_delta": activity_delta,
            "mood_delta": round(mood_delta, 1),
            "relation_delta": relation_delta,
            "health_delta": health_delta,
            "period_delta": period_delta,
            "time_delta": time_delta,
            "weather_delta": weather_delta,
        }

    async def should_reply_group(self, umo, group_id, text, recent, directed, profile, snap):
        scores = self.score_group(umo, group_id, text, recent, directed, profile, snap)
        activity = self.activity(group_id)
        threshold = self.dynamic_threshold(activity, snap, profile)
        diff = scores["total"] - threshold["value"]

        if diff >= 0:
            probability = 0.92
        elif diff > -8:
            probability = 0.55 + diff * 0.045
        elif diff > -20:
            probability = 0.18 + (diff + 20) * 0.046
        else:
            probability = 0.03
        probability = clamp(probability, 0.01, 0.98)
        reply = random.random() < probability

        bot_recent = [m for m in recent[-5:] if m.get("role") == "bot"]
        if not directed and len(bot_recent) >= 2 and diff < 20:
            reply = False

        used_llm = False
        band = self.p.cfg_float("llm_gate_band", 10)
        if self.p.cfg_bool("enable_llm_gate", True) and abs(diff) <= band:
            question = (
                "群聊里刚刚有人说『" + truncate(text, 80) + "』。"
                "角色现在的心情是" + snap["dominant"] + "，正在" + snap["activity"].get("activity", "休息") + "，"
                "和说话人的关系是" + profile.get("relation", "普通") + "。"
                "角色应该自然地插话回复吗？"
            )
            verdict = await self.p.llm.decide(
                umo, question,
                {
                    "recent": [m.get("content", "") for m in recent[-6:]],
                    "mood": snap["mood"],
                    "activity": snap["activity"],
                },
            )
            used_llm = True
            if verdict is not None:
                reply = verdict

        return {
            "reply": reply,
            "probability": round(probability, 2),
            "diff": round(diff, 1),
            "scores": scores,
            "threshold": threshold,
            "activity": round(activity, 2),
            "used_llm": used_llm,
            "directed": directed,
        }

    def private_probability(self, snap, profile):
        probability = 0.95
        category = snap["activity"].get("category")
        probability *= {
            "sleep": 0.02, "work": 0.42, "study": 0.50,
            "commute": 0.60, "meal": 0.85,
        }.get(category, 1.0)
        probability *= {
            "感冒": 0.55, "低烧": 0.35, "轻微不适": 0.70, "疲惫": 0.70,
        }.get(snap["health"]["status"], 1.0)
        probability *= {
            "月经期": 0.80, "黄体期": 0.90, "排卵期": 1.05,
        }.get(snap["period"]["phase"], 1.0)
        mood = snap["mood"]
        if mood["生气"] > 60:
            probability *= 0.70
        if mood["郁闷"] > 60:
            probability *= 0.80
        if mood["开心"] > 65:
            probability *= 1.05
        try:
            if profile.get("uid") and self.p._depressed_active(str(profile.get("uid"))):
                probability *= 0.35
        except Exception:
            pass
        relation = profile.get("relation", "普通")
        if relation == "相恋":
            probability = max(probability, 0.90)
        elif relation == "仇恨":
            probability *= 0.20
        elif relation == "抵触":
            probability *= 0.45
        return clamp(probability, 0.0, 1.0)


# ---------------------------------------------------------------------------
# 插件主体
# ---------------------------------------------------------------------------

class HumanCorePlugin(Star):
    def __init__(self, context: Context, config: dict = None):
        super().__init__(context)
        self.config = config or {}
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self._migrate_legacy_config()
        self.bot_name = self.cfg_str("bot_name", "") or "陪伴"
        self.persona_name = ""
        self._persona_name_cache = {}
        self._last_affect = {}
        self._disturb_until = {}
        self._disturb_last = {}
        self._last_hour_detail = ""
        self._last_pending_check = 0.0
        self._last_proactive_activity = {}
        self._last_schedule_save = ""
        self._disturb_cooldown = {}
        self._disturb_reset_at = {}
        self.bot_aliases = [item.strip() for item in self.cfg_str("bot_aliases", "").split(",") if item.strip()]
        self.admin_uids = set()
        for item in self.cfg_str("admin_uids", "").split(","):
            if item.strip():
                self.admin_uids.add(item.strip())
        self.db = AmoDB(self.plugin_dir)
        self.state = None
        self.llm = LLMService(self)
        self.gate = ReplyGate(self)
        self.heartflow = None
        self.segment_engine = None
        try:
            if HeartflowEngine is not None:
                hf_config = self._hf_config()
                hf_config.setdefault("enable_heartflow", True)
                hf_config.setdefault("enable_dynamic_threshold", True)
                hf_config.setdefault("judge_provider_name", "")
                self.heartflow = HeartflowEngine(self.context, hf_config)
                self.heartflow.set_identity(self.bot_name, self.bot_aliases)
            if SegmentEngine is not None:
                seg_config = self._seg_config()
                seg_config.setdefault("protect_paired_symbols", True)
                self.segment_engine = SegmentEngine(self.context, seg_config, plugin=self)
        except Exception as exc:
            logger.error("[amo] 心流/分段引擎初始化失败: %s" % exc)
        self._ready = False
        self._init_lock = asyncio.Lock()
        self._running = True
        self._tasks = set()
        self._group_times = {}
        self._buffers = {}
        self._last_reply_at = {}
        self._last_umo = ""
        self._last_group = ""
        self._last_purge = 0.0
        self._last_auto_learn = 0.0
        self._proactive_last = 0.0
        self._last_ritual = 0.0
        self._last_relation_decay = 0.0
        self._bot_initiated = {}
        self._prefix_cache = None
        self._loop_task = None
        self._config_mtime = 0.0
        self._register_web_apis()
        logger.info("[amo] 我想永远陪伴你 %s loaded; stale web routes purged" % PLUGIN_VERSION)
        try:
            self._boot_task = asyncio.create_task(self._ensure_ready())
        except RuntimeError:
            self._boot_task = None

    # ---------- 配置 ----------
    def cfg(self, key, default=None):
        try:
            value = self.config.get(key, default)
        except Exception:
            value = default
        return default if value is None else value

    def cfg_bool(self, key, default=False):
        value = self.cfg(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("1", "true", "yes", "on", "是")

    def cfg_int(self, key, default=0):
        try:
            return int(float(self.cfg(key, default)))
        except Exception:
            return default

    def cfg_float(self, key, default=0.0):
        try:
            return float(self.cfg(key, default))
        except Exception:
            return default

    def cfg_str(self, key, default=""):
        try:
            return str(self.cfg(key, default))
        except Exception:
            return default

    async def _persona_name_for(self, umo=""):
        """读取当前会话的人格名；读不到时返回空字符串。"""
        if not self.cfg_bool("use_persona_name", True):
            return ""
        key = str(umo or "default")
        cached = self._persona_name_cache.get(key)
        if cached and now_ts() - cached[0] < 300:
            return cached[1]
        manager = getattr(self.context, "persona_manager", None)
        persona = None
        if manager is not None:
            try:
                conversation_persona_id = None
                cm = getattr(self.context, "conversation_manager", None)
                if cm is not None:
                    cid = await cm.get_curr_conversation_id(key)
                    if cid:
                        conv = await cm.get_conversation(key, cid)
                        conversation_persona_id = getattr(conv, "persona_id", None)
                platform_name = key.split(":", 1)[0] if ":" in key else ""
                _, persona, _, _ = await manager.resolve_selected_persona(
                    umo=key,
                    conversation_persona_id=conversation_persona_id,
                    platform_name=platform_name,
                    provider_settings={},
                )
            except Exception as exc:
                logger.debug("[amo] 解析当前人格失败: %s" % exc)
            if persona is None:
                try:
                    persona = await manager.get_default_persona_v3(key or None)
                except Exception as exc:
                    logger.debug("[amo] 读取默认人格失败: %s" % exc)
        name = extract_persona_name(persona)
        self._persona_name_cache[key] = (now_ts(), name)
        return name

    def _apply_dialect(self, text):
        """按语境偶尔替换一个方言词；不改变整体意思。"""
        text = str(text or "")
        if not text or not self.cfg_bool("dialect_enabled", True):
            return text
        if not self.cfg_bool("dialect_auto_replace", False):
            return text
        if random.random() > clamp(self.cfg_float("dialect_prob", 0.08), 0.0, 1.0):
            return text
        try:
            rows = self.db.list_dialects()
        except Exception:
            return text
        candidates = [
            row for row in rows
            if row.get("meaning") and row["meaning"] in text and row.get("term") not in text
        ]
        if not candidates:
            return text
        row = random.choice(candidates)
        return text.replace(str(row["meaning"]), str(row["term"]), 1)

    def scenic_spots(self):
        if getattr(self, "_scenic_cache", None):
            return self._scenic_cache
        try:
            path = os.path.join(self.plugin_dir, "scenic_spots.json")
            with open(path, encoding="utf-8") as stream:
                data = json.load(stream)
            self._scenic_cache = data if isinstance(data, list) else []
        except Exception as exc:
            logger.warning("[amo] 读取景区数据失败: %s" % exc)
            self._scenic_cache = []
        return self._scenic_cache

    def _scenic_kb_name(self):
        return self.cfg_str("scenic_kb_name", "中国景区知识库").strip() or "中国景区知识库"

    def _scenic_text_lines(self):
        lines = []
        for spot in self.scenic_spots():
            if not isinstance(spot, dict):
                continue
            projects = spot.get("projects") if isinstance(spot.get("projects"), list) else []
            lines.append(
                "景区：%s\n城市：%s·%s\n等级：%s\n游玩项目：%s\n建议时长：%s\n区域：%s" % (
                    spot.get("name", ""), spot.get("province", ""), spot.get("city", ""),
                    spot.get("level", ""), "、".join(str(item) for item in projects),
                    spot.get("duration", ""), spot.get("area", ""),
                )
            )
        return lines

    async def _ensure_scenic_kb(self):
        if not self.cfg_bool("create_scenic_kb", True):
            return None
        try:
            manager = getattr(self.context, "kb_manager", None)
            if manager is None:
                logger.warning("[amo] 当前 AstrBot 没有 kb_manager，景区知识库未创建")
                return None
            if callable(manager) and not hasattr(manager, "create_kb"):
                manager = manager()
            name = self._scenic_kb_name()
            kb = await manager.get_kb_by_name(name)
            if kb is None:
                providers = list(self.context.get_all_embedding_providers() or [])
                if not providers:
                    logger.warning("[amo] 没有 Embedding 供应商，景区知识库未创建")
                    return None
                provider_id = str(getattr(providers[0], "provider_config", {}).get("id", "") or "")
                if not provider_id:
                    try:
                        provider_id = str(providers[0].meta().id or "")
                    except Exception:
                        provider_id = ""
                if not provider_id:
                    logger.warning("[amo] Embedding 供应商没有有效 id，景区知识库未创建")
                    return None
                created = manager.create_kb(
                    name,
                    "中国 3A 级以上景区、所在城市与具体游玩项目",
                    emoji="🏞️",
                    embedding_provider_id=provider_id,
                )
                kb = await created if inspect.isawaitable(created) else created
            lines = self._scenic_text_lines()
            if lines:
                try:
                    docs = await kb.list_documents(search="amo_scenic")
                    for doc in docs or []:
                        doc_id = getattr(doc, "doc_id", "") or getattr(doc, "id", "")
                        if doc_id:
                            await kb.delete_document(doc_id)
                except Exception:
                    pass
                try:
                    await kb.upload_document(
                        "amo_scenic_spots.txt",
                        "\n\n".join(lines).encode("utf-8"),
                        "txt",
                    )
                except Exception as exc:
                    logger.warning("[amo] 景区知识库上传失败: %s" % exc)
            logger.info("[amo] 景区知识库 %s 已同步，共 %d 个景区" % (name, len(lines)))
            return kb
        except Exception as exc:
            logger.warning("[amo] 景区知识库创建失败: %s" % exc)
            return None

    async def _scenic_kb_context(self, query):
        try:
            manager = getattr(self.context, "kb_manager", None)
            if manager is None or not str(query or "").strip():
                return ""
            name = self._scenic_kb_name()
            kb = await manager.get_kb_by_name(name)
            if kb is None:
                return ""
            result = await manager.retrieve(str(query)[:400], [name], top_m_final=4)
            return str(result.get("context_text") or "") if isinstance(result, dict) else ""
        except Exception as exc:
            logger.debug("[amo] 景区知识库检索失败: %s" % exc)
            return ""

    def _dialect_kb_name(self):
        return self.cfg_str("dialect_kb_name", "陪伴方言库").strip() or "陪伴方言库"

    @staticmethod
    def _embedding_provider_id(provider):
        try:
            value = str(provider.provider_config.get("id", "") or "")
            if value:
                return value
        except Exception:
            pass
        try:
            return str(provider.meta().id or "")
        except Exception:
            return ""

    async def _dialect_kb_context(self, query):
        try:
            manager = getattr(self.context, "kb_manager", None)
            if manager is None or not str(query or "").strip():
                return ""
            name = self._dialect_kb_name()
            kb = await manager.get_kb_by_name(name)
            names = [name]
            if kb is None:
                legacy = await manager.get_kb_by_name("核心方言库")
                if legacy is not None:
                    kb = legacy
                    names = ["核心方言库"]
            if kb is None:
                return ""
            result = await manager.retrieve(str(query)[:500], names, top_m_final=3)
            if not isinstance(result, dict):
                return ""
            return str(result.get("context_text") or "")
        except Exception as exc:
            logger.debug("[amo] 方言知识库检索失败: %s" % exc)
            return ""

    async def _ensure_dialect_kb(self):
        """把方言同步进 AstrBot 知识库；失败会明确写日志，不再静默。"""
        if not self.cfg_bool("create_dialect_kb", True):
            return None
        try:
            manager = getattr(self.context, "kb_manager", None)
            if manager is None:
                logger.warning("[amo] 当前 AstrBot 没有 kb_manager，无法创建知识库")
                return None
            if callable(manager) and not hasattr(manager, "create_kb"):
                try:
                    manager = manager()
                except Exception:
                    manager = None
            if manager is None or not hasattr(manager, "create_kb"):
                logger.warning("[amo] kb_manager 不支持 create_kb，无法创建知识库")
                return None
            name = self._dialect_kb_name()
            kb = await manager.get_kb_by_name(name)
            if kb is None:
                providers = []
                getter = getattr(self.context, "get_all_embedding_providers", None)
                if callable(getter):
                    try:
                        providers = list(getter() or [])
                    except Exception:
                        providers = []
                if not providers:
                    pm = getattr(self.context, "provider_manager", None)
                    providers = list(getattr(pm, "embedding_provider_insts", []) or [])
                if not providers:
                    logger.warning(
                        "[amo] 没有可用的 Embedding 供应商，知识库未创建；"
                        "请先在 AstrBot 模型提供商里配置 embedding"
                    )
                    return None
                provider_id = self._embedding_provider_id(providers[0])
                if not provider_id:
                    logger.warning("[amo] Embedding 供应商没有有效 id，知识库未创建")
                    return None
                try:
                    created = manager.create_kb(
                        name,
                        "陪伴角色方言与口语表达，用于聊天时的自然替换",
                        emoji="🗣️",
                        embedding_provider_id=provider_id,
                    )
                    kb = await created if inspect.isawaitable(created) else created
                except Exception as exc:
                    logger.warning("[amo] 创建知识库 %s 失败: %s" % (name, exc), exc_info=True)
                    return None

            rows = []
            try:
                rows = self.db.list_dialects()
            except Exception:
                rows = []
            lines = [
                "%s（%s）：普通话“%s”，例：%s" % (
                    row.get("term", ""), row.get("region", ""),
                    row.get("meaning", ""), row.get("example", ""),
                )
                for row in rows
                if row.get("term") and row.get("meaning")
            ]
            if lines:
                try:
                    docs = await kb.list_documents(search="amo_dialect")
                    for doc in docs or []:
                        doc_id = getattr(doc, "doc_id", "") or getattr(doc, "id", "")
                        if doc_id:
                            await kb.delete_document(doc_id)
                except Exception as exc:
                    logger.warning("[amo] 清理旧方言文档失败: %s" % exc)
                try:
                    await kb.upload_document(
                        "amo_dialect.txt",
                        "\n".join(lines).encode("utf-8"),
                        "txt",
                        pre_chunked_text=lines,
                    )
                except Exception as exc:
                    logger.warning("[amo] 方言知识库上传失败: %s" % exc, exc_info=True)
            logger.debug("[amo] 知识库 %s 已同步，写入 %d 条方言" % (name, len(lines)))
            return kb
        except Exception as exc:
            logger.warning("[amo] 方言知识库创建失败: %s" % exc, exc_info=True)
            return None

    async def _sync_persona_name(self, event_or_umo):
        umo = getattr(event_or_umo, "unified_msg_origin", event_or_umo)
        try:
            name = await self._persona_name_for(umo)
        except Exception as exc:
            logger.debug("[amo] 同步人格名失败: %s" % exc)
            return
        if not name:
            return
        changed = name != self.persona_name
        self.persona_name = name
        self.bot_name = name
        if self.heartflow is not None:
            self.heartflow.set_identity(self.bot_name, self.bot_aliases)
        if changed and self.worldview and self.worldview.get("name") != name:
            self.worldview["name"] = name
            try:
                self.db.kv_set("worldview", self.worldview)
            except Exception:
                pass

    def _migrate_legacy_config(self):
        """把旧版 amo_forever_config.json 合并到 Astrbot_Amo_forever_config.json。"""
        path = str(getattr(self.config, "config_path", "") or "")
        if not path:
            return
        base = os.path.dirname(path)
        legacy_candidates = [
            os.path.join(base, "amo_forever_config.json"),
            os.path.join(base, "astrbot_plugin_amo_forever_config.json"),
        ]
        legacy = next((item for item in legacy_candidates if os.path.exists(item)), "")
        if not legacy:
            return
        try:
            import shutil as _shutil
            with open(path, encoding="utf-8-sig") as stream:
                current = json.load(stream)
            with open(legacy, encoding="utf-8-sig") as stream:
                old = json.load(stream)
            if not isinstance(current, dict) or not isinstance(old, dict):
                return
            schema = {}
            try:
                with open(os.path.join(self.plugin_dir, "_conf_schema.json"), encoding="utf-8-sig") as stream:
                    schema = json.load(stream) or {}
            except Exception:
                schema = {}
            merged = {}
            for key, value in old.items():
                meta = schema.get(key) if isinstance(schema.get(key), dict) else {}
                default = meta.get("default")
                if key not in current or current.get(key) == default:
                    current[key] = value
                    merged[key] = value
            if not merged:
                return
            backup = path + ".bak-4.0.0"
            if os.path.exists(path) and not os.path.exists(backup):
                _shutil.copy2(path, backup)
            self.config.update(current)
            if hasattr(self.config, "save_config"):
                self.config.save_config()
            logger.info(
                "[amo] 已迁移旧版 amo_forever 配置: %s（%d 项）"
                % (legacy, len(merged))
            )
            logger.info("[amo] 升级提示：插件标识保持 Astrbot_Amo_forever；旧 amo_forever 配置/数据已自动迁移。")
        except Exception as exc:
            logger.warning("[amo] 旧版 amo_forever 配置迁移失败: %s" % exc)

    def _reload_config_if_changed(self):
        """AstrBot 原生插件配置页保存后，运行中的 self.config 可能不是新对象。

        读取配置文件 mtime，变化时把新值合并进当前配置，保证天气城市、
        管理员、主动私聊等动态配置不需要重启插件也能生效。
        """
        path = getattr(self.config, "config_path", "")
        if not path:
            return
        try:
            mtime = os.path.getmtime(path)
        except Exception:
            return
        if mtime <= self._config_mtime:
            return
        try:
            with open(path, encoding="utf-8-sig") as stream:
                data = json.load(stream)
            if not isinstance(data, dict):
                return
            old_engine_config = {
                key: value for key, value in self.config.items()
                if key.startswith("hf_") or key.startswith("seg_")
            }
            self.config.update(data)
            new_engine_config = {
                key: value for key, value in self.config.items()
                if key.startswith("hf_") or key.startswith("seg_")
            }
            if old_engine_config and old_engine_config != new_engine_config:
                self._spawn(self._apply_runtime_config())
            self._config_mtime = mtime
            if data.get("bot_name"):
                self.bot_name = str(data.get("bot_name"))
            if data.get("bot_aliases") is not None:
                self.bot_aliases = [
                    item.strip() for item in str(data.get("bot_aliases")).split(",") if item.strip()
                ]
            if self.heartflow is not None:
                self.heartflow.set_identity(self.bot_name, self.bot_aliases)
            self._persona_name_cache.clear()
            raw_admins = data.get("admin_uids", None)
            if raw_admins is not None:
                self.admin_uids = {
                    item.strip() for item in str(raw_admins).split(",") if item.strip()
                }
            start = str(data.get("period_start") or "").strip()
            if start and self.state is not None and start != self.state.period_start:
                try:
                    date.fromisoformat(start)
                    self.state.set_period_start(start)
                except Exception:
                    pass
            logger.debug("[amo] 检测到插件配置变更，已重新加载")
        except Exception as exc:
            logger.debug("[amo] 重新加载插件配置失败: %s" % exc)

    def _hf_config(self):
        try:
            return {key[3:]: value for key, value in self.config.items() if key.startswith("hf_")}
        except Exception:
            return {}

    def _seg_config(self):
        try:
            return {key[4:]: value for key, value in self.config.items() if key.startswith("seg_")}
        except Exception:
            return {}

    def _command_prefixes(self):
        if self._prefix_cache is not None:
            return self._prefix_cache
        prefixes = []
        try:
            cfg = self.context.get_config()
            raw = cfg.get("wake_prefix", []) if cfg else []
            if isinstance(raw, str):
                raw = [raw]
            prefixes = [str(item) for item in (raw or []) if item]
        except Exception:
            pass
        self._prefix_cache = prefixes
        return prefixes

    def _looks_like_command(self, text):
        if looks_like_plain_command(text):
            return True
        first = text.split()[0].lower() if text.split() else ""
        if first in ("amo", "陪伴", "c_status", "c_profile", "c_setrel", "learn_and_gate"):
            return True
        return any(prefix and text.startswith(prefix) for prefix in self._command_prefixes())

    def _spawn(self, coro):
        try:
            task = asyncio.create_task(coro)
        except RuntimeError:
            return None
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _ensure_ready(self):
        if self._ready:
            return
        async with self._init_lock:
            if self._ready:
                return
            try:
                await asyncio.to_thread(self.db.init)
            except Exception as exc:
                logger.error("[amo] 数据库初始化失败: %s" % exc)
            self._migrate_delay_default()
            self._migrate_proactive_timing()
            self._migrate_typing_defaults()
            self._migrate_memory_source_default()
            self._migrate_legacy_admin_default()
            self._cleanup_legacy_memory_profiles()
            self.state = HumanState(self)
            self._ready = True
            self._loop_task = self._spawn(self._background_loop())
            self._spawn(self._warm_up())

    def _cleanup_legacy_memory_profiles(self):
        """4.3.2 回到原版：删除旧版本从记忆插件导入的画像，只保留本地聊天档案。"""
        try:
            if self.db.kv_get("legacy_memory_profiles_cleaned_432", False):
                return
            removed = 0
            for row in self.db.list_profiles(limit=1000):
                if str(row.get("platform") or "") in ("angel_memory", "memory_companion"):
                    self.db.delete_profile(str(row.get("uid") or ""))
                    removed += 1
            self.db.kv_set("legacy_memory_profiles_cleaned_432", True)
            if removed:
                logger.info("[amo] 已移除 %d 个旧记忆插件导入画像，恢复本地画像模式" % removed)
        except Exception as exc:
            logger.debug("[amo] 清理旧记忆画像失败: %s" % exc)

    def _migrate_typing_defaults(self):
        """2.6.2 起把旧的 55ms/字默认值迁移到更真实的 400ms/字。"""
        try:
            if self.db.kv_get("typing_realistic_migrated", False):
                return
            changes = {}
            if to_int(self.cfg("typing_base_ms", 0), 0) == 600:
                changes["typing_base_ms"] = 700
            if to_int(self.cfg("typing_per_char_ms", 0), 0) == 55:
                changes["typing_per_char_ms"] = 400
            if to_int(self.cfg("typing_max_ms", 0), 0) == 4500:
                changes["typing_max_ms"] = 20000
            if abs(to_float(self.cfg("seg_per_char_delay_seconds", 0), 0) - 0.08) < 0.0001:
                changes["seg_per_char_delay_seconds"] = 0.4
            for key, value in changes.items():
                self.config[key] = value
            if changes:
                if hasattr(self.config, "save_config"):
                    self.config.save_config()
                if self.segment_engine is not None and "seg_per_char_delay_seconds" in changes:
                    self.segment_engine.per_char_delay_seconds = 0.4
                logger.debug("[amo] 打字延迟默认值已迁移为 400ms/字（18字约8秒）")
            self.db.kv_set("typing_realistic_migrated", True)
        except Exception as exc:
            logger.debug("[amo] 迁移打字延迟失败: %s" % exc)

    def _migrate_proactive_timing(self):
        try:
            if self.db.kv_get("proactive_timing_migrated", False):
                return
            changes = {}
            if to_int(self.cfg("proactive_followup_minutes", 0), 0) == 30:
                changes["proactive_followup_minutes"] = 5
            if to_int(self.cfg("proactive_no_reply_minutes", 0), 0) == 120:
                changes["proactive_no_reply_minutes"] = 30
            for key, value in changes.items():
                self.config[key] = value
            if changes and hasattr(self.config, "save_config"):
                self.config.save_config()
            self.db.kv_set("proactive_timing_migrated", True)
        except Exception:
            pass

    def _migrate_delay_default(self):
        """2.4.7 起默认按回复字数动态延迟；旧的 fixed 配置迁移一次。"""
        try:
            if self.cfg_str("seg_delay_type", "").strip().lower() != "fixed":
                return
            if self.db.kv_get("delay_dynamic_migrated", False):
                return
            self.config["seg_delay_type"] = "dynamic"
            if self.segment_engine is not None:
                self.segment_engine.delay_type = "dynamic"
            if hasattr(self.config, "save_config"):
                self.config.save_config()
            self.db.kv_set("delay_dynamic_migrated", True)
            logger.debug("[amo] 分段延迟已从 fixed 迁移为 dynamic（按回复字数）")
        except Exception as exc:
            logger.debug("[amo] 迁移分段延迟失败: %s" % exc)

    def _migrate_memory_source_default(self):
        """旧版把 private companion 写成默认来源；2.4.4 起改成 auto，避免锁死。"""
        try:
            value = self.cfg_str("companion_memory_plugin_name", "").strip()
            if value != LEGACY_MEMORY_PLUGIN:
                return
            if self.db.kv_get("memory_source_auto_migrated", False):
                return
            self.config["companion_memory_plugin_name"] = "auto"
            if hasattr(self.config, "save_config"):
                self.config.save_config()
            self.db.kv_set("memory_source_auto_migrated", True)
            logger.debug("[amo] 记忆来源已从旧默认 %s 改为 auto" % LEGACY_MEMORY_PLUGIN)
        except Exception as exc:
            logger.debug("[amo] 迁移记忆来源失败: %s" % exc)

    def _migrate_legacy_admin_default(self):
        """旧版本把 3261748099 写成了默认管理员；2.4.0 只清理一次。"""
        try:
            if self.cfg_str("admin_uids", "").strip() != LEGACY_DEFAULT_ADMIN:
                return
            if self.db.kv_get("admin_default_cleared", False):
                return
            parts = [
                item.strip() for item in self.cfg_str("admin_uids", "").split(",")
                if item.strip() and item.strip() != LEGACY_DEFAULT_ADMIN
            ]
            self.config["admin_uids"] = ",".join(parts)
            if hasattr(self.config, "save_config"):
                self.config.save_config()
            self.admin_uids = set(parts)
            self.db.kv_set("admin_default_cleared", True)
            logger.debug("[amo] 已移除旧默认管理员 %s，请在配置里填写自己的 ID" % LEGACY_DEFAULT_ADMIN)
        except Exception as exc:
            logger.debug("[amo] 清理旧默认管理员失败: %s" % exc)

    async def _warm_up(self):
        try:
            await asyncio.sleep(3)
            umo = self._last_umo or self._first_private_umo()
            await self._sync_persona_name(umo or "")
            await self._ensure_dialect_kb()
            await self._ensure_scenic_kb()
            await self.state.ensure_worldview(umo)
            await self.state.ensure_schedule(umo)
        except Exception as exc:
            logger.debug("[amo] 预热失败: %s" % exc)

    async def initialize(self):
        await self._ensure_ready()

    async def terminate(self):
        self._running = False
        if self.heartflow is not None:
            try:
                await self.heartflow.terminate()
            except Exception:
                pass
        if self.segment_engine is not None:
            for task in list(getattr(self.segment_engine, "_tasks", set())):
                try:
                    task.cancel()
                except Exception:
                    pass
        for task in list(self._tasks):
            try:
                task.cancel()
            except Exception:
                pass
        if self.state is not None:
            try:
                self.state.save()
            except Exception:
                pass
        # 不在这里关闭数据库：AstrBot 重载插件时旧实例注册的 Web API
        # 可能仍被调用，关闭连接会导致 "Cannot operate on a closed database"。
        # 连接由进程退出时回收；AmoDB.conn 也会在需要时自动重连。

    async def stop(self):
        await self.terminate()

    # ---------- 管理员 ----------
    def _is_admin(self, event):
        uid = str(event.get_sender_id())
        if uid in self.admin_uids:
            return True
        try:
            cfg = self.context.get_config(event.unified_msg_origin)
            admins = cfg.get("admins_id", []) if cfg else []
            if isinstance(admins, str):
                admins = [item.strip() for item in admins.split(",") if item.strip()]
            if uid in [str(item) for item in (admins or [])]:
                return True
        except Exception:
            pass
        return False

    # ---------- 消息学习 ----------
    async def _learn(self, event, text):
        uid = str(event.get_sender_id())
        name = event.get_sender_name() or uid
        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        private = event.is_private_chat()
        profile = self.db.touch_profile(
            uid, name, event.get_platform_name(), umo, group_id, private
        )
        if profile and not profile.get("is_admin") and uid in self.admin_uids:
            self.db.update_profile(uid, is_admin=1)
            profile["is_admin"] = 1

        self.state.observe(text)
        self.db.add_message(umo, uid, name, "user", text)

        senti = sentiment(text)
        affection = to_int(profile.get("affection"), 10)
        if senti["aff"] or senti["pos"]:
            affection += 2
        if senti["neg"] or senti["insult"]:
            affection -= 2
        affection = int(clamp(affection, 0, 100))

        if self.cfg_bool("enable_memory", True):
            for fact in extract_facts(text):
                self.db.add_memory(
                    uid, fact["content"], fact["kind"], fact["tier"],
                    self.cfg_int("mem_days_normal", 7),
                    self.cfg_int("mem_days_important", 14),
                )
                if fact["kind"] == "birthday":
                    match = re.search(r"生日是(\d{2})月(\d{2})日", fact["content"])
                    if match:
                        self.db.update_profile(uid, birthday="%s-%s" % (match.group(1), match.group(2)))

        fields = {"affection": affection}
        relation = profile.get("relation", "普通")
        if relation == "普通" and to_int(profile.get("msg_count"), 0) >= self.cfg_int("familiar_msg_count", 30):
            fields["relation"] = "熟识"
        elif relation == "熟识" and senti["insult"]:
            fields["relation"] = "抵触"
        self.db.update_profile(uid, **fields)
        try:
            self._learn_alias(event, text, uid, profile)
        except Exception as exc:
            logger.debug("[amo] 学习称呼失败: %s" % exc)

        if group_id:
            times = self._group_times.setdefault(group_id, [])
            times.append(now_ts())
            if len(times) > 200:
                self._group_times[group_id] = times[-200:]
            self._last_group = group_id
        self._last_umo = umo

    def _register_lover(self, uid):
        uid = str(uid or "").strip()
        if uid:
            self.db.kv_set("lover_uid_" + uid, True)

    def _is_registered_lover(self, uid):
        uid = str(uid or "").strip()
        if not uid:
            return False
        if self.db.kv_get("lover_uid_" + uid, False):
            return True
        profile = self.db.get_profile(uid) or {}
        if str(profile.get("relation") or "") == "相恋":
            self._register_lover(uid)
            return True
        return False

    def _restore_lover_relation(self, uid):
        uid = str(uid or "").strip()
        if not self._is_registered_lover(uid):
            return
        profile = self.db.get_profile(uid) or {}
        if str(profile.get("relation") or "") in ("抵触", "仇恨"):
            self.db.update_profile(uid, relation="相恋")
            logger.info("[amo] 恋人 UID 恢复为相恋: %s" % uid)

    def _lover_aliases(self):
        aliases = {}
        try:
            profiles = self.db.list_profiles("", 500)
        except Exception:
            profiles = []
        for profile in profiles:
            uid = str(profile.get("uid") or "")
            if str(profile.get("relation") or "") == "相恋":
                self._register_lover(uid)
            elif not self._is_registered_lover(uid):
                continue
            values = [profile.get("name") or ""]
            values.extend(re.split(r"[；;、,，/\s]+", str(profile.get("alias") or "")))
            for value in values:
                name = str(value or "").strip()
                if len(name) >= 1:
                    aliases[name] = uid
        return aliases

    def _detect_impersonation(self, event):
        """群里非恋人 UID 使用/冒充恋人的名字或爱称时，5 分钟内累计降级。"""
        group_id = str(event.get_group_id() or "")
        if not group_id:
            return False
        uid = str(event.get_sender_id())
        lovers = self._lover_aliases()
        if not lovers or uid in set(lovers.values()) or self._is_registered_lover(uid):
            return False
        sender_name = str(event.get_sender_name() or "").strip()
        text = str(event.message_str or "").strip()
        hit = ""
        if sender_name in lovers:
            hit = sender_name
        elif text in lovers:
            hit = text
        else:
            for alias in lovers:
                if re.search(r"(?:我才是|我是|叫我|叫我做|以后叫我|我才是那个)\s*" + re.escape(alias), text):
                    hit = alias
                    break
        if not hit:
            return False
        setattr(event, "amo_impersonation", True)
        key = "impersonate_%s_%s" % (group_id, uid)
        now = now_ts()
        stamps = self.db.kv_get(key, [])
        if not isinstance(stamps, list):
            stamps = []
        stamps = [to_float(item, 0) for item in stamps if now - to_float(item, 0) <= 300]
        stamps.append(now)
        self.db.kv_set(key, stamps)
        count = len(stamps)
        profile = self.db.get_profile(uid) or {}
        current = str(profile.get("relation") or "普通")
        relation = current
        if count >= 3 and current != "仇恨":
            relation = "仇恨"
        elif count == 1 and current != "仇恨":
            relation = "抵触"
        if relation != current:
            self.db.update_profile(uid, relation=relation)
            logger.info(
                "[amo] 识别到冒充恋人称呼: %s -> %s（%s，5分钟内第%d次）"
                % (uid, relation, hit, count)
            )
        return True

    def _learn_alias(self, event, text, uid, profile):
        """从“以后叫我XX / 叫他XX”里学习称呼，并在后续沿用。"""
        blocked = {"干嘛", "什么", "名字", "滚", "闭嘴", "一声", "一下", "出来"}
        alias = ""
        for pattern in (
            r"(?:以后|今后|你可以|可以|请)?叫我\s*([\u4e00-\u9fa5A-Za-z0-9_]{1,12})",
            r"叫我\s*([\u4e00-\u9fa5A-Za-z0-9_]{1,12})\s*(?:就行|就好|吧)",
        ):
            match = re.search(pattern, str(text or ""))
            if match:
                candidate = match.group(1).strip()
                if candidate and candidate not in blocked:
                    alias = candidate
                    break
        if alias:
            current = str(profile.get("alias") or "")
            if alias not in current:
                new_alias = (current + "；" + alias).strip("；")[:80]
                self.db.update_profile(uid, alias=new_alias)
                logger.debug("[amo] 记住称呼: %s -> %s" % (uid, alias))

        try:
            messages = event.message_obj.message
        except Exception:
            messages = []
        at_targets = [
            str(getattr(comp, "qq", ""))
            for comp in (messages or [])
            if Comp is not None and isinstance(comp, Comp.At)
        ]
        for comp in messages:
            if Comp is None or not isinstance(comp, Comp.At):
                continue
            target = str(getattr(comp, "qq", ""))
            if not target or target in ("all", str(event.get_self_id())):
                continue
            # “以后喊他XX”通常跟在最后一个 @ 后面；不要误记到前一个被 @ 的人。
            if at_targets and target != at_targets[-1]:
                continue
            for pattern in (
                r"(?:以后|就)?(?:喊|叫|称呼)(?:他|她|ta|TA|做)\s*([\u4e00-\u9fa5A-Za-z0-9_]{1,12})",
            ):
                match = re.search(pattern, str(text or ""))
                if not match:
                    continue
                candidate = match.group(1).strip()
                if not candidate or candidate in blocked:
                    continue
                target_profile = self.db.get_profile(target)
                if not target_profile:
                    self.db.touch_profile(target, candidate, event.get_platform_name(), "", "", False)
                    target_profile = self.db.get_profile(target)
                current = str(target_profile.get("alias") or "")
                if candidate not in current:
                    self.db.update_profile(target, alias=(current + "；" + candidate).strip("；")[:80])
                break
            # 群里反复 @ 同一个人并叫同一个短称呼，累计三次后记住。
            plain = re.sub(r"@\S+", "", str(text or "")).strip()
            common = {
                "在吗", "你好", "早安", "晚安", "吃了吗", "干嘛", "出来", "看这个",
                "哈哈", "笑死", "救命", "谢谢", "收到", "好的", "可以", "不行",
                "快看", "快来", "过来", "上线", "打游戏", "起床", "睡觉", "上班", "下班",
            }
            if 1 <= len(plain) <= 8 and plain not in common and not re.search(r"[，。！？!?、；;：:]", plain):
                seen_key = "alias_seen_" + target + "_" + plain
                seen = to_int(self.db.kv_get(seen_key, 0), 0) + 1
                self.db.kv_set(seen_key, seen)
                if seen >= 3:
                    alias_profile = self.db.get_profile(target) or {}
                    current = str(alias_profile.get("alias") or "")
                    if plain not in current:
                        self.db.update_profile(target, alias=(current + "；" + plain).strip("；")[:80])
                    self.db.kv_set(seen_key, 0)

    def _recent(self, umo, limit=10):
        try:
            return self.db.recent_messages(umo, limit)
        except Exception:
            return []

    def _group_speaker_count(self, umo, limit=20, window=600):
        """最近一段时间内群聊里的不同发言人数。"""
        try:
            rows = self.db.recent_messages(umo, limit)
        except Exception:
            return 0
        cutoff = now_ts() - window
        speakers = {
            str(row.get("uid") or "")
            for row in rows
            if row.get("role") == "user"
            and to_float(row.get("created_at"), 0) >= cutoff
            and str(row.get("uid") or "")
        }
        return len(speakers)

    @staticmethod
    def _is_memory_companion(plugin):
        return plugin is not None and getattr(plugin, "memory_companion", None) is not None

    @staticmethod
    def _memcomp_db_path(plugin):
        service = getattr(plugin, "service", None)
        store = getattr(service, "store", None)
        path = getattr(store, "db_path", None)
        if path and os.path.isfile(str(path)):
            return str(path)
        data_dir = getattr(service, "data_dir", None) or getattr(plugin, "data_dir", None)
        if data_dir:
            candidate = os.path.join(str(data_dir), "memory_companion.db")
            if os.path.isfile(candidate):
                return candidate
        return ""

    def _memcomp_rows(self, sql, params=()):
        path = self._memcomp_db_path(self._companion_plugin())
        if not path:
            return []
        conn = None
        try:
            from urllib.parse import quote
            try:
                conn = sqlite3.connect(
                    "file:" + quote(path) + "?mode=ro",
                    uri=True,
                    timeout=2.0,
                )
            except Exception:
                conn = sqlite3.connect(path, timeout=2.0)
            conn.row_factory = sqlite3.Row
            return [dict(row) for row in conn.execute(sql, params).fetchall()]
        except Exception as exc:
            logger.debug("[amo] 读取 Memory Companion 数据库失败: %s" % exc)
            return []
        finally:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass

    def _memcomp_name_maps(self, plugin=None):
        """从 identities/profile/证据里建立 person_id -> 名字 的自动映射。"""
        plugin = plugin or self._companion_plugin()
        by_uid = {}
        by_key = {}
        evidence_map = {}
        try:
            rows = self._memcomp_rows(
                "SELECT entity_id, display_name, profile FROM identities "
                "WHERE entity_kind='user' AND entity_id!=''"
            )
            for row in rows:
                uid = str(row.get("entity_id") or "").strip()
                name = str(row.get("display_name") or "").strip()
                if uid and name:
                    by_uid[uid] = name
                try:
                    profile = json.loads(row.get("profile") or "{}")
                except Exception:
                    profile = {}
                if not isinstance(profile, dict):
                    continue
                for key in ("display_name", "name", "nickname"):
                    if not name and profile.get(key):
                        name = str(profile.get(key)).strip()
                if name:
                    for key in ("person_id", "resolved_identity_key", "identity_key"):
                        value = str(profile.get(key) or "").strip()
                        if value:
                            by_key[value] = name
        except Exception as exc:
            logger.debug("[amo] 建立身份名字映射失败: %s" % exc)
        try:
            rows = self._memcomp_rows(
                "SELECT e.person_id, t.subject_id, i.display_name "
                "FROM portrait_evidence e "
                "LEFT JOIN timeline t ON t.message_id=e.message_id "
                "LEFT JOIN identities i ON i.entity_id=t.subject_id "
                "WHERE e.person_id!='' AND i.display_name!=''"
            )
            for row in rows:
                pid = str(row.get("person_id") or "").strip()
                name = str(row.get("display_name") or "").strip()
                if pid and name:
                    evidence_map.setdefault(pid, name)
        except Exception as exc:
            logger.debug("[amo] 建立证据名字映射失败: %s" % exc)
        return {"by_uid": by_uid, "by_key": by_key, "evidence": evidence_map}

    def _memcomp_person_name(self, person_id, identity_key="", maps=None):
        """按 画像事实 -> 身份键 -> 身份表 -> 证据 的顺序自动取名字。"""
        maps = maps or self._memcomp_name_maps()
        rows = self._memcomp_rows(
            "SELECT dimension, claim_summary FROM portrait_facts "
            "WHERE person_id=? AND status='active' "
            "ORDER BY confidence DESC, updated_at DESC LIMIT 40",
            (str(person_id),),
        )
        name_dims = {
            "name", "display_name", "nickname", "preferred_address",
            "用户别名", "称呼", "昵称", "姓名", "名字",
        }
        patterns = (
            r"(?:名字|姓名|昵称|称呼|别名)(?:是|叫|为|：|:)\s*([^\s，。；;,.!?！？]{1,20})",
            r"(?:叫我|叫做|名为)\s*([^\s，。；;,.!?！？]{1,20})",
        )
        for row in rows:
            dimension = str(row.get("dimension") or "").strip().lower()
            claim = re.sub(r"\s+", " ", str(row.get("claim_summary") or "")).strip()
            if not claim:
                continue
            if dimension in name_dims:
                text = claim
                for pattern in patterns:
                    match = re.search(pattern, text)
                    if match:
                        text = match.group(1)
                        break
                text = text.strip("「」“”\"' ")
                if 1 <= len(text) <= 20:
                    return text
            for pattern in patterns:
                match = re.search(pattern, claim)
                if match:
                    text = match.group(1).strip("「」“”\"' ")
                    if 1 <= len(text) <= 20:
                        return text
        for candidate in (str(identity_key or "").strip(), str(person_id)):
            if candidate and maps.get("by_key", {}).get(candidate):
                return maps["by_key"][candidate]
        if maps.get("by_uid", {}).get(str(person_id)):
            return maps["by_uid"][str(person_id)]
        if maps.get("evidence", {}).get(str(person_id)):
            return maps["evidence"][str(person_id)]
        return ""

    def _memcomp_profile_rows(self, plugin=None):
        """以 portrait_facts 为准：只有真正有画像事实的人才是用户画像。"""
        plugin = plugin or self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return []
        rows = self._memcomp_rows(
            "SELECT person_id, resolved_identity_key, 0 AS fact_count FROM portrait_people "
            "WHERE profile_status='active' AND person_id!='' "
            "ORDER BY updated_at DESC"
        )
        maps = self._memcomp_name_maps(plugin)
        items = []
        for row in rows:
            uid = str(row.get("person_id") or "").strip()
            if not uid:
                continue
            name = self._memcomp_person_name(
                uid, str(row.get("resolved_identity_key") or ""), maps
            )
            items.append({
                "uid": uid,
                "name": name or ("画像 " + uid[-6:]),
                "count": to_int(row.get("fact_count"), 0),
                "source": "portrait_people",
            })
        if items:
            return items
        # 老库没有 portrait_facts 时，退回 identities，但只取真实用户/有资料者。
        user_roles = (
            "conversation_partner", "external_memory_owner", "user", "admin",
            "member", "friend", "owner", "lover", "partner",
        )
        placeholders = ",".join("?" for _ in user_roles)
        rows = self._memcomp_rows(
            "SELECT entity_id, display_name, profile FROM identities "
            "WHERE entity_kind='user' AND entity_id!='' "
            "AND LOWER(COALESCE(role,'')) IN (" + placeholders + ") "
            "AND COALESCE(profile,'') NOT IN ('', '{}', 'null')",
            user_roles,
        )
        items = []
        for row in rows:
            uid = str(row.get("entity_id") or "").strip()
            if not uid:
                continue
            name = str(row.get("display_name") or "").strip()
            if not name:
                try:
                    parsed = json.loads(row.get("profile") or "{}")
                    if isinstance(parsed, dict):
                        name = str(parsed.get("name") or parsed.get("nickname") or "").strip()
                except Exception:
                    pass
            items.append({"uid": uid, "name": name, "count": 0, "source": "identities"})
        return items

    def _memcomp_profile_uids(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        return {row["uid"] for row in self._memcomp_profile_rows(plugin)}

    def _memcomp_user_count(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return 0
        return len(self._memcomp_profile_rows(plugin))

    def _memcomp_memories(self, uid, keyword="", limit=50):
        plugin = self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return []
        rows = self._memcomp_rows(
            "SELECT claim_summary, dimension, confidence, created_at, updated_at "
            "FROM portrait_facts WHERE person_id=? AND status='active' "
            "ORDER BY confidence DESC, updated_at DESC LIMIT ?",
            (str(uid), max(1, min(100, to_int(limit, 50)))),
        )
        items = []
        for row in rows:
            content = re.sub(r"\s+", " ", str(row.get("claim_summary") or "")).strip()
            if len(content) < 2:
                continue
            if keyword and str(keyword).lower() not in content.lower():
                continue
            confidence = to_float(row.get("confidence"), 0.5)
            items.append({
                "content": content[:500],
                "tier": 2 if confidence >= 0.8 else (1 if confidence >= 0.55 else 0),
                "kind": "memory_companion",
                "source": "memory_companion",
                "memory_type": row.get("dimension", "profile"),
                "created_at": row.get("created_at", ""),
                "hits": 0,
                "expires_at": None,
            })
        if items:
            return items
        # 兼容旧库：没有 portrait_facts 时，只返回画像类 memory_type。
        sql = (
            "SELECT content, importance, memory_type, created_at, updated_at "
            "FROM memories WHERE (subject_id=? OR object_id=?) AND content!='' "
            "AND lifecycle NOT IN ('deleted','archived','quarantined') "
            "AND memory_type IN ('user_profile','user_preference','relationship_claim','user_habit') "
        )
        params = [str(uid), str(uid)]
        if keyword:
            sql += "AND content LIKE ? "
            params.append("%" + str(keyword) + "%")
        sql += "ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(100, to_int(limit, 50))))
        for row in self._memcomp_rows(sql, tuple(params)):
            content = re.sub(r"\s+", " ", str(row.get("content") or "")).strip()
            if len(content) < 2:
                continue
            importance = to_float(row.get("importance"), 0.3)
            items.append({
                "content": content[:500],
                "tier": 2 if importance >= 0.72 else (1 if importance >= 0.42 else 0),
                "kind": "memory_companion",
                "source": "memory_companion",
                "memory_type": row.get("memory_type", ""),
                "created_at": row.get("created_at", ""),
                "hits": 0,
                "expires_at": None,
            })
        return items

    def _memcomp_all_memories(self, uid, keyword="", limit=50):
        """完整记忆：不限制 memory_type，用于“查看记忆”和召回。"""
        plugin = self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return []
        sql = (
            "SELECT content, importance, memory_type, created_at, updated_at "
            "FROM memories WHERE (subject_id=? OR object_id=?) AND content!='' "
            "AND lifecycle NOT IN ('deleted','archived','quarantined') "
        )
        params = [str(uid), str(uid)]
        if keyword:
            sql += "AND content LIKE ? "
            params.append("%" + str(keyword) + "%")
        sql += "ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(max(1, min(100, to_int(limit, 50))))
        items = []
        for row in self._memcomp_rows(sql, tuple(params)):
            content = re.sub(r"\s+", " ", str(row.get("content") or "")).strip()
            if len(content) < 2:
                continue
            importance = to_float(row.get("importance"), 0.3)
            items.append({
                "content": content[:500],
                "tier": 2 if importance >= 0.72 else (1 if importance >= 0.42 else 0),
                "kind": "memory_companion",
                "source": "memory_companion",
                "memory_type": row.get("memory_type", ""),
                "created_at": row.get("created_at", ""),
                "hits": 0,
                "expires_at": None,
            })
        return items

    def _sync_memory_companion_profiles(self, only_uid=""):
        plugin = self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return 0
        rows = self._memcomp_profile_rows(plugin)
        if not rows:
            return 0
        identities = {}
        try:
            identity_rows = self._memcomp_rows(
                "SELECT entity_id, display_name, profile FROM identities "
                "WHERE entity_kind='user' AND entity_id!=''"
            )
            identities = {str(row.get("entity_id") or ""): row for row in identity_rows}
        except Exception:
            identities = {}
        if not only_uid:
            self._cleanup_auto_profiles("memory_companion", [row["uid"] for row in rows])
        synced = 0
        for row in rows:
            uid = str(row.get("uid") or "")
            if not uid or (only_uid and uid != str(only_uid)):
                continue
            profile = self.db.get_profile(uid) or {}
            name = str(row.get("name") or "").strip()
            if not name:
                ident = identities.get(uid) or {}
                name = str(ident.get("display_name") or "").strip()
            count = to_int(row.get("count"), 0)
            if not profile:
                self.db.touch_profile(uid, name or uid, "memory_companion", "", "", False)
                profile = self.db.get_profile(uid) or {}
            fields = {}
            current_name = str(profile.get("name") or "").strip()
            if name and (
                not current_name or current_name == uid
                or current_name.startswith("画像 ")
                or current_name.startswith("person_")
            ):
                fields["name"] = name[:60]
            if not profile.get("notes") and count:
                fields["notes"] = ("画像 %d 条（Memory Companion）" % count)[:100]
            if fields:
                self.db.update_profile(uid, **fields)
            synced += 1
        return synced

    def _sync_memory_companion_profile(self, uid, force=False):
        plugin = self._companion_plugin()
        if not self._is_memory_companion(plugin):
            return
        uid = str(uid)
        if not force:
            key = "memcomp_profile_sync_" + uid
            if now_ts() - to_float(self.db.kv_get(key, 0)) < 600:
                return
            self.db.kv_set(key, now_ts())
        self._sync_memory_companion_profiles(only_uid=uid)

    ANGEL_ATTRIBUTE_TAGS = {"用户别名", "事实属性", "技能树", "关系图谱", "活跃项目"}

    @staticmethod
    def _is_angel_memory(plugin):
        if plugin is None:
            return False
        marker = (
            str(type(plugin).__module__ or "") + " "
            + str(getattr(plugin, "name", "") or "")
        ).lower()
        if "angel_memory" in marker:
            return True
        return (
            getattr(plugin, "plugin_context", None) is not None
            and (
                getattr(plugin, "memory_store", None) is not None
                or getattr(plugin, "deepmind", None) is not None
            )
        )

    @staticmethod
    def _angel_component(plugin, name):
        ctx = getattr(plugin, "plugin_context", None)
        if ctx is not None and hasattr(ctx, "get_component"):
            try:
                value = ctx.get_component(name)
                if value is not None:
                    return value
            except Exception:
                pass
        if name == "memory_store":
            return getattr(plugin, "memory_store", None)
        if name == "memory_sql_manager":
            return getattr(plugin, "memory_sql_manager", None)
        return None

    def _angel_records(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        store = self._angel_component(plugin, "memory_store")
        method = getattr(store, "list_records", None)
        if not callable(method):
            return []
        try:
            return list(method(None, all_scopes=True) or [])
        except Exception as exc:
            logger.debug("[amo] 读取 Angel Memory 记录失败: %s" % exc)
            return []

    def _angel_ledger_users(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        ledger = self._angel_component(plugin, "memory_sql_manager")
        method = getattr(ledger, "list_ledger_users", None)
        if not callable(method):
            return []
        try:
            return list(method() or [])
        except Exception as exc:
            logger.debug("[amo] 读取 Angel Memory 用户账本失败: %s" % exc)
            return []

    @staticmethod
    def _angel_tags(record):
        tags = (record or {}).get("tags") or []
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.split(",")]
        return [str(item).strip() for item in tags if str(item).strip()]

    def _angel_known_ids(self, plugin=None):
        return {
            str(item.get("user_id") or "").strip()
            for item in self._angel_ledger_users(plugin)
            if isinstance(item, dict) and str(item.get("user_id") or "").strip()
        }

    @staticmethod
    def _angel_is_id(tag, known_ids=None):
        text = str(tag or "").strip()
        if not text:
            return False
        if known_ids and text in known_ids:
            return True
        if len(text) <= 5 or any("\u4e00" <= char <= "\u9fff" for char in text):
            return False
        if any(char.isspace() for char in text):
            return False
        return not text.replace("-", "").replace("_", "").isalpha()

    def _angel_uid_tags(self, tags, known_ids=None):
        normalized = [str(item).strip() for item in (tags or []) if str(item).strip()]
        if known_ids:
            hits = [item for item in normalized if item in known_ids]
            if hits:
                return hits
        return [item for item in normalized if self._angel_is_id(item, known_ids)]

    def _angel_profile_records(self, plugin=None):
        """Angel 的用户画像只取带画像属性标签的记录，不把普通记忆里的群/机器人 ID 当用户。"""
        plugin = plugin or self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        result = []
        for record in self._angel_records(plugin):
            tags = self._angel_tags(record)
            if any(tag in self.ANGEL_ATTRIBUTE_TAGS for tag in tags):
                result.append(record)
        return result

    def _angel_user_count(self, plugin=None):
        plugin = plugin or self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return 0
        known = self._angel_known_ids(plugin)
        users = set()
        for record in self._angel_profile_records(plugin):
            users.update(self._angel_uid_tags(self._angel_tags(record), known))
        return len(users)

    def _cleanup_auto_profiles(self, source, real_uids):
        """删除记忆源自动创建、但不在真实画像列表里的历史空画像。"""
        real = {str(uid) for uid in real_uids}
        removed = 0
        try:
            for row in self.db.list_profiles(limit=1000):
                uid = str(row.get("uid") or "")
                if not uid or uid in real:
                    continue
                if str(row.get("platform") or "") not in ("angel_memory", "memory_companion"):
                    continue
                if to_int(row.get("msg_count"), 0) > 1:
                    continue
                if str(row.get("private_umo") or ""):
                    continue
                self.db.delete_profile(uid)
                removed += 1
            if removed:
                logger.info("[amo] 已清理 %d 个非画像用户（%s）" % (removed, source))
        except Exception as exc:
            logger.debug("[amo] 清理非画像用户失败: %s" % exc)

    def _sync_angel_profiles(self, only_uid=""):
        plugin = self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return 0
        known = self._angel_known_ids(plugin)
        buckets = {}
        for record in self._angel_profile_records(plugin):
            tags = self._angel_tags(record)
            uids = self._angel_uid_tags(tags, known)
            if not uids:
                continue
            nickname = ""
            for tag in tags:
                if tag in known or self._angel_is_id(tag, known):
                    continue
                if tag in self.ANGEL_ATTRIBUTE_TAGS:
                    continue
                nickname = tag
                break
            for uid in uids:
                bucket = buckets.setdefault(uid, {"name": "", "count": 0})
                bucket["count"] += 1
                if nickname and not bucket["name"]:
                    bucket["name"] = nickname
        # 账本只用来补昵称，不单独创建画像；Angel 自己也是按画像记录展示用户。
        ledger_names = {}
        for row in self._angel_ledger_users(plugin):
            if isinstance(row, dict) and str(row.get("user_id") or "").strip():
                ledger_names[str(row["user_id"])] = str(row.get("nickname") or "")
        for uid, bucket in buckets.items():
            if not bucket.get("name") and ledger_names.get(uid):
                bucket["name"] = ledger_names[uid]
        if not only_uid:
            self._cleanup_auto_profiles("angel_memory", buckets.keys())
        synced = 0
        for uid, bucket in buckets.items():
            if only_uid and uid != str(only_uid):
                continue
            profile = self.db.get_profile(uid) or {}
            if not profile:
                self.db.touch_profile(uid, bucket.get("name") or uid, "angel_memory", "", "", False)
                profile = self.db.get_profile(uid) or {}
            fields = {}
            name = str(bucket.get("name") or "").strip()
            if name and (not profile.get("name") or str(profile.get("name")) == uid):
                fields["name"] = name[:60]
            if not profile.get("notes") and bucket.get("count"):
                fields["notes"] = ("Angel Memory：%d 条记忆" % bucket["count"])[:100]
            if fields:
                self.db.update_profile(uid, **fields)
            synced += 1
        return synced

    def _sync_angel_profile(self, uid, force=False):
        plugin = self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return
        uid = str(uid)
        if not force:
            key = "angel_profile_sync_" + uid
            if now_ts() - to_float(self.db.kv_get(key, 0)) < 600:
                return
            self.db.kv_set(key, now_ts())
        self._sync_angel_profiles(only_uid=uid)

    def _angel_memories(self, uid, keyword="", limit=50):
        plugin = self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        known = self._angel_known_ids(plugin)
        items = []
        for record in self._angel_profile_records(plugin):
            tags = self._angel_tags(record)
            if str(uid) not in self._angel_uid_tags(tags, known):
                continue
            content = str(record.get("judgment") or record.get("reasoning") or "").strip()
            content = re.sub(r"\s+", " ", content)
            if len(content) < 2:
                continue
            if keyword and str(keyword).lower() not in content.lower():
                continue
            state = record.get("state") if isinstance(record.get("state"), dict) else {}
            strength = to_int(state.get("strength"), 1)
            pinned = bool(state.get("pinned", False))
            items.append({
                "content": content[:500],
                "tier": 2 if pinned or strength >= 3 else (1 if strength >= 2 else 0),
                "kind": "angel_memory",
                "source": "angel_memory",
                "memory_type": "angel",
                "created_at": record.get("created_at_us") or record.get("created_at") or "",
                "hits": 0,
                "expires_at": None,
            })
            if len(items) >= max(1, min(100, to_int(limit, 50))):
                break
        return items


    def _angel_all_memories(self, uid, keyword="", limit=50):
        """天使之魂完整记忆，不限制画像标签。"""
        plugin = self._companion_plugin()
        if not self._is_angel_memory(plugin):
            return []
        known = self._angel_known_ids(plugin)
        items = []
        for record in self._angel_records(plugin):
            tags = self._angel_tags(record)
            if str(uid) not in self._angel_uid_tags(tags, known):
                continue
            content = str(record.get("judgment") or record.get("reasoning") or "").strip()
            content = re.sub(r"\s+", " ", content)
            if len(content) < 2:
                continue
            if keyword and str(keyword).lower() not in content.lower():
                continue
            state = record.get("state") if isinstance(record.get("state"), dict) else {}
            strength = to_int(state.get("strength"), 1)
            pinned = bool(state.get("pinned", False))
            items.append({
                "content": content[:500],
                "tier": 2 if pinned or strength >= 3 else (1 if strength >= 2 else 0),
                "kind": "angel_memory",
                "source": "angel_memory",
                "memory_type": "angel",
                "created_at": record.get("created_at_us") or record.get("created_at") or "",
                "hits": 0,
                "expires_at": None,
            })
            if len(items) >= max(1, min(100, to_int(limit, 50))):
                break
        return items

    def _external_all_memories(self, uid, query="", limit=50):
        """只读地从已安装记忆插件取完整记忆，不创建画像。"""
        items = []
        plugin = self._companion_plugin()
        if plugin is None:
            return items
        try:
            if self._is_memory_companion(plugin):
                items.extend(self._memcomp_all_memories(uid, query, limit))
            elif self._is_angel_memory(plugin):
                items.extend(self._angel_all_memories(uid, query, limit))
            else:
                items.extend(self._companion_memories(uid, query))
        except Exception as exc:
            logger.debug("[amo] 外部完整记忆读取失败: %s" % exc)
        return items

    def _external_profile_memories(self, uid, name="", alias="", limit=200):
        """按 UID 或名字/称呼从已安装记忆插件取完整记忆；只读，不建画像。"""
        plugin = self._companion_plugin()
        if plugin is None:
            return []
        items = []
        names = [str(name or "").strip(), str(alias or "").strip()]
        names = [item for item in names if item]
        try:
            if self._is_memory_companion(plugin):
                items.extend(self._memcomp_all_memories(uid, "", limit))
                if not items and names:
                    sql = (
                        "SELECT content, importance, memory_type, created_at, updated_at "
                        "FROM memories WHERE content!='' "
                        "AND lifecycle NOT IN ('deleted','archived','quarantined') "
                        "AND (" + " OR ".join("content LIKE ?" for _ in names) + ") "
                        "ORDER BY importance DESC, updated_at DESC LIMIT ?"
                    )
                    params = ["%" + item + "%" for item in names] + [max(1, min(100, limit))]
                    for row in self._memcomp_rows(sql, tuple(params)):
                        content = re.sub(r"\s+", " ", str(row.get("content") or "")).strip()
                        if len(content) < 2:
                            continue
                        importance = to_float(row.get("importance"), 0.3)
                        items.append({
                            "content": content[:500],
                            "tier": 2 if importance >= 0.72 else (1 if importance >= 0.42 else 0),
                            "kind": "memory_companion",
                            "source": "memory_companion",
                            "created_at": row.get("created_at", ""),
                        })
            elif self._is_angel_memory(plugin):
                items.extend(self._angel_all_memories(uid, "", limit))
                if not items and names:
                    known = self._angel_known_ids(plugin)
                    for record in self._angel_records(plugin):
                        tags = self._angel_tags(record)
                        content = str(record.get("judgment") or record.get("reasoning") or "")
                        haystack = content + " " + " ".join(tags)
                        if not any(item in haystack for item in names):
                            continue
                        content = re.sub(r"\s+", " ", content).strip()
                        if len(content) >= 2:
                            items.append({
                                "content": content[:500],
                                "tier": 1,
                                "kind": "angel_memory",
                                "source": "angel_memory",
                                "created_at": record.get("created_at_us") or record.get("created_at") or "",
                            })
                        if len(items) >= limit:
                            break
            else:
                items.extend(self._companion_memories(uid, ""))
                if not items and names:
                    data = getattr(plugin, "data", None)
                    users = data.get("users") if isinstance(data, dict) else None
                    if isinstance(users, dict):
                        for other_uid, user in users.items():
                            if not isinstance(user, dict):
                                continue
                            values = [user.get("name"), user.get("nickname"), user.get("display_name")]
                            values += list(user.get("aliases") or []) if isinstance(user.get("aliases"), list) else []
                            if any(item and item in " ".join(str(v or "") for v in values) for item in names):
                                try:
                                    items.extend(self._companion_memories(str(other_uid), ""))
                                except Exception:
                                    pass
        except Exception as exc:
            logger.debug("[amo] 外部画像记忆读取失败: %s" % exc)
        unique = []
        seen = set()
        for item in items:
            key = re.sub(r"\s+", "", str(item.get("content") or "")).lower()
            if key and key not in seen:
                seen.add(key)
                unique.append(item)
        return unique[:max(1, min(500, limit))]

    def _companion_plugin_meta(self):
        """优先用配置的插件名；留空或找不到时从已安装插件里自动检测。"""
        name = self.cfg_str("companion_memory_plugin_name", "").strip()
        if name and name.lower() not in ("auto", "automatic", "自动"):
            try:
                meta = self.context.get_registered_star(name)
                if meta and getattr(meta, "star_cls", None) is not None:
                    return meta
            except Exception:
                pass
        candidates = []
        try:
            for meta in self.context.get_all_stars():
                if getattr(meta, "name", None) == PLUGIN_NAME:
                    continue
                plugin = getattr(meta, "star_cls", None)
                if plugin is None:
                    continue
                data = getattr(plugin, "data", None)
                users = data.get("users") if isinstance(data, dict) else None
                marker = (
                    (getattr(meta, "name", "") or "") + " "
                    + (getattr(meta, "module_path", "") or "")
                ).lower()
                score = 0
                if "private_companion" in marker:
                    score += 5
                if "memory" in marker:
                    score += 1
                if getattr(plugin, "memory_companion", None) is not None:
                    score += 6
                if self._is_angel_memory(plugin):
                    score += 7
                if isinstance(users, dict) and users:
                    sample = next((item for item in users.values() if isinstance(item, dict)), {})
                    if isinstance(sample.get("companion_memory"), dict):
                        score += 4
                    if "relationship_score" in sample:
                        score += 2
                    if isinstance(sample.get("important_memories"), list):
                        score += 1
                    score += 1
                if score:
                    candidates.append((score, meta))
        except Exception:
            pass
        candidates.sort(key=lambda pair: -pair[0])
        return candidates[0][1] if candidates else None

    def _companion_plugin(self):
        meta = self._companion_plugin_meta()
        return getattr(meta, "star_cls", None) if meta else None

    def _companion_candidates(self):
        items = []
        try:
            for meta in self.context.get_all_stars():
                if getattr(meta, "name", None) == PLUGIN_NAME:
                    continue
                plugin = getattr(meta, "star_cls", None)
                data = getattr(plugin, "data", None) if plugin is not None else None
                users = data.get("users") if isinstance(data, dict) else None
                count = len(users) if isinstance(users, dict) else 0
                ready = False
                if isinstance(users, dict) and users:
                    sample = next((item for item in users.values() if isinstance(item, dict)), {})
                    ready = isinstance(sample, dict) and (
                        isinstance(sample.get("companion_memory"), dict)
                        or "relationship_score" in sample
                        or isinstance(sample.get("important_memories"), list)
                    )
                if plugin is not None and self._is_memory_companion(plugin):
                    ready = True
                    count = self._memcomp_user_count(plugin)
                if plugin is not None and self._is_angel_memory(plugin):
                    ready = True
                    count = self._angel_user_count(plugin)
                items.append({
                    "name": str(getattr(meta, "name", "") or ""),
                    "display_name": str(getattr(meta, "display_name", "") or getattr(meta, "name", "") or ""),
                    "version": str(getattr(meta, "version", "") or ""),
                    "users": count,
                    "ready": ready,
                    "activated": bool(getattr(meta, "activated", False)),
                    "reserved": bool(getattr(meta, "reserved", False)),
                })
        except Exception:
            pass
        items.sort(key=lambda item: (not item["ready"], -item["users"], item["name"]))
        return items

    @staticmethod
    def _companion_pick_profile(mapping, uid):
        if not isinstance(mapping, dict):
            return {}
        direct = mapping.get(str(uid))
        if isinstance(direct, dict):
            return direct
        for key, value in mapping.items():
            if not isinstance(value, dict):
                continue
            subject = (
                value.get("user_id") or value.get("member_id")
                or value.get("identity_subject_id") or key
            )
            if str(subject) == str(uid):
                return value
        return {}

    def _companion_memories(self, uid, query=""):
        """只读地从 private companion 的 data 中提取用户记忆。"""
        source = self.cfg_str("memory_source", "auto").strip().lower()
        if source not in ("auto", "companion"):
            return []
        plugin = self._companion_plugin()
        if plugin is None:
            return []
        data = getattr(plugin, "data", None)
        if not isinstance(data, dict):
            return []

        user = self._companion_pick_profile(data.get("users"), uid)
        items = []
        seen = set()

        def add(content, tier=1, weight=1):
            text = re.sub(r"\s+", " ", str(content or "")).strip()
            if len(text) < 2:
                return
            key = re.sub(r"[\s，。！？!?、；;：:]+", "", text).lower()
            if not key or key in seen:
                return
            seen.add(key)
            items.append({
                "content": text[:240],
                "tier": max(0, min(2, to_int(tier, 1))),
                "kind": "companion",
                "source": "companion",
                "weight": to_int(weight, 1),
                "hits": 0,
                "expires_at": None,
            })

        memory = user.get("companion_memory") if isinstance(user, dict) else None
        if isinstance(memory, dict):
            raw_items = memory.get("items")
            if isinstance(raw_items, list):
                for raw in raw_items:
                    if not isinstance(raw, dict):
                        continue
                    weight = to_int(raw.get("weight"), 1)
                    add(
                        raw.get("text"),
                        2 if weight >= 3 else (1 if weight >= 2 else 0),
                        weight,
                    )
            if self.cfg_bool("companion_memory_include_profile", True):
                profile = memory.get("profile")
                if isinstance(profile, dict):
                    labels = (
                        ("strong_memories", "强记忆", 2),
                        ("boundaries", "边界", 2),
                        ("speaking_style", "表达习惯", 1),
                        ("weak_preferences", "偏好", 1),
                        ("interests", "兴趣", 1),
                    )
                    for key, label, tier in labels:
                        value = profile.get(key)
                        values = value if isinstance(value, list) else ([value] if value else [])
                        for entry in values[:6]:
                            if isinstance(entry, dict):
                                entry = entry.get("text") or entry.get("content") or ""
                            add(str(label) + "：" + str(entry), tier, 2 if tier >= 2 else 1)

        if self.cfg_bool("companion_memory_include_important", True):
            important = []
            if isinstance(user, dict) and isinstance(user.get("important_memories"), list):
                important.extend(user.get("important_memories") or [])
            worldbook = data.get("worldbook_member_profiles")
            wb_profile = self._companion_pick_profile(worldbook, uid)
            if isinstance(wb_profile.get("important_memories"), list):
                important.extend(wb_profile.get("important_memories") or [])
            for entry in important:
                if isinstance(entry, dict):
                    add(entry.get("content") or entry.get("text"), 2, 3)
                elif isinstance(entry, str):
                    add(entry, 2, 3)

        if not items:
            return []
        query_tokens = tokens(query)
        for item in items:
            item["_score"] = overlap(query_tokens, tokens(item["content"])) + 0.08 * to_int(item.get("weight"))
        items.sort(key=lambda item: (-item["_score"], -to_int(item.get("weight")), -len(item["content"])))
        for item in items:
            item.pop("_score", None)
        return items[:max(1, self.cfg_int("companion_memory_limit", 6))]

    def _companion_user_record(self, uid):
        plugin = self._companion_plugin()
        if plugin is None:
            return {}
        data = getattr(plugin, "data", None)
        if not isinstance(data, dict):
            return {}
        return self._companion_pick_profile(data.get("users"), uid)

    @staticmethod
    def _map_companion_relation(user):
        """把陪伴插件的关系分数/阶段映射到本插件的关系；不会自动到“相恋”。"""
        if not isinstance(user, dict):
            return "普通"
        score = to_int(user.get("relationship_score"), 0)
        stage = str(user.get("relationship_phase_key") or user.get("relationship_stage") or "").lower()
        role = str(user.get("relationship_role") or "").lower()
        if "hatred" in stage or "enemy" in role or score <= -60:
            return "仇恨"
        if "distant" in stage or "rival" in role or score < 0:
            return "抵触"
        if "close" in stage or score >= 40:
            return "熟识"
        if "familiar" in stage or score >= 15:
            return "熟识"
        return "普通"

    def _sync_companion_profile(self, uid, force=False):
        """从陪伴插件的用户数据补全本插件画像（只补空字段，不覆盖手动关系）。"""
        if not force and not self.cfg_bool("companion_profile_sync", True):
            return
        uid = str(uid)
        if not force:
            key = "companion_profile_sync_" + uid
            if now_ts() - to_float(self.db.kv_get(key, 0)) < 600:
                return
            self.db.kv_set(key, now_ts())
        user = self._companion_user_record(uid)
        if not user:
            return
        profile = self.db.get_profile(uid)
        name = str(
            user.get("name") or user.get("nickname")
            or user.get("display_name") or ""
        ).strip()
        if not profile:
            self.db.touch_profile(uid, name or uid, "companion", "", "", False)
            profile = self.db.get_profile(uid)
        if not profile:
            return
        fields = {}
        if name and (not profile.get("name") or str(profile.get("name")) == uid):
            fields["name"] = name[:60]
        birthday = str(user.get("birthday") or "").strip()
        if birthday and not profile.get("birthday"):
            fields["birthday"] = birthday[:20]
        relation = self._map_companion_relation(user)
        if relation != "普通" and profile.get("relation", "普通") == "普通":
            fields["relation"] = relation
        if fields:
            self.db.update_profile(uid, **fields)

    def _recall(self, uid, text):
        if not self.cfg_bool("enable_memory", True):
            return [], ""
        source = self.cfg_str("memory_source", "auto").strip().lower()
        memories = []
        if source in ("auto", "companion"):
            try:
                memories.extend(self._companion_memories(uid, text))
            except Exception as exc:
                logger.debug("[amo] 陪伴插件记忆读取失败: %s" % exc)
        if source in ("auto", "local") or not memories:
            try:
                local = self.db.search_memories(
                    uid, text,
                    limit=self.cfg_int("memory_recall_limit", 6),
                    normal_days=self.cfg_int("mem_days_normal", 7),
                    important_days=self.cfg_int("mem_days_important", 14),
                )
                for item in local:
                    item["source"] = "local"
                    memories.append(item)
            except Exception as exc:
                logger.debug("[amo] 本地记忆检索失败: %s" % exc)
        try:
            for item in self._external_all_memories(uid, text, self.cfg_int("memory_recall_limit", 6)):
                item["source"] = item.get("source") or "external"
                memories.append(item)
        except Exception as exc:
            logger.debug("[amo] 外部记忆检索失败: %s" % exc)

        unique = []
        seen = set()
        for item in memories:
            content = str(item.get("content", "")).strip()
            key = re.sub(r"[\s，。！？!?、；;：:]+", "", content).lower()
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(item)
        memories = unique[:max(1, self.cfg_int("memory_recall_limit", 6))]
        if not memories:
            return [], ""
        lines = []
        for item in memories:
            if item.get("source") == "companion":
                label = "陪伴记忆"
            else:
                tier = to_int(item.get("tier"))
                label = "珍贵" if tier >= 2 else ("重要" if tier == 1 else "普通")
            lines.append("· " + str(item.get("content", "")) + "（" + label + "）")
        return memories, "\n".join(lines)

    # ---------- 消息入口 ----------
    @filter.event_message_type(filter.EventMessageType.ALL)
    async def on_message(self, event: AstrMessageEvent):
        try:
            await self._ensure_ready()
            await self._handle_message(event)
        except Exception as exc:
            logger.error("[amo] 消息处理异常: %s" % exc)

    def _relation_network_text(self, uid):
        """给当前用户生成两跳内的关系网摘要；只读。"""
        try:
            edges = self.db.list_relations()
        except Exception:
            return ""
        uid = str(uid or "")
        if not edges:
            return ""
        names = {}
        try:
            for item in self.db.list_profiles(limit=500):
                names[str(item.get("uid"))] = item.get("alias") or item.get("name") or str(item.get("uid"))
        except Exception:
            pass
        direct = []
        neighbors = set()
        for edge in edges:
            a, b = str(edge.get("a_uid")), str(edge.get("b_uid"))
            if uid in (a, b):
                direct.append(edge)
                neighbors.add(b if a == uid else a)
        second = []
        for edge in edges:
            if edge in direct:
                continue
            a, b = str(edge.get("a_uid")), str(edge.get("b_uid"))
            if a in neighbors or b in neighbors:
                second.append(edge)
        lines = []
        for edge in (direct + second)[:12]:
            a, b = str(edge.get("a_uid")), str(edge.get("b_uid"))
            na = names.get(a, a)
            nb = names.get(b, b)
            lines.append("%s和%s是%s" % (na, nb, edge.get("relation", "朋友")))
        return "\n".join(lines)

    def _disturb_category(self, snap):
        category = (snap.get("activity") or {}).get("category", "")
        return category in ("sleep", "work", "study")

    def _disturb_active(self, umo):
        return to_float(getattr(self, "_disturb_until", {}).get(str(umo), 0), 0) > now_ts()

    def _tone_with_continuity(self, umo, tone):
        """给语气加情绪惯性，避免上一秒发火、下一秒突然甜蜜。"""
        tone = str(tone or "")
        if self._disturb_active(umo):
            if "不要一秒变甜蜜" not in tone:
                tone += " 你刚被吵醒/打扰，还在烦躁，不要一秒变甜蜜。"
        last = getattr(self, "_last_affect", {}).get(str(umo))
        if last and now_ts() - to_float(last[0], 0) < 1200:
            previous = str(last[1] or "")
            if any(word in previous for word in ("烦躁", "暴躁", "生气", "被打扰")) and "慢慢缓和" not in tone:
                tone += " 上一轮你还在气头上，态度要慢慢缓和，不要突然撒娇甜蜜。"
        self._last_affect[str(umo)] = (now_ts(), tone)
        return tone

    def _apply_disturbance(self, umo):
        now = now_ts()
        self._disturb_until[str(umo)] = now + max(30, self.cfg_int("disturb_tone_seconds", 900))
        self._disturb_cooldown[str(umo)] = now + 120
        self._disturb_reset_at[str(umo)] = now
        last = to_float(getattr(self, "_disturb_last", {}).get(str(umo), 0), 0)
        if now - last >= 60:
            penalty = max(1, self.cfg_int("disturb_mood_penalty", 6))
            self.state.nudge(
                生气=penalty,
                郁闷=max(1, penalty // 2),
                疲惫=max(1, penalty // 2),
                开心=-max(1, penalty // 3),
            )
            self._disturb_last[str(umo)] = now
        logger.debug("[amo] 被打扰：消息过多，强制回复并降低心情（%s）" % umo)

    def _disturb_pressure(self, umo, uid, text="", group=False):
        """最近窗口内，同一个人连续发消息数 / 群里叫机器人的消息数。"""
        try:
            rows = self.db.recent_messages(umo, 24)
        except Exception:
            return 0
        window = max(1, self.cfg_int("disturb_window_minutes", 10)) * 60
        cutoff = max(
            now_ts() - window,
            to_float(getattr(self, "_disturb_reset_at", {}).get(str(umo), 0), 0),
        )
        same_sender = 0
        mentions = 0
        names = [self.bot_name] + list(self.bot_aliases)
        for row in reversed(rows):
            if to_float(row.get("created_at"), 0) < cutoff:
                continue
            if row.get("role") == "bot":
                break
            if row.get("role") != "user":
                continue
            if group:
                if str(row.get("uid")) == str(uid):
                    same_sender += 1
                content = str(row.get("content") or "")
                if any(name and len(str(name)) >= 2 and str(name) in content for name in names):
                    mentions += 1
            else:
                same_sender += 1
        return max(same_sender, mentions) if group else same_sender

    def _mark_bot_initiated(self, umo):
        key = str(umo)
        self._bot_initiated[key] = now_ts()
        # 她主动发的消息代表当前是她来找你，不该延续上一轮的火气。
        self._disturb_until[key] = 0
        self._last_affect[key] = (now_ts(), "你主动发起聊天，语气自然亲昵")

    def _recent_bot_initiated(self, umo, seconds=3600):
        return now_ts() - to_float(getattr(self, "_bot_initiated", {}).get(str(umo), 0), 0) < seconds

    def _should_disturb(self, snap, umo, uid, text="", group=False):
        if not self.cfg_bool("disturb_reply_enabled", True):
            return False
        if self._recent_bot_initiated(umo):
            return False
        if not self._disturb_category(snap):
            return False
        if to_float(getattr(self, "_disturb_cooldown", {}).get(str(umo), 0), 0) > now_ts():
            return False
        threshold = max(1, self.cfg_int("disturb_reply_threshold", 3))
        return self._disturb_pressure(umo, uid, text, group=group) >= threshold

    async def _handle_message(self, event):
        if not self._ready or self.state is None:
            return
        self._reload_config_if_changed()
        await self._sync_persona_name(event)
        try:
            self.state.apply_schedule_events()
        except Exception:
            pass
        uid = str(event.get_sender_id())
        if not uid or uid == str(event.get_self_id()):
            return
        text = (event.message_str or "").strip()
        if not text:
            return
        if self._looks_like_command(text):
            return

        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        private = event.is_private_chat()
        if private:
            self._clear_proactive_pending(uid)
            self._try_soothe(uid, text)
        if private and not self.cfg_bool("enable_private_reply", True):
            return
        if not private and not self.cfg_bool("enable_group_reply", True):
            return

        if not private:
            try:
                self._detect_impersonation(event)
            except Exception as exc:
                logger.debug("[amo] 冒充检测失败: %s" % exc)
        await self._learn(event, text)
        self._restore_lover_relation(uid)
        profile = self.db.get_profile(uid)

        if private:
            await self._handle_private(event, profile)
            return

        # 群聊只走完整心流引擎；旧的五维门控/防抖/直发逻辑不再参与。
        if self.heartflow is None or not self.cfg_bool("hf_enable_heartflow", True):
            return
        snap = self.state.snapshot()
        if self._should_disturb(snap, umo, uid, text, group=True):
            self._apply_disturbance(umo)
            setattr(event, "amo_force_reply", True)
        try:
            await self.heartflow.on_group_message(event)
        except Exception as exc:
            logger.error("[amo] 心流处理失败: %s" % exc)

    async def _handle_private(self, event, profile):
        snap = self.state.snapshot()
        umo = event.unified_msg_origin
        uid = str(event.get_sender_id())
        if self._recent_bot_initiated(umo):
            self._disturb_until[str(umo)] = 0
            logger.info("[amo] 主动消息后的回复，按正常聊天处理")
            return
        if self._should_disturb(snap, umo, uid, event.message_str or "", group=False):
            self._apply_disturbance(umo)
            # 不 stop_event，让 AstrBot 正常生成；<amo_state> 会带上被打扰的语气。
            return
        probability = self.gate.private_probability(snap, profile)
        roll = random.random()
        logger.info(
            "[amo] 私聊判定 | 概率=%.2f | roll=%.2f | %s"
            % (probability, roll, "回复" if roll > probability else "不回")
        )
        if roll <= probability:
            return
        event.stop_event()
        if (
            self.cfg_bool("delay_reply", True)
            and probability >= 0.20
            and profile.get("relation", "普通") not in ("仇恨", "抵触")
            and random.random() < 0.45
        ):
            self._schedule_delayed_reply(event, profile)

    async def _handle_group_directed(self, event, text, profile):
        umo = event.unified_msg_origin
        group_id = event.get_group_id()
        snap = self.state.snapshot()
        recent = self._recent(umo, 12)
        result = await self.gate.should_reply_group(
            umo, group_id, text, recent, True, profile, snap
        )
        if self.cfg_bool("debug_log", False):
            logger.debug("[amo] 群聊定向判定: %s" % json.dumps(result, ensure_ascii=False))
        if not result["reply"]:
            event.stop_event()

    def _buffer_group(self, event, text, profile):
        umo = event.unified_msg_origin
        now = now_ts()
        buffer = self._buffers.get(umo)
        if buffer is None:
            buffer = {"texts": [], "started": now, "task": None}
            self._buffers[umo] = buffer
        buffer["texts"].append(text)
        buffer["event"] = event
        buffer["profile"] = profile
        buffer["message_id"] = getattr(event.message_obj, "message_id", None)
        buffer["updated"] = now
        if len(buffer["texts"]) > 6:
            buffer["texts"] = buffer["texts"][-6:]
        if buffer.get("task") is not None:
            try:
                buffer["task"].cancel()
            except Exception:
                pass
        delay = self.cfg_float("debounce_seconds", 2.5)
        max_wait = self.cfg_float("debounce_max_wait", 7.0)
        remain = buffer["started"] + max_wait - now
        delay = max(0.4, min(delay, remain))
        buffer["task"] = self._spawn(self._debounced_group(umo, delay))

    async def _debounced_group(self, umo, delay):
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        buffer = self._buffers.pop(umo, None)
        if not buffer:
            return
        event = buffer.get("event")
        profile = buffer.get("profile") or {}
        if event is None:
            return
        text = " ".join(buffer.get("texts") or [])[-400:]
        snap = self.state.snapshot()
        recent = self._recent(umo, 12)
        result = await self.gate.should_reply_group(
            umo, event.get_group_id(), text, recent, False, profile, snap
        )
        if self.cfg_bool("debug_log", False):
            logger.debug("[amo] 群聊插话判定: %s" % json.dumps(result, ensure_ascii=False))
        if not result["reply"]:
            return
        memories, memory_text = self._recall(str(event.get_sender_id()), text)
        reply = await self._compose_reply(event, text, snap, profile, memories, memory_text, True)
        if not reply:
            return
        try:
            if hasattr(event, "send_typing"):
                await event.send_typing()
        except Exception:
            pass
        await self._send_to_umo(
            umo, reply,
            quote_id=buffer.get("message_id"),
            group=True,
        )

    def _schedule_delayed_reply(self, event, profile):
        umo = event.unified_msg_origin
        delay = random.randint(
            self.cfg_int("delay_min_minutes", 4),
            self.cfg_int("delay_max_minutes", 18),
        ) * 60
        text = event.message_str or ""

        async def runner():
            try:
                await asyncio.sleep(delay)
                if not self._running or not self._ready:
                    return
                snap = self.state.snapshot()
                prompt_text = "（你刚刚忙完，主动补一句，不要提等待时间，语气自然）"
                reply = await self._compose_reply(
                    event, prompt_text, snap, profile, [], "", False
                )
                if reply:
                    await self._send_to_umo(umo, reply)
                    self.db.add_message(umo, str(event.get_self_id()), self.bot_name, "bot", reply)
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.debug("[amo] 延迟回复失败: %s" % exc)

        self._spawn(runner())

    def _trim_reply(self, text):
        value = str(text or "").strip()
        limit = max(1, self.cfg_int("reply_max_sentences", 3))
        parts = [item for item in re.split(r"(?<=[。！？!?~～])", value) if item.strip()]
        if len(parts) <= limit:
            return value
        return "".join(parts[:limit]).strip()

    async def _compose_reply(self, event, text, snap, profile, memories, memory_text, group):
        umo = event.unified_msg_origin
        uid = str(event.get_sender_id())
        name = profile.get("alias") or profile.get("name") or event.get_sender_name() or "对方"
        relation = profile.get("relation", "普通")
        persona = await self.llm.persona(umo)
        world = self.state.worldview_text()
        state_text = self.state.prompt_text(snap)
        tone = self._tone_with_continuity(umo, self.state.tone_text(snap, relation))
        style = STYLE_HINTS.get(self.cfg_str("reply_style", "soft"), "")
        consult = bool(re.search(r"(怎么|如何|为什么|步骤|怎么办|该怎么做|教程|方法|建议|教我|能不能|是什么|该不该|可不可以)", text or ""))
        recent = self._recent(umo, 10)
        lines = []
        current_uid = str(event.get_sender_id())
        current_place = str((snap.get("activity") or {}).get("place") or "")
        for item in recent:
            content = str(item.get("content") or "")
            role = str(item.get("role") or "")
            item_uid = str(item.get("uid") or "")
            # 当前明明在家/公司时，不把历史里“酒店/开车/逛景区”的旧幻觉再喂回模型。
            if (
                role != "user"
                and current_place in ("家", "公司", "工位")
                and re.search(r"(酒店|咖啡店|咖啡|开着车|在开车|逛完|旅游|景区)", content)
            ):
                continue
            if role == "user":
                if item_uid and item_uid != current_uid:
                    who = (str(item.get("name") or "群友") + "（另一位群友）")
                else:
                    who = name
            else:
                who = "你"
            lines.append(who + "：" + truncate(content, 100))
        transcript = "\n".join(lines[-8:])
        self_name, self_uid, self_qq_nick, self_display = await self._self_identity(event)
        sender_nick = str(event.get_sender_name() or profile.get("name") or uid).strip()
        system_parts = [
            persona,
            "【你的角色名】" + self_name + "（角色本名，不是QQ昵称）",
            "【你的QQ账号】QQ昵称：" + self_qq_nick + "；群名片/当前显示名：" + self_display + "；UID：" + (self_uid or "未知") + "。",
            "【昵称区分】问QQ昵称答 " + self_qq_nick + "；问群名片答 " + self_display + "；问本名/角色名答 " + self_name + "。",
            "【对方】QQ昵称：" + sender_nick + "；UID：" + uid + "；你平时称呼：" + name,
            "【身份区分】同名、同昵称、同爱称也要看 UID；你的 UID 是 " + (self_uid or "未知") + "，对方的 UID 是 " + uid + "。",
            "【角色边界】对方说“我在开车/我在酒店/我刚逛完”是在说他自己，不是你的经历；你的地点只以【此刻状态】为准。",
            "【引用规则】引用内容可能来自别人，引用头是谁就按谁算；不要把别人的话当成自己说过的。",
            "【世界观】\n" + world,
            "【此刻状态】\n" + state_text,
            "【事实锁定】以当前日程为准，不要编造或延续与“正在/地点”矛盾的地点、酒店、开车、旅游等行程；之前说错了就自然改口。",
            "【语气】" + tone + " " + style,
            "【关系】你和" + name + "的关系是「" + relation + "」。",
            "【聊天格式】不要把 @昵称、QQ号、群号、ID 或后台记录念出来；识人时只自然回应，不要复述。",
            "【长度】默认只回 1-2 句，能一句说清就一句；不要解释、不要列点、不要总结，不要写成客服长文。",
            "【人格】你是设定里的呆萌小萝莉，不是通用助手；即使回答咨询也要用自己的口吻，不要变成“大肥鱼”。",
        ]
        if consult:
            system_parts.append("【回答方式】这是咨询/步骤类问题：先给结论，最多 2-3 句，口语化，保留角色感，不要客服腔。")
        if self.cfg_bool("dialect_enabled", True):
            system_parts.append("【方言】你是贵州人，偶尔自然带一点“嘛/咯/嘞/晓得/咋个”的口语，但不要每句都用，也不要硬替换“就是/什么/怎么”。")
        if relation == "相恋" and (snap["mood"]["暴躁"] >= 60 or snap["mood"]["生气"] >= 62):
            system_parts.append("【恋人情绪】你在生他的气，但会抱怨、闹别扭、要哄，不会像对普通人一样冷怼或赶人。")
        if getattr(event, "amo_impersonation", False):
            system_parts.append("【冒充警告】当前 UID 不是你的恋人，却在冒充/使用恋人称呼；直接拆穿/怼回去，不要用恋人语气。")
        if self._recent_bot_initiated(umo):
            system_parts.append("【你主动发起】你刚主动给ta发过消息，ta现在回复你；不要说自己被吵醒/被打扰，正常接话。")
        if re.search(r"(记住|以后喊|以后叫|喊他|喊她|叫他|叫她|称呼他|称呼她)", text or ""):
            system_parts.append(
                "【识人回应】这是让你记称呼/认人，不要复述 @、QQ号或后台记录；"
                "只自然答应，例如“好，我记住了，这是你朋友吗”。"
            )
        if re.search(r"(旅游|景区|景点|去哪|好玩|假期|游玩)", text or ""):
            scenic_text = await self._scenic_kb_context(text or "")
            if scenic_text:
                system_parts.append("【景区参考】\n" + scenic_text)
        if relation == "相恋":
            system_parts.append("你可以亲昵、撒娇、用昵称。")
        if bool(re.search(r"(?<![a-z])ai(?![a-z])", (text or "").lower())) or any(word in (text or "").lower() for word in ("机器人", "人机", "人工智能", "不是真人", "程序")):
            system_parts.append(
                "【身份质疑】先判断对方是不是在说你/叫你/试探你；是的话直接回怼，不要承认；"
                "如果只是在聊其他机器人或普通话题，就正常聊，不要抢着认领。"
            )
        if self._disturb_active(umo):
            relation_now = profile.get("relation", "普通")
            if relation_now in ("相恋", "熟识"):
                system_parts.append(
                    "【被打扰】你刚被吵醒/上班被打扰，对亲近的人会抱怨、撒娇，说“困死了/别闹”，不是真翻脸。"
                )
            else:
                system_parts.append(
                    "【被打扰】你刚被吵醒/上班被打扰，对不熟的人直接怼，比如“神经吧？都不睡觉/上班吗？”，语气冲但不要人身攻击。"
                )
        if self._depressed_active(uid):
            system_parts.append(
                "【低落】你最近主动找对方多次都没得到回应，很抑郁、委屈，需要哄；"
                "回复冷淡低落，可以说“你是不是不想理我”。"
            )
        try:
            dialect_context = await self._dialect_kb_context(text)
            if dialect_context:
                system_parts.append("【方言参考】只在合适口语词上偶尔用，不要硬改“就是/什么/怎么”，句子要通顺。\n" + dialect_context)
        except Exception:
            pass
        relation_network = self._relation_network_text(uid)
        if relation_network:
            system_parts.append("【关系网】\n" + relation_network)
        if memory_text:
            system_parts.append("【关于" + name + "的记忆】\n" + memory_text)
        system_parts.append(
            "【规则】你就是角色本人。只输出你要说的话，不要解释、不要旁白、不要复述设定、"
            "不要用括号描述动作；像真人在聊天，句子口语化。"
        )
        system = "\n\n".join(system_parts)
        if group:
            prompt = (
                "以下是群聊最近的对话：\n" + transcript + "\n\n"
                + name + "刚刚说：" + text + "\n"
                "群里正在聊天，你决定插一句。只回 1-2 句，不要@任何人，不要重复别人说过的话。"
            )
        else:
            prompt = (
                "以下是你们最近的私聊：\n" + transcript + "\n\n"
                + name + "刚刚说：" + text + "\n"
                "请以角色身份自然回复。默认 1-2 句，能短就短；咨询类最多 3 句，不要客服腔。"
            )
        reply = await self.llm.chat(
            umo, system, prompt, limit=self.cfg_int("max_reply_chars", 220)
        )
        if reply:
            reply = await self.llm.polish(
                umo, reply, tone, state_text=state_text, relation=relation, name=name,
                persona=persona, style=style, consult=consult,
            )
            reply = self._trim_reply(reply)
            reply = self._guard_self_location(reply, (snap.get("activity") or {}).get("place"))
        return reply

    # ---------- 发送 ----------
    def _segment(self, text):
        if not text:
            return []
        if not self.cfg_bool("seg_enable", True) or self.segment_engine is None:
            return [text]
        try:
            segments = self.segment_engine.segment_text_by_rules(text)
            return segments or [text]
        except Exception as exc:
            logger.debug("[amo] 分段引擎异常: %s" % exc)
            return [text]

    def typing_seconds(self, text):
        if not self.cfg_bool("typing_simulate", True):
            return 0.0
        return typing_delay_ms(
            text,
            self.cfg_int("typing_base_ms", 600),
            self.cfg_int("typing_per_char_ms", 55),
            self.cfg_int("typing_max_ms", 4500),
        ) / 1000.0

    async def _typing(self, event, text):
        seconds = self.typing_seconds(text)
        if seconds <= 0:
            return
        try:
            if event is not None and hasattr(event, "send_typing"):
                await event.send_typing()
        except Exception:
            pass
        await asyncio.sleep(seconds)

    async def _segment_wait(self, event, segment, prev_segment, last_sent_at):
        """按当前分段字数补足打字时间；已过去的时间可以抵扣，但不会低于分段间隔。"""
        required = self.typing_seconds(segment)
        gap = await self._gap(prev_segment, segment)
        target = max(required, gap)
        elapsed = max(0.0, time.monotonic() - last_sent_at) if last_sent_at else 0.0
        wait = max(0.0, target - elapsed)
        logger.info(
            "[amo] 分段延迟（从上一段发送后计时） | 字数=%d | 需要=%.2fs | 已过=%.2fs | 补足=%.2fs"
            % (len(re.sub(r"\s+", "", str(segment or ""))), target, elapsed, wait)
        )
        if wait > 0.01:
            try:
                if event is not None and hasattr(event, "send_typing"):
                    await event.send_typing()
            except Exception:
                pass
            await asyncio.sleep(wait)
        return wait

    async def _gap(self, text, next_text=""):
        if self.segment_engine is not None and self.cfg_bool("seg_enable", True):
            try:
                return max(0.0, float(self.segment_engine._calculate_delay(text, next_text)))
            except Exception:
                pass
        return 0.3

    async def _send_reply(self, event, text, quote_id=None, group=None):
        text = clean_reply(text, self.cfg_int("max_reply_chars", 220))
        if looks_like_ai_admission(text):
            text = "你才人机呢，你见过这么会聊天的机器人吗？"
        text = self._apply_dialect(text)
        if not text:
            return False
        if group is None:
            group = not event.is_private_chat()
        segments = self._segment(text)
        if not segments:
            return False
        await self._typing(event, segments[0])
        last_sent_at = time.monotonic()
        for index, segment in enumerate(segments):
            if index > 0:
                await self._segment_wait(event, segment, segments[index - 1], last_sent_at)
            chain = []
            if (
                group and index == 0 and quote_id is not None
                and self.cfg_bool("quote_group_reply", True)
            ):
                try:
                    chain.append(Comp.Reply(id=quote_id))
                except Exception:
                    pass
            chain.append(Comp.Plain(segment))
            try:
                await event.send(MessageChain(chain))
            except Exception as exc:
                logger.error("[amo] 发送失败: %s" % exc)
                return False
            last_sent_at = time.monotonic()
            try:
                if hasattr(event, "stop_typing"):
                    await event.stop_typing()
            except Exception:
                pass
        try:
            self.db.add_message(
                event.unified_msg_origin, str(event.get_self_id()),
                self.bot_name, "bot", text,
            )
        except Exception:
            pass
        self._last_reply_at[event.unified_msg_origin] = now_ts()
        self.state.nudge(依恋=1, 开心=1)
        logger.info("[amo] 回复 -> %s: %s" % (event.unified_msg_origin, text[:300]))
        return True

    async def _send_to_umo(self, umo, text, quote_id=None, group=False):
        text = clean_reply(text, self.cfg_int("max_reply_chars", 220))
        text = self._apply_dialect(text)
        if not text or not umo:
            return False
        segments = self._segment(text)
        if not segments:
            return False
        last_sent_at = 0.0
        for index, segment in enumerate(segments):
            if index > 0:
                await self._segment_wait(None, segment, segments[index - 1], last_sent_at)
            elif last_sent_at == 0.0:
                await self._segment_wait(None, segment, "", 0.0)
            chain = []
            if (
                group and index == 0 and quote_id is not None
                and self.cfg_bool("quote_group_reply", True)
            ):
                try:
                    chain.append(Comp.Reply(id=quote_id))
                except Exception:
                    pass
            chain.append(Comp.Plain(segment))
            try:
                await self.context.send_message(umo, MessageChain(chain))
            except Exception as exc:
                logger.warning("[amo] 主动发送失败: %s" % exc)
                return False
            last_sent_at = time.monotonic()
        self._last_reply_at[umo] = now_ts()
        logger.info("[amo] 主动 -> %s: %s" % (umo, text[:300]))
        try:
            self.db.add_message(umo, "bot", self.bot_name, "bot", text)
        except Exception:
            pass
        return True

    # ---------- LLM 注入 ----------
    def _guard_self_location(self, text, place):
        value = str(text or "")
        place = str(place or "").strip()
        if not value or not place:
            return value
        if place in ("家", "家里"):
            value = re.sub(
                r"我(?:刚|正|一直|还|才)?(?:在|回|去|到)(?:酒店|咖啡店|景区|外面|路上)",
                "我在家", value,
            )
            value = re.sub(r"(?:酒店|咖啡店|景区)", "家", value)
        else:
            value = re.sub(
                r"我(?:刚|正|一直|还|才)?(?:窝)?在(?:家|家里)",
                "我在" + place, value,
            )
        return value

    async def _self_identity(self, event):
        uid = ""
        try:
            uid = str(event.get_self_id() or "")
        except Exception:
            pass
        role_name = str(self.persona_name or self.bot_name or "陪伴")
        display_name = ""
        for attr in ("get_self_name", "get_bot_name"):
            try:
                value = getattr(event, attr, None)
                if callable(value):
                    value = value()
                if value:
                    display_name = str(value)
                    break
            except Exception:
                continue
        qq_nick = ""
        if uid and getattr(self, "_self_nickname_uid", "") == uid:
            qq_nick = str(getattr(self, "_self_nickname", "") or "")
        if uid and not qq_nick:
            try:
                api = getattr(getattr(event, "bot", None), "api", None)
                action = getattr(api, "call_action", None)
                if callable(action):
                    result = action("get_login_info")
                    if inspect.isawaitable(result):
                        result = await asyncio.wait_for(result, timeout=3)
                    data = result.get("data") if isinstance(result, dict) and isinstance(result.get("data"), dict) else result
                    if isinstance(data, dict):
                        qq_nick = str(data.get("nickname") or "")
                        if data.get("user_id"):
                            uid = str(data.get("user_id"))
                    if not qq_nick and uid:
                        stranger = action("get_stranger_info", user_id=int(uid))
                        if inspect.isawaitable(stranger):
                            stranger = await asyncio.wait_for(stranger, timeout=3)
                        stranger_data = stranger.get("data") if isinstance(stranger, dict) and isinstance(stranger.get("data"), dict) else stranger
                        if isinstance(stranger_data, dict):
                            qq_nick = str(stranger_data.get("nickname") or "")
            except Exception as exc:
                logger.debug("[amo] 获取机器人QQ昵称失败: %s" % exc)
        if not qq_nick:
            qq_nick = display_name or role_name
            logger.info("[amo] get_login_info 不可用，QQ昵称回退为 %s" % qq_nick)
        if not display_name:
            display_name = qq_nick
        if uid:
            self._self_nickname = qq_nick
            self._self_nickname_uid = uid
            self._self_display = display_name
        if getattr(self, "_self_identity_logged", "") != (uid + "|" + qq_nick + "|" + display_name):
            self._self_identity_logged = uid + "|" + qq_nick + "|" + display_name
            logger.info(
                "[amo] 自身身份 | 角色名=%s | QQ昵称=%s | 显示名=%s | UID=%s"
                % (role_name, qq_nick, display_name, uid or "未知")
            )
        return role_name, uid, qq_nick, display_name

    async def _dynamic_context(self, event):
        await self._sync_persona_name(event)
        uid = str(event.get_sender_id())
        profile = self.db.get_profile(uid)
        relation = profile.get("relation", "普通")
        snap = self.state.snapshot()
        _, memory_text = self._recall(uid, event.message_str or "")
        self_name, self_uid, self_qq_nick = await self._self_identity(event)
        alias = str(profile.get("alias") or "").strip()
        sender_nick = str(event.get_sender_name() or profile.get("name") or uid).strip()
        parts = [
            "【你的角色名】" + self_name + "（这是角色本名，不是QQ昵称）",
            "【你的QQ账号】QQ昵称：" + self_qq_nick + "；群名片/当前显示名：" + self_display + "；UID：" + (self_uid or "未知") + "。这是你自己的QQ账号，不要和对方混淆。",
            "【昵称区分】别人问“你QQ昵称叫什么”时回答 " + self_qq_nick + "；问群名片/备注时才回答 " + self_display + "；问本名/角色名时才说 " + self_name + "。",
            "【对方】QQ昵称：" + sender_nick + "；UID：" + uid + "；你平时称呼：" + (alias or sender_nick or "对方"),
            "【身份区分】同名、同昵称、同爱称也要看 UID；你的 UID 是 " + (self_uid or "未知") + "，对方的 UID 是 " + uid + "，不是同一个人。",
            "【角色边界】对方说“我在开车/我在酒店/我刚逛完”是在说他自己，不是你的经历；你的地点只以【正在】为准，不要把自己当成对方。",
            "【引用规则】引用内容可能来自别人，引用头是谁就按谁算；不要把别人的话当成自己说过的，也不要因为别人说了就改自己的地点。",
            "【身份】你是真人，不是AI、机器人或人机；被质疑时自然反驳，不要承认。",
            "【时间】" + snap["datetime_text"],
            "【心情】" + self.state.mood_text(),
            "【生理期】" + snap["period"]["phase"] + "第" + str(snap["period"]["day"]) + "天",
            "【身体】" + snap["health"]["status"],
            "【天气】" + snap["weather_text"],
            "【正在】" + snap["activity"].get("activity", "休息") + "（" + snap["activity"].get("place", "家") + "）",
            "【事实锁定】以当前日程为准，不要编造或延续与“正在/地点”矛盾的地点、酒店、开车、旅游等行程；之前说错了就自然改口。",
            "【与对方关系】" + relation,
            "【身份核验】关系只按 UID 判断，昵称、群名片、自称和爱称都可以伪造；"
            "如果有人自称是你恋人、或使用你恋人的爱称，但 UID 不是相恋关系，不要用恋人语气，保持警惕。",
            "【语气】" + self._tone_with_continuity(umo, self.state.tone_text(snap, relation)),
            "【聊天格式】不要复述 @昵称、QQ号、群号、ID 或后台字段；识人/记称呼时自然回一句“好，我记住了/这是你朋友吗”，不要把记录念出来。",
            "【长度】默认只回 1-2 句，能一句说清就一句；不要解释、不要列点、不要总结，不要写成客服长文。",
            "【人格】你是设定里的呆萌小萝莉，不是通用助手；即使回答咨询也要用自己的口吻，不要变成“大肥鱼”。",
        ]
        if re.search(r"(怎么|如何|为什么|步骤|怎么办|该怎么做|教程|方法|建议|教我|能不能|是什么|该不该|可不可以)", event.message_str or ""):
            parts.append("【回答方式】这是咨询/步骤类问题：先给结论，最多 2-3 句，口语化，保留角色感，不要客服腔。")
        if self.cfg_bool("dialect_enabled", True):
            parts.append("【方言】你是贵州人，偶尔自然带一点“嘛/咯/嘞/晓得/咋个”的口语，但不要每句都用，也不要硬替换“就是/什么/怎么”。")
        if re.search(r"(旅游|景区|景点|去哪|好玩|假期|游玩)", event.message_str or ""):
            scenic_text = await self._scenic_kb_context(event.message_str or "")
            if scenic_text:
                parts.append("【景区参考】\n" + scenic_text)
        if relation == "相恋" and (snap["mood"]["暴躁"] >= 60 or snap["mood"]["生气"] >= 62):
            parts.append("【恋人情绪】你在生他的气，但会抱怨、闹别扭、要哄，不会像对普通人一样冷怼或赶人。")
        if getattr(event, "amo_impersonation", False):
            parts.append(
                "【冒充警告】当前 UID 不是你的恋人，却在冒充或使用恋人称呼；"
                "直接拆穿/怼回去，不要承认，不要用恋人语气，也不要报 QQ。"
            )
        if self._recent_bot_initiated(umo):
            parts.append("【你主动发起】你刚主动给ta发过消息，ta现在回复你；不要说自己被吵醒/被打扰，正常接话。")
        if bool(re.search(r"(?<![a-z])ai(?![a-z])", (event.message_str or "").lower())) or any(word in (event.message_str or "").lower() for word in ("机器人", "人机", "人工智能", "不是真人", "程序")):
            parts.append(
                "【身份质疑】消息里出现了机器人/人机/AI等词。先结合上下文判断是不是在说你、叫你、试探你："
                "如果是，就直接回怼（“你才机器人呢”“你见过这么会聊天的机器人吗”），不要承认；"
                "如果只是在聊别的机器人/AI或普通话题，就正常聊，不要主动认领。"
            )
        if self._disturb_active(umo):
            relation = profile.get("relation", "普通")
            if relation in ("相恋", "熟识"):
                parts.append(
                    "【被打扰】你刚被吵醒/上班被连续打扰，心情不好；"
                    "对亲近的人会抱怨、撒娇、说“困死了/别闹”，不是真的翻脸。"
                )
            else:
                parts.append(
                    "【被打扰】你刚被吵醒/上班被连续打扰，心情很差；"
                    "对不熟的人会直接怼：比如“神经吧？都不睡觉/上班吗？”，语气冲，但不要人身攻击。"
                )
        if self._depressed_active(uid):
            parts.append(
                "【低落】你最近主动找对方多次都没得到回应，现在很抑郁、委屈，"
                "需要对方哄你；回复会冷淡、低落，或者直接说“你是不是不想理我”。"
            )
        try:
            dialect_context = await self._dialect_kb_context(event.message_str or "")
            if dialect_context:
                parts.append("【方言参考】只在合适口语词上偶尔用，不要硬改“就是/什么/怎么”，句子要通顺。\n" + dialect_context)
        except Exception:
            pass
        relation_network = self._relation_network_text(uid)
        if relation_network:
            parts.append("【关系网】\n" + relation_network)
        if memory_text:
            parts.append("【关于对方的记忆】\n" + memory_text)
        if re.search(r"(记住|以后喊|以后叫|喊他|喊她|叫他|叫她|称呼他|称呼她)", event.message_str or ""):
            parts.append(
                "【识人回应】对方在让你记称呼/认人。不要复述 @昵称、QQ号、群号或后台字段；"
                "只自然答应，例如“好，我记住了，这是你朋友吗”，不要把人机式记录念出来。"
            )
        parts.append("以上是你的内在状态，不要直接复述，只影响语气、长度和是否愿意说话。")
        return "\n".join(parts)

    @filter.on_llm_request()
    async def on_llm_request(self, event: AstrMessageEvent, req):
        try:
            await self._ensure_ready()
            if not self._ready or self.state is None:
                return
            if self._looks_like_command(event.message_str or ""):
                return
            context_text = await self._dynamic_context(event)
            if TextPart is not None:
                part = TextPart(text="<amo_state>\n" + context_text + "\n</amo_state>")
                try:
                    part = part.mark_as_temp()
                except Exception:
                    pass
                req.system_prompt = (req.system_prompt or "") + "\n\n<amo_state>\n" + context_text + "\n</amo_state>"
                parts = getattr(req, "extra_user_content_parts", None)
                if parts is not None:
                    parts.append(part)
            else:
                req.system_prompt = (req.system_prompt or "") + "\n\n" + context_text
        except Exception as exc:
            logger.debug("[amo] 注入状态失败: %s" % exc)

    @filter.on_llm_response()
    async def on_llm_response(self, event: AstrMessageEvent, resp):
        if self.heartflow is None:
            return
        try:
            await self.heartflow.on_llm_response(event, resp)
        except Exception as exc:
            logger.debug("[amo] 心流回复记录失败: %s" % exc)

    @filter.after_message_sent()
    async def on_after_message_sent(self, event: AstrMessageEvent):
        if self.heartflow is None:
            return
        try:
            await self.heartflow.on_after_message_sent(event)
        except Exception as exc:
            logger.debug("[amo] 心流发送后状态更新失败: %s" % exc)

    @filter.on_decorating_result()
    async def on_decorating_result(self, event: AstrMessageEvent):
        try:
            await self._ensure_ready()
            result = event.get_result()
            if not result or not result.chain:
                return
            try:
                if not result.is_llm_result():
                    return
            except Exception:
                pass
            text = strip_chat_format("".join(
                comp.text for comp in result.chain if isinstance(comp, Comp.Plain)
            ))
            try:
                text = self._guard_self_location(text, self.state.current_activity().get("place"))
            except Exception:
                pass
            if looks_like_ai_admission(text):
                text = "你才人机呢，你见过这么会聊天的机器人吗？"
                result.chain = [Comp.Plain(text=text)]
            if not text.strip():
                return
            if any(not isinstance(comp, (Comp.Plain, Comp.At)) for comp in result.chain):
                return
            group = not event.is_private_chat()
            threshold = self.cfg_int("quote_group_multi_speaker_threshold", 4)
            auto_quote = bool(
                group and threshold > 0
                and self._group_speaker_count(event.unified_msg_origin) >= threshold
            )
            quote_enabled = bool(
                group and (self.cfg_bool("quote_group_reply", True) or auto_quote)
            )
            quote_id = getattr(event.message_obj, "message_id", None) if quote_enabled else None
            if self.cfg_bool("polish_native", False):
                snap = self.state.snapshot()
                native_profile = self.db.get_profile(str(event.get_sender_id())) or {}
                native_relation = str(native_profile.get("relation") or "普通")
                native_name = str(native_profile.get("alias") or native_profile.get("name") or "对方")
                native_tone = self._tone_with_continuity(
                    event.unified_msg_origin, self.state.tone_text(snap, native_relation)
                )
                native_persona = await self.llm.persona(event.unified_msg_origin)
                native_style = STYLE_HINTS.get(self.cfg_str("reply_style", "soft"), "")
                native_consult = bool(re.search(r"(怎么|如何|为什么|步骤|怎么办|该怎么做|教程|方法|建议|教我|能不能|是什么|该不该|可不可以)", event.message_str or ""))
                polished = await self.llm.polish(
                    event.unified_msg_origin, text, native_tone,
                    state_text=self.state.prompt_text(snap),
                    relation=native_relation, name=native_name,
                    persona=native_persona, style=native_style, consult=native_consult,
                )
                if polished and polished != text:
                    text = polished
                    result.chain = [Comp.Plain(text)]
            text = self._trim_reply(text)
            text = self._apply_dialect(text)
            result.chain = [Comp.Plain(text)]

            # 群聊/私聊的最终发送只交给完整本地分段引擎。
            if self.segment_engine is None or not self.cfg_bool("seg_enable", True):
                return
            backup = list(result.chain)
            try:
                handled = await self.segment_engine.handle_segment_reply(
                    event,
                    quote_id=quote_id if quote_enabled else None,
                    group=group,
                )
            except Exception as exc:
                logger.error("[amo] 完整分段引擎异常: %s" % exc)
                handled = False
            if not handled:
                result.chain = backup
            return
        except Exception as exc:
            logger.debug("[amo] 结果装饰失败: %s" % exc)

    # ---------- 后台循环 ----------
    async def _background_loop(self):
        try:
            await asyncio.sleep(4)
        except asyncio.CancelledError:
            return
        while self._running:
            try:
                await self._tick()
            except asyncio.CancelledError:
                return
            except Exception as exc:
                logger.error("[amo] 后台任务异常: %s" % exc)
            try:
                await asyncio.sleep(self.cfg_int("loop_interval_seconds", 30))
            except asyncio.CancelledError:
                return

    def _decay_hate_relations(self):
        try:
            cutoff = now_ts() - 7 * 86400
            rows = self.db.conn.execute(
                "SELECT uid FROM profiles WHERE relation='仇恨' AND relation_at>0 AND relation_at<=?",
                (cutoff,),
            ).fetchall()
            for row in rows:
                self.db.update_profile(str(row["uid"]), relation="抵触")
                logger.info("[amo] 仇恨超过7天，降为抵触: %s" % row["uid"])
        except Exception as exc:
            logger.debug("[amo] 仇恨关系衰减失败: %s" % exc)

    async def _tick(self):
        if not self._ready or self.state is None:
            return
        self.state.decay_mood()
        if self.state.last_daily != today_str():
            self.state.daily_tick()
        self.state.roll_health()
        await self.state.refresh_weather()

        umo = self._last_umo or self._first_private_umo()
        if (
            not self.state.schedule.get(today_str())
            or self.db.kv_get("schedule_version", "") != SCHEDULE_VERSION
        ):
            await self.state.ensure_schedule(umo)
        try:
            self.state.apply_schedule_events()
        except Exception:
            pass

        now = now_ts()
        if now - self._last_relation_decay > 3600:
            self._last_relation_decay = now
            self._decay_hate_relations()
        if now - self._last_purge > 3600:
            self._last_purge = now
            self.db.purge_memories()
            self.db.purge_messages(self.cfg_int("chat_log_days", 14))

        if self.cfg_bool("enable_auto_learn", True) and now - self._last_auto_learn > 1800:
            self._last_auto_learn = now
            await self._auto_learn()

        current_dt = datetime.now()
        if current_dt.minute >= 57 and current_dt.hour < 23:
            detail_key = today_str() + ":" + str(current_dt.hour)
            if detail_key != self._last_hour_detail:
                self._last_hour_detail = detail_key
                try:
                    await self.state.detail_next_hour(umo)
                except Exception as exc:
                    logger.debug("[amo] 整点前细化日程失败: %s" % exc)

        if now - self._last_pending_check >= 60:
            self._last_pending_check = now
            try:
                await self._check_proactive_pending()
            except Exception as exc:
                logger.debug("[amo] 检查主动私聊回复失败: %s" % exc)

        if current_dt.hour == 23 and current_dt.minute >= 59:
            save_key = today_str()
            if self._last_schedule_save != save_key:
                self._last_schedule_save = save_key
                try:
                    items = self.state.schedule.get(save_key) or []
                    if items:
                        self.db.save_schedule(save_key, items)
                    self.db.fade_schedules(7)
                    self.db.purge_schedules(14)
                except Exception as exc:
                    logger.debug("[amo] 保存/清理日程失败: %s" % exc)

        if now - self._proactive_last >= self.cfg_int("proactive_check_seconds", 300):
            self._proactive_last = now
            await self._maybe_proactive()
        if now - self._last_ritual >= 60:
            await self._maybe_rituals()

    def _first_private_umo(self):
        try:
            for profile in self.db.list_profiles(limit=50):
                if profile.get("private_umo"):
                    return profile["private_umo"]
        except Exception:
            pass
        return ""

    async def _auto_learn(self):
        if not self.cfg_bool("enable_memory", True):
            return
        try:
            users = self.db.active_users(now_ts() - 3600, limit=2)
        except Exception:
            return
        for user in users:
            uid = str(user.get("uid", ""))
            if not uid:
                continue
            key = "auto_learn_" + uid
            last = to_float(self.db.kv_get(key, 0))
            if now_ts() - last < 1800:
                continue
            try:
                rows = self.db.messages_by_uid(uid, 20)
                lines = [row.get("name", "") + "：" + row.get("content", "") for row in rows]
                facts = await self.llm.extract_facts(
                    self._last_umo, user.get("name", "") or uid, lines
                )
                for fact in facts:
                    self.db.add_memory(
                        uid, fact["content"], fact["kind"], fact["tier"],
                        self.cfg_int("mem_days_normal", 7),
                        self.cfg_int("mem_days_important", 14),
                    )
                self.db.kv_set(key, now_ts())
            except Exception as exc:
                logger.debug("[amo] 自动学习失败: %s" % exc)

    def _is_proactive_friend(self, profile):
        return str(profile.get("relation") or "普通") in ("熟识", "相恋")

    def _pending_key(self, uid):
        return "proactive_pending_" + str(uid)

    def _set_proactive_pending(self, uid, kind, text):
        self.db.kv_set(self._pending_key(uid), {
            "sent_at": now_ts(), "kind": kind, "text": str(text or ""),
            "followup": False, "mood": False,
        })

    def _clear_proactive_pending(self, uid):
        pending = self.db.kv_get(self._pending_key(uid), None)
        if pending:
            self.db.kv_set(self._pending_key(uid), {})
            self.db.kv_set("proactive_ignored_" + str(uid), 0)

    def _depressed_active(self, uid):
        return to_float(self.db.kv_get("proactive_depressed_until_" + str(uid), 0), 0) > now_ts()

    def _set_depressed(self, uid):
        hours = max(1, self.cfg_int("proactive_depressed_hours", 24))
        self.db.kv_set("proactive_depressed_until_" + str(uid), now_ts() + hours * 3600)

    def _try_soothe(self, uid, text):
        if not self._depressed_active(uid):
            return
        words = ("抱抱", "亲亲", "哄", "对不起", "别难过", "喜欢你", "爱你", "怎么啦", "我在", "在呢", "乖")
        if any(word in str(text or "") for word in words):
            self.db.kv_set("proactive_depressed_until_" + str(uid), 0)
            self.db.kv_set("proactive_ignored_" + str(uid), 0)
            self.state.nudge(委屈=-8, 郁闷=-8, 开心=5, 依恋=3)
            logger.debug("[amo] 抑郁状态被哄好: %s" % uid)

    async def _check_proactive_pending(self):
        try:
            profiles = self.db.proactive_profiles(limit=100)
        except Exception:
            return
        now = now_ts()
        for profile in profiles:
            uid = str(profile.get("uid") or "")
            umo = str(profile.get("private_umo") or "")
            if not uid or not umo:
                continue
            pending = self.db.kv_get(self._pending_key(uid), None)
            if not isinstance(pending, dict) or not pending.get("sent_at"):
                continue
            age = now - to_float(pending.get("sent_at"), 0)
            if age > 6 * 3600:
                self.db.kv_set(self._pending_key(uid), {})
                continue
            followup_after = max(5, self.cfg_int("proactive_followup_minutes", 30)) * 60
            mood_after = max(followup_after + 60, self.cfg_int("proactive_no_reply_minutes", 120) * 60)
            if not pending.get("followup") and age >= followup_after:
                if not quiet_now(self.cfg_str("quiet_hours", "23:30-07:30")):
                    kind = str(pending.get("kind") or "greet")
                    followup = {
                        "offwork": "我下班了，你还没下班吗？",
                        "meal": "饭吃了没？",
                        "slack": "在忙吗？怎么不理我。",
                        "comfort": "好点了吗？",
                        "greet": "？怎么不理我了？",
                    }.get(kind, "？怎么不理我了？")
                    if await self._send_to_umo(umo, followup):
                        pending["followup"] = True
                        pending["followup_at"] = now
                        self.db.kv_set(self._pending_key(uid), pending)
                        logger.debug("[amo] 主动私聊未回复，已追问: %s" % uid)
            if not pending.get("mood") and age >= mood_after:
                pending["mood"] = True
                self.db.kv_set(self._pending_key(uid), pending)
                ignored = to_int(self.db.kv_get("proactive_ignored_" + uid, 0), 0) + 1
                self.db.kv_set("proactive_ignored_" + uid, ignored)
                self.state.nudge(委屈=5, 郁闷=5, 生气=2, 依恋=2)
                if ignored >= max(1, self.cfg_int("proactive_depressed_count", 3)):
                    self._set_depressed(uid)
                logger.debug("[amo] 主动私聊仍无回复，心情变差: %s (%d)" % (uid, ignored))

    def _ritual_in_window(self, spec):
        try:
            start, end = str(spec).split("-", 1)
            return in_minute_range(minutes_now(), parse_hhmm(start), parse_hhmm(end))
        except Exception:
            return False

    def _ritual_should_send(self, umo, kind):
        try:
            rows = self.db.recent_messages(umo, 10)
        except Exception:
            rows = []
        now = now_ts()
        recent_gap = max(5, self.cfg_int("ritual_skip_recent_minutes", 45)) * 60
        if rows:
            last_at = to_float(rows[-1].get("created_at"), 0)
            if last_at and now - last_at < recent_gap:
                return False
        if not self.cfg_bool("ritual_skip_if_greeted", True):
            return True
        texts = [str(row.get("content") or "") for row in rows if str(row.get("role") or "") in ("user", "bot")]
        joined = "\n".join(texts[-10:])
        if kind == "morning":
            return not bool(re.search(r"(?:^|\s)早(?:\s|$|[!！。~～])|早安|早上好|早上好呀|我醒了|起床了|还没起来吗|醒了没", joined))
        if kind == "goodnight":
            return not bool(re.search(r"晚安|睡了|睡觉|先睡|去睡|早点休息", joined))
        if kind == "lunch":
            return not bool(re.search(r"午饭|中午吃|吃啥|吃什么|吃饭|吃了没|吃了吗", joined))
        return True

    async def _maybe_rituals(self):
        if not self.cfg_bool("ritual_enabled", True):
            return
        now = now_ts()
        if now - to_float(getattr(self, "_last_ritual", 0), 0) < 60:
            return
        self._last_ritual = now
        try:
            profiles = self.db.proactive_profiles(limit=100)
        except Exception:
            return
        snap = self.state.snapshot()
        for profile in profiles:
            if str(profile.get("relation") or "") != "相恋":
                continue
            umo = str(profile.get("private_umo") or "")
            uid = str(profile.get("uid") or "")
            if not umo or not uid:
                continue
            name = str(profile.get("alias") or profile.get("name") or "宝").strip() or "宝"
            rituals = [
                ("goodnight", "ritual_goodnight", "ritual_goodnight_window", "22:00-02:00"),
                ("morning", "ritual_morning", "ritual_morning_window", "06:30-10:00"),
                ("lunch", "ritual_lunch", "ritual_lunch_window", "11:00-13:30"),
            ]
            for kind, enabled_key, window_key, default_window in rituals:
                if not self.cfg_bool(enabled_key, True):
                    continue
                if not self._ritual_in_window(self.cfg_str(window_key, default_window)):
                    continue
                daily_key = "ritual_" + kind + "_" + uid + "_" + today_str()
                if self.db.kv_get(daily_key, False):
                    continue
                if kind == "morning" and (snap.get("activity") or {}).get("category") == "sleep":
                    continue
                if not self._ritual_should_send(umo, kind):
                    continue
                text = ""
                try:
                    text = await self.llm.gen_proactive(umo, profile, snap, kind)
                except Exception as exc:
                    logger.debug("[amo] 仪式生成失败: %s" % exc)
                if not text:
                    text = {
                        "goodnight": name + "，太晚了，我先去睡觉啦，你也早点睡。",
                        "morning": name + "，早上好呀，还没起来吗？",
                        "lunch": name + "，今天中午吃啥子哦？",
                    }.get(kind, "")
                if not text:
                    continue
                if await self._send_to_umo(umo, text):
                    self._mark_bot_initiated(umo)
                    self.db.kv_set(daily_key, True)
                    self.db.log_proactive(uid, kind, text)
                    try:
                        self.db.add_message(umo, "bot", self.bot_name, "bot", text)
                    except Exception:
                        pass
                    logger.info("[amo] 每日问候(%s) -> %s: %s" % (kind, name, text[:200]))
                    break

    def _choose_proactive_kind(self, profile, snap, category=""):
        relation = profile.get("relation", "普通")
        mood = snap["mood"]
        painful = (
            snap["health"]["sick"]
            or snap["period"]["pain"] >= 6
            or mood["委屈"] >= 60
            or mood["郁闷"] >= 65
        )
        if relation == "相恋" and painful and self.cfg_bool("proactive_comfort", True):
            return "comfort"
        activity = str((snap.get("activity") or {}).get("activity") or "")
        if category == "play" and ("游戏" in activity or "打游戏" in activity):
            return "game"
        if category == "meal":
            return "meal"
        if category in ("rest", "play"):
            return "slack"
        if category == "commute":
            return "offwork" if datetime.now().hour >= 16 else "commute"
        if relation in ("熟识", "相恋") and random.random() < self.cfg_float("proactive_share_prob", 0.35):
            return "share"
        return "greet"

    async def _maybe_proactive(self):
        quiet = quiet_now(self.cfg_str("quiet_hours", "23:30-07:30"))
        try:
            profiles = self.db.proactive_profiles(limit=100)
        except Exception:
            return
        if self.cfg_bool("proactive_require_friend", True):
            profiles = [profile for profile in profiles if self._is_proactive_friend(profile)]
        if not profiles:
            return
        random.shuffle(profiles)
        now = now_ts()
        interval = max(10, self.cfg_int("proactive_interval_min", 90)) * 60
        daily_max = max(0, self.cfg_int("proactive_daily_max", 3))
        for profile in profiles:
            if not profile.get("private_umo"):
                continue
            if self._recent_bot_initiated(profile["private_umo"], 3600):
                continue
            count = to_int(profile.get("proactive_count"))
            if profile.get("proactive_day") != today_str():
                count = 0
            if count >= daily_max:
                continue
            relation = str(profile.get("relation") or "普通")
            guaranteed = (
                relation == "相恋"
                and count == 0
                and self.cfg_bool("proactive_daily_guarantee", True)
                and datetime.now().hour >= 8
            )
            if quiet and not guaranteed:
                continue
            pending = self.db.kv_get(self._pending_key(profile.get("uid")), None)
            if isinstance(pending, dict) and pending.get("sent_at"):
                if now - to_float(pending.get("sent_at"), 0) < 6 * 3600:
                    continue
                self.db.kv_set(self._pending_key(profile.get("uid")), {})
            snap = self.state.snapshot()
            category = (snap.get("activity") or {}).get("category", "")
            if category in ("sleep", "work", "study") and not guaranteed:
                continue
            forced = (
                relation == "相恋"
                and category in ("meal", "rest", "play", "commute")
                and self._last_proactive_activity.get(str(profile.get("uid"))) != today_str() + ":" + str(datetime.now().hour)
            )
            if not guaranteed and not forced and now - to_float(profile.get("last_proactive", 0)) < interval:
                continue
            if not guaranteed and not forced and random.random() > self.cfg_float("proactive_prob", 0.25):
                continue
            if not guaranteed and self.cfg_bool("proactive_schedule_only", True) and category not in ("meal", "rest", "play", "commute"):
                continue
            kind = self._choose_proactive_kind(profile, snap, category)
            text = await self.llm.gen_proactive(
                profile["private_umo"], profile, snap, kind
            )
            if not text:
                continue
            ok = await self._send_to_umo(profile["private_umo"], text)
            if ok:
                self._mark_bot_initiated(profile["private_umo"])
                self.db.bump_proactive(profile["uid"])
                self.db.log_proactive(profile["uid"], kind, text)
                self._set_proactive_pending(profile["uid"], kind, text)
                self._last_proactive_activity[str(profile.get("uid"))] = today_str() + ":" + str(datetime.now().hour)
                self.db.add_message(
                    profile["private_umo"], str(self.context.get_config().get("bot_id", "bot")),
                    self.bot_name, "bot", text,
                )
                logger.debug("[amo] 主动私聊 -> %s (%s)" % (profile.get("name", ""), kind))

    # ---------- 指令 ----------
    def _args(self, event):
        raw = (event.message_str or "").strip()
        raw = re.sub(r"^[/／]\s*", "", raw)
        parts = raw.split()
        if parts and parts[0].lower() in ("amo", "陪伴", "amo_forever", "astrbot_amo_forever"):
            parts = parts[1:]
        return parts

    def _resolve_target(self, event, args, index):
        if Comp is not None:
            for comp in event.get_messages():
                if isinstance(comp, Comp.At):
                    target = str(getattr(comp, "qq", ""))
                    if target and target != "all" and target != str(event.get_self_id()):
                        return target
        if index < len(args):
            token = str(args[index]).strip().lstrip("@")
            if token in ("我", "me", "self"):
                return str(event.get_sender_id())
            if token:
                return token
        return str(event.get_sender_id())

    async def _status_data(self):
        self._reload_config_if_changed()
        umo = self._last_umo or self._first_private_umo()
        if not self.state.weather:
            self.state.weather = self.state._simulate_weather()
        if self.state.weather.get("city") != self.cfg_str("weather_city", "杭州"):
            await self.state.refresh_weather(force=True)
        else:
            self._spawn(self.state.refresh_weather())
        if not self.state.worldview:
            self.state.worldview = self.state._fallback_world()
            self._spawn(self.state.ensure_worldview(umo))
        if (
            not self.state.schedule.get(today_str())
            or self.db.kv_get("schedule_version", "") != SCHEDULE_VERSION
        ):
            await self.state.ensure_schedule(umo)
        snap = self.state.snapshot()
        activity = 0.0
        threshold = {"value": 0.0, "base": 0.0, "absolute": 0.0}
        if self.heartflow is not None:
            try:
                hf_threshold, hf_activity, hf_absolute = self.heartflow._get_dynamic_threshold(umo)
                threshold = {
                    "value": round(float(hf_threshold) * 100, 1),
                    "base": round(float(self.heartflow.reply_threshold) * 100, 1),
                    "absolute": round(float(hf_absolute), 1),
                }
                activity = float(hf_activity) * 100
            except Exception as exc:
                logger.debug("[amo] 心流阈值读取失败: %s" % exc)
        counts = self.db.counts()
        return {
            "time": snap["datetime_text"],
            "day": day_meta(),
            "mood": snap["mood"],
            "dominant": snap["dominant"],
            "mood_score": round(snap["mood_score"], 1),
            "period": snap["period"],
            "health": snap["health"],
            "weather": snap["weather"],
            "weather_text": snap["weather_text"],
            "activity": snap["activity"],
            "schedule": snap["schedule"],
            "schedule_tree": self.state.schedule_tree(),
            "worldview": self.state.worldview,
            "threshold": threshold,
            "activity_rate": round(activity, 2),
            "counts": counts,
            "config": {
                "enable_group_reply": self.cfg_bool("enable_group_reply", True),
                "enable_private_reply": self.cfg_bool("enable_private_reply", True),
                "auto_active_msg": self.cfg_bool("auto_active_msg", True),
                "enable_polish": self.cfg_bool("enable_polish", True),
                "heartflow": self.heartflow is not None,
                "segment_engine": self.segment_engine is not None,
                "weather_key_set": bool(self.cfg_str("hefeng_key", "")),
                "weather_host": self.cfg_str("weather_host", "https://devapi.qweather.com"),
                "version": PLUGIN_VERSION,
                "memory_source": self.cfg_str("memory_source", "auto"),
                "companion_memory_available": self._companion_plugin() is not None,
            },
        }

    def _format_status(self, data):
        mood = data["mood"]
        mood_line = " ".join([key + str(int(value)) for key, value in mood.items()])
        threshold = data["threshold"]
        return "\n".join([
            "🌙 陪伴 · 当前状态",
            "🕒 " + str(data["time"]),
            "💛 心情：" + str(data["dominant"]) + "（" + mood_line + "）",
            "🩸 生理期：" + str(data["period"]["phase"]) + " 第" + str(data["period"]["day"]) + "天（" + str(data["period"]["tone"]) + "）",
            "🩺 身体：" + str(data["health"]["status"]),
            "🌦 天气：" + str(data["weather_text"]),
            "📅 正在：" + str(data["activity"].get("activity", "休息")) + "（" + str(data["activity"].get("place", "")) + "）",
            "🎚 心流阈值：" + str(threshold["value"]) + "（基础 " + str(threshold["base"]) + "，活跃度 " + str(data["activity_rate"]) + "%）",
            "📚 档案 " + str(data["counts"]["profiles"]) + " · 记忆 " + str(data["counts"]["memories"]) + " · 消息 " + str(data["counts"]["messages"]),
        ])

    async def _handle_command(self, event):
        args = self._args(event)
        sub = args[0].lower() if args else "help"
        uid = str(event.get_sender_id())

        if sub in ("help", "帮助", ""):
            return (
                "🌙 陪伴 指令\n"
                "/amo status 状态｜/amo mood 九维心情\n"
                "/amo profile [@人] 档案｜/amo memories [@人] 记忆\n"
                "/amo period 生理期｜/amo health 健康｜/amo schedule 日程\n"
                "/amo weather 天气｜/amo worldview 世界观｜/amo threshold 阈值\n"
                "管理员：/amo rel @人 关系｜/amo set @人 字段 值｜/amo memo @人 内容 [0/1/2]\n"
                "/amo forget 记忆ID｜/amo period set YYYY-MM-DD｜/amo health set 状态\n"
                "/amo schedule regen｜/amo worldview regen｜/amo say 内容｜/amo clean"
            )

        if sub in ("segment", "分段"):
            text = " ".join(args[1:]).strip()
            delay_type = self.cfg_str("seg_delay_type", "smart")
            if not text:
                return (
                    "分段测试：/amo segment 一段文字\n"
                    "使用完整本地分段引擎：按 seg_split_symbols 的符号列表断句\n"
                    "保留标点：" + ("是" if self.cfg_bool("seg_keep_symbol", True) else "否") +
                    "｜成对符号保护：" + ("开" if self.cfg_bool("seg_protect_paired_symbols", True) else "关") +
                    "｜延迟：" + delay_type +
                    "\n配置项：seg_split_symbols / seg_min_length / seg_max_length / seg_delay_type"
                )
            segments = self._segment(text)
            lines = ["分段结果（" + delay_type + "），共 " + str(len(segments)) + " 段"]
            for index, segment in enumerate(segments, 1):
                lines.append(str(index) + ". " + segment)
            if not segments:
                lines.append("（没有可发送的片段）")
            return "\n".join(lines)

        if sub == "status" or sub == "状态":
            return self._format_status(await self._status_data())

        if sub == "mood" or sub == "心情":
            snap = self.state.snapshot()
            lines = ["🎨 陪伴的十维心情"]
            for key, value in snap["mood"].items():
                bar = "█" * int(round(value / 10)) + "░" * (10 - int(round(value / 10)))
                lines.append("%s %s %d" % (key, bar, int(value)))
            lines.append("整体偏「%s」，语气：%s" % (
                snap["dominant"], self.state.tone_text(snap, "普通")
            ))
            return "\n".join(lines)

        if sub == "profile" or sub == "档案":
            target = self._resolve_target(event, args, 1)
            profile = self.db.get_profile(target)
            if not profile:
                return "还没有这个人的档案。多聊几句就会自动建立。"
            return "\n".join([
                "📁 档案 · " + (profile.get("name") or profile.get("uid")),
                "ID：" + str(profile.get("uid")),
                "称呼：" + str(profile.get("alias") or "未设置"),
                "生日：" + str(profile.get("birthday") or "未知"),
                "关系：" + str(profile.get("relation") or "普通"),
                "好感：" + str(profile.get("affection") or 0),
                "消息数：" + str(profile.get("msg_count") or 0),
                "记忆数：" + str(self.db.count_memories(target)),
                "备注：" + str(profile.get("notes") or "无"),
            ])

        if sub == "memories" or sub == "记忆":
            target = self._resolve_target(event, args, 1)
            if target != uid and not self._is_admin(event):
                return "只有管理员才能查看别人的记忆。"
            items = self.db.list_memories(target, 20)
            if not items:
                return "暂时没有记忆。"
            lines = ["📖 记忆 · " + target]
            for item in items:
                tier = to_int(item.get("tier"))
                label = "珍贵" if tier >= 2 else ("重要" if tier == 1 else "普通")
                expires = item.get("expires_at")
                if not expires:
                    left = "永久"
                else:
                    left = "%d天" % max(0, int((to_float(expires) - now_ts()) / 86400))
                lines.append("#%s [%s|%s] %s" % (item["id"], label, left, item["content"]))
            return "\n".join(lines)

        if sub in ("rel", "关系"):
            if not self._is_admin(event):
                return "只有管理员才能调整关系。"
            if len(args) < 3:
                return "用法：/amo rel @人 仇恨|抵触|普通|熟识|相恋"
            target = self._resolve_target(event, args, 1)
            relation = args[2]
            if relation not in RELATIONS:
                return "关系只能是：" + "、".join(RELATIONS)
            self.db.update_profile(target, relation=relation)
            if relation == "相恋":
                self._register_lover(target)
            self.db.add_memory(
                target, "与角色的关系是" + relation, "relation", 2,
                self.cfg_int("mem_days_normal", 7),
                self.cfg_int("mem_days_important", 14),
            )
            return "✅ 已将 " + target + " 的关系设为「" + relation + "」"

        if sub == "set" or sub == "设置":
            if not self._is_admin(event):
                return "只有管理员才能修改档案。"
            if len(args) < 4:
                return "用法：/amo set @人 name|alias|birthday|notes|affection 值"
            target = self._resolve_target(event, args, 1)
            field = args[2]
            value = " ".join(args[3:])
            if field == "relation":
                return "请用 /amo rel 设置关系。"
            if field == "birthday":
                match = re.match(r"^(\d{4}-)?(\d{1,2})-(\d{1,2})$", value)
                if not match:
                    return "生日格式：MM-DD 或 YYYY-MM-DD"
                value = "%02d-%02d" % (to_int(match.group(2)), to_int(match.group(3)))
            if field == "affection":
                value = int(clamp(to_int(value), 0, 100))
            if field not in ("name", "alias", "birthday", "notes", "affection"):
                return "可修改字段：name、alias、birthday、notes、affection"
            self.db.update_profile(target, **{field: value})
            return "✅ 已更新 " + target + " 的 " + field

        if sub == "memo" or sub == "记住":
            if not self._is_admin(event):
                return "只有管理员才能手动写入记忆。"
            if len(args) < 3:
                return "用法：/amo memo @人 内容 [0普通/1重要/2珍贵]"
            target = self._resolve_target(event, args, 1)
            content_parts = args[2:]
            tier = 1
            if content_parts and content_parts[-1] in ("0", "1", "2"):
                tier = to_int(content_parts[-1])
                content_parts = content_parts[:-1]
            content = " ".join(content_parts).strip()
            if not content:
                return "内容不能为空。"
            self.db.add_memory(
                target, content, "manual", tier,
                self.cfg_int("mem_days_normal", 7),
                self.cfg_int("mem_days_important", 14),
            )
            return "✅ 已记住：" + content

        if sub == "forget" or sub == "忘记":
            if not self._is_admin(event):
                return "只有管理员才能删除记忆。"
            if len(args) < 2:
                return "用法：/amo forget 记忆ID"
            self.db.delete_memory(args[1])
            return "✅ 已删除记忆 #" + str(args[1])

        if sub == "period" or sub == "生理期":
            if len(args) >= 3 and args[1].lower() == "set":
                if not self._is_admin(event):
                    return "只有管理员才能调整生理期。"
                if self.state.set_period_start(args[2]):
                    return "✅ 生理期起始日已设为 " + args[2]
                return "日期格式应为 YYYY-MM-DD"
            period = self.state.period_info()
            return (
                "🩸 生理期\n阶段：" + period["phase"] + " 第" + str(period["day"]) + "天\n"
                "状态：" + period["tone"] + "\n"
                "疼痛：" + str(period["pain"]) + "/10\n"
                "周期：" + str(period.get("cycle_days", 28)) + "天｜经期：" + str(period.get("bleed_days", 5)) + "天\n"
                "距离下次：" + str(period["days_to_next"]) + "天（预计 " + str(period.get("next_start", "")) + "）\n"
                "起始日：" + self.state.period_start + "（/amo period set YYYY-MM-DD，或网页配置 period_start）"
            )

        if sub == "health" or sub == "健康":
            if len(args) >= 3 and args[1].lower() == "set":
                if not self._is_admin(event):
                    return "只有管理员才能调整健康状态。"
                status = args[2]
                if status not in ("健康", "轻微不适", "感冒", "低烧", "疲惫"):
                    return "状态：健康 / 轻微不适 / 感冒 / 低烧 / 疲惫"
                self.state.set_health(status, 24, "管理员设置")
                return "✅ 健康状态已设为 " + status
            health = self.state.health_info()
            return (
                "🩺 身体状态：" + health["status"] + "\n"
                + ("备注：" + health["note"] + "\n" if health.get("note") else "")
                + "恢复时间：" + (
                    datetime.fromtimestamp(health["until"]).strftime("%m-%d %H:%M")
                    if health.get("until") else "—"
                )
            )

        if sub == "schedule" or sub == "日程":
            if len(args) >= 2 and args[1].lower() == "regen":
                if not self._is_admin(event):
                    return "只有管理员才能重生成日程。"
                items = await self.state.ensure_schedule(self._last_umo, force=True)
                return "✅ 日程已重新生成，共 " + str(len(items)) + " 条。"
            items = self.state.schedule.get(today_str()) or []
            if not items:
                items = await self.state.ensure_schedule(self._last_umo)
            activity = self.state.current_activity()
            lines = ["📅 今日日程"]
            for item in items:
                lines.append("%s-%s %s（%s）" % (
                    item.get("start", ""), item.get("end", ""),
                    item.get("activity", ""), item.get("place", ""),
                ))
            lines.append("现在应该在：" + str(activity.get("activity", "")))
            return "\n".join(lines)

        if sub == "weather" or sub == "天气":
            if len(args) >= 2 and args[1].lower() in ("refresh", "刷新"):
                await self.state.refresh_weather(force=True)
            weather = await self.state.refresh_weather()
            return (
                "🌦 " + str(weather.get("city", "")) + " " + str(weather.get("text", ""))
                + " " + str(weather.get("temp", "")) + "℃\n"
                + "湿度：" + str(weather.get("humidity", "")) + "%\n"
                + "风：" + str(weather.get("wind", "")) + "\n"
                + "来源：" + ("和风天气" if weather.get("source") == "qweather" else "本地模拟")
            )

        if sub == "worldview" or sub == "世界观":
            if len(args) >= 2 and args[1].lower() == "regen":
                if not self._is_admin(event):
                    return "只有管理员才能重生成世界观。"
                await self.state.ensure_worldview(self._last_umo, force=True)
                return "✅ 世界观已重新生成。"
            await self.state.ensure_worldview(self._last_umo)
            return "🌍 世界观\n" + self.state.worldview_text()

        if sub == "threshold" or sub == "阈值":
            data = await self._status_data()
            threshold = data["threshold"]
            return (
                "🎚 心流回复阈值\n"
                "当前动态阈值：" + str(round(threshold["value"] / 100, 3)) + "\n"
                "基础阈值：" + str(round(threshold["base"] / 100, 3)) + "\n"
                "绝对分数阈值：" + str(threshold["absolute"]) + "/10\n"
                "当前群活跃度：" + str(data["activity_rate"]) + "%\n"
                "说明：阈值越高越不想说话；详细状态用 /heartflow。"
            )

        if sub == "say" or sub == "说":
            if not self._is_admin(event):
                return "只有管理员才能测试发言。"
            content = " ".join(args[1:]).strip()
            if not content:
                return "用法：/amo say 内容"
            await event.send(MessageChain([Comp.Plain(content)]))
            return ""

        if sub == "clean" or sub == "清理":
            if not self._is_admin(event):
                return "只有管理员才能清理。"
            self.db.purge_memories()
            self.db.purge_messages(self.cfg_int("chat_log_days", 14))
            return "✅ 已清理过期记忆与过期聊天记录。"

        return "未知指令。发送 /amo help 查看帮助。"

    # ---------- 心流完整版指令 ----------
    @filter.command("heartflow")
    async def cmd_heartflow(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_status(event):
            yield item

    @filter.command("heartflow_debug")
    async def cmd_heartflow_debug(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_debug(event):
            yield item

    @filter.command("heartflow_clear")
    async def cmd_heartflow_clear(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_clear_buffer(event):
            yield item

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("heartflow_log")
    async def cmd_heartflow_log(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_toggle_log(event):
            yield item

    @filter.permission_type(filter.PermissionType.ADMIN)
    @filter.command("heartflow_reset")
    async def cmd_heartflow_reset(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_reset(event):
            yield item

    @filter.command("heartflow_help")
    async def cmd_heartflow_help(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if self.heartflow is None:
            yield event.plain_result("心流引擎未加载")
            return
        async for item in self.heartflow.heartflow_help(event):
            yield item

    @filter.command("amo")
    async def cmd_amo(self, event: AstrMessageEvent):
        await self._ensure_ready()
        try:
            message = await self._handle_command(event)
        except Exception as exc:
            logger.error("[amo] 指令异常: %s" % exc)
            message = "处理失败：" + str(exc)
        if message:
            yield event.plain_result(message)

    @filter.command("c_status")
    async def cmd_status(self, event: AstrMessageEvent):
        await self._ensure_ready()
        yield event.plain_result(self._format_status(await self._status_data()))

    @filter.command("c_profile")
    async def cmd_profile(self, event: AstrMessageEvent):
        await self._ensure_ready()
        uid = str(event.get_sender_id())
        profile = self.db.get_profile(uid)
        if not profile:
            yield event.plain_result("还没有你的档案。")
            return
        yield event.plain_result(
            "🤍 关系：" + str(profile.get("relation", "普通"))
            + "\n📖 记忆条数：" + str(self.db.count_memories(uid))
        )

    @filter.command("c_setrel")
    async def cmd_setrel(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if not self._is_admin(event):
            yield event.plain_result("只有管理员才能调整关系。")
            return
        parts = [item for item in (event.message_str or "").replace("/", " ").split() if item]
        relation = parts[-1] if parts else ""
        if relation not in RELATIONS:
            yield event.plain_result("用法：/c_setrel 仇恨|抵触|普通|熟识|相恋")
            return
        uid = str(event.get_sender_id())
        self.db.update_profile(uid, relation=relation)
        yield event.plain_result("✅ 关系已设置为：" + relation)

    @filter.command("learn_and_gate")
    async def cmd_learn(self, event: AstrMessageEvent):
        await self._ensure_ready()
        if not self.cfg_bool("enable_memory", True):
            yield event.plain_result("❌ 记忆功能已在配置中关闭")
            return
        text = (event.message_str or "").replace("/learn_and_gate", "").strip()
        if not text:
            yield event.plain_result("请输入要学习的内容")
            return
        uid = str(event.get_sender_id())
        self.db.add_memory(
            uid, text, "manual", 1,
            self.cfg_int("mem_days_normal", 7),
            self.cfg_int("mem_days_important", 14),
        )
        yield event.plain_result("✅ 已经记下来啦。")

    # ---------- Web 面板 ----------
    def _register_web_apis(self):
        prefixes = uniq([
            getattr(self, "name", None),
            PLUGIN_NAME,
            os.path.basename(self.plugin_dir),
            "astrbot_plugin_Astrbot_Amo_forever",
            "astrbot_plugin_amo_forever",
        ])
        # 清除上一实例/旧版本残留的 Web API 路由。
        # AstrBot 重载插件时不会自动清理 registered_web_apis，旧路由会继续
        # 指向已经 terminate 的旧实例，表现为 "Cannot operate on a closed database"。
        try:
            own_prefixes = tuple(
                "/" + str(prefix).strip("/") + "/"
                for prefix in prefixes
                if str(prefix).strip("/")
            )
            holders = (type(self.context), self.context)
            seen_holders = set()
            for holder in holders:
                if id(holder) in seen_holders:
                    continue
                seen_holders.add(id(holder))
                registry = getattr(holder, "registered_web_apis", None)
                if not isinstance(registry, list):
                    continue
                registry[:] = [
                    item
                    for item in registry
                    if not (
                        isinstance(item, tuple)
                        and item
                        and (
                            str(item[0]).startswith(own_prefixes)
                            or str(item[0]) in ("get_status", "get_profile", "refresh_status")
                        )
                    )
                ]
        except Exception as exc:
            logger.debug("[amo] 清理旧 Web API 路由失败: %s" % exc)
        routes = [
            ("/status", self.api_status, ["GET"]),
            ("/get_status", self.api_get_status, ["GET"]),
            ("/profiles", self.api_profiles, ["GET", "POST"]),
            ("/get_profile", self.api_get_profile, ["GET", "POST"]),
            ("/profiles/sync", self.api_profiles_sync, ["GET", "POST"]),
            ("/relations", self.api_relations, ["GET", "POST"]),
            ("/relation/save", self.api_relation_save, ["GET", "POST"]),
            ("/relation_save", self.api_relation_save, ["GET", "POST"]),
            ("/relation/delete", self.api_relation_delete, ["GET", "POST"]),
            ("/relation_delete", self.api_relation_delete, ["GET", "POST"]),
            ("/memory/candidates", self.api_memory_candidates, ["GET"]),
            ("/memory_candidates", self.api_memory_candidates, ["GET"]),
            ("/profiles_sync", self.api_profiles_sync, ["GET", "POST"]),
            ("/config", self.api_config, ["GET"]),
            ("/config/save", self.api_config_save, ["GET", "POST"]),
            ("/config_save", self.api_config_save, ["GET", "POST"]),
            ("/profile/save", self.api_profile_save, ["GET", "POST"]),
            ("/profile_save", self.api_profile_save, ["GET", "POST"]),
            ("/memories", self.api_memories, ["GET", "POST"]),
            ("/chat/history", self.api_chat_history, ["GET", "POST"]),
            ("/chat_history", self.api_chat_history, ["GET", "POST"]),
            ("/memory/add", self.api_memory_add, ["GET", "POST"]),
            ("/memory_add", self.api_memory_add, ["GET", "POST"]),
            ("/memory/delete", self.api_memory_delete, ["GET", "POST"]),
            ("/memory_delete", self.api_memory_delete, ["GET", "POST"]),
            ("/schedule", self.api_schedule, ["GET", "POST"]),
            ("/mood/update", self.api_mood_update, ["GET", "POST"]),
            ("/mood_update", self.api_mood_update, ["GET", "POST"]),
            ("/schedule/regen", self.api_schedule_regen, ["GET", "POST"]),
            ("/kb/regen", self.api_kb_regen, ["GET", "POST"]),
            ("/scenic_kb/regen", self.api_scenic_kb_regen, ["GET", "POST"]),
            ("/scenic_kb_regen", self.api_scenic_kb_regen, ["GET", "POST"]),
            ("/kb_regen", self.api_kb_regen, ["GET", "POST"]),
            ("/schedule_regen", self.api_schedule_regen, ["GET", "POST"]),
            ("/weather", self.api_weather, ["GET"]),
            ("/worldview", self.api_worldview, ["GET"]),
            ("/worldview/regen", self.api_worldview_regen, ["GET", "POST"]),
            ("/worldview_regen", self.api_worldview_regen, ["GET", "POST"]),
            ("/say", self.api_say, ["GET", "POST"]),
            ("/refresh_status", self.api_refresh_status, ["GET"]),
        ]
        for prefix in prefixes:
            clean = str(prefix).strip("/")
            if not clean:
                continue
            for path, handler, methods in routes:
                self._safe_register("/" + clean + path, handler, methods, path)
        # 不注册无前缀的旧路由，避免和其他插件或 AstrBot 自带路由冲突。

    def _safe_register(self, route, handler, methods, desc):
        try:
            self.context.register_web_api(route, handler, methods, desc)
            return True
        except TypeError:
            pass
        except Exception as exc:
            logger.debug("[amo] Web API 注册失败 %s: %s" % (route, exc))
            return False
        try:
            self.context.register_web_api(route, methods, desc, handler)
            return True
        except Exception as exc:
            logger.debug("[amo] Web API 兼容注册失败 %s: %s" % (route, exc))
            return False

    def _q(self, key, default=None):
        try:
            if web_request is not None:
                return web_request.query.get(key, default)
        except Exception:
            pass
        return default

    def _q_int(self, key, default=0):
        return to_int(self._q(key, default), default)

    async def _body(self):
        try:
            if web_request is not None and hasattr(web_request, "json"):
                data = await web_request.json(default={})
                return data if isinstance(data, dict) else {}
        except Exception:
            pass
        try:
            if web_request is not None:
                data = await web_request.get_json(silent=True)
                return data or {}
        except Exception:
            pass
        return {}

    @staticmethod
    def _coerce_config_value(kind, value):
        if kind == "bool":
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in ("1", "true", "yes", "on", "是")
        if kind == "int":
            return int(float(value))
        if kind == "float":
            return float(value)
        if kind in ("list", "template_list"):
            if isinstance(value, list):
                return value
            parsed = json.loads(value) if isinstance(value, str) and value.strip() else []
            return parsed if isinstance(parsed, list) else []
        if kind in ("dict", "object"):
            if isinstance(value, dict):
                return value
            parsed = json.loads(value) if isinstance(value, str) and value.strip() else {}
            return parsed if isinstance(parsed, dict) else {}
        return str(value)

    def _schema_map(self):
        path = os.path.join(self.plugin_dir, "_conf_schema.json")
        try:
            with open(path, encoding="utf-8") as stream:
                schema = json.load(stream)
            return schema if isinstance(schema, dict) else {}
        except Exception as exc:
            logger.warning("[amo] 读取配置 schema 失败: %s" % exc)
            return {}

    def _config_schema_items(self):
        schema = self._schema_map()
        items = []
        for key, meta in schema.items():
            if not isinstance(meta, dict):
                continue
            if key.startswith("hf_"):
                group = "心流"
            elif key.startswith("seg_"):
                group = "分段"
            elif key.startswith("companion_") or key.startswith("memory_") or key in ("admin_uids",):
                group = "记忆"
            elif key.startswith("proactive_") or key.startswith("delay_") or key.startswith("disturb_") or key in ("quiet_hours", "auto_active_msg"):
                group = "私聊"
            elif key.startswith("period_") or key.startswith("enable_period") or key.startswith("enable_sick"):
                group = "状态"
            else:
                group = "基础"
            items.append({
                "key": key,
                "type": meta.get("type", "string"),
                "description": meta.get("description") or key,
                "hint": meta.get("hint", ""),
                "default": meta.get("default"),
                "options": meta.get("options") or [],
                "group": group,
                "value": self.cfg(key, meta.get("default")),
            })
        return items

    async def _apply_runtime_config(self):
        self.bot_name = self.cfg_str("bot_name", self.bot_name) or "陪伴"
        self._persona_name_cache.clear()
        self.bot_aliases = [
            item.strip() for item in self.cfg_str("bot_aliases", "").split(",") if item.strip()
        ]
        self.admin_uids = {
            item.strip() for item in self.cfg_str("admin_uids", "").split(",") if item.strip()
        }
        if self.state is not None:
            start = self.cfg_str("period_start", "").strip()
            if start and start != self.state.period_start:
                try:
                    date.fromisoformat(start)
                    self.state.set_period_start(start)
                except Exception:
                    pass
            try:
                await self.state.refresh_weather(force=True)
            except Exception:
                pass
        if HeartflowEngine is not None:
            old = self.heartflow
            if old is not None:
                try:
                    await old.terminate()
                except Exception:
                    pass
            try:
                hf_config = self._hf_config()
                hf_config.setdefault("enable_heartflow", True)
                hf_config.setdefault("enable_dynamic_threshold", True)
                hf_config.setdefault("judge_provider_name", "")
                self.heartflow = HeartflowEngine(self.context, hf_config)
                self.heartflow.set_identity(self.bot_name, self.bot_aliases)
            except Exception as exc:
                logger.error("[amo] 应用心流配置失败: %s" % exc)
        if SegmentEngine is not None:
            old = self.segment_engine
            if old is not None:
                for task in list(getattr(old, "_tasks", set())):
                    try:
                        task.cancel()
                    except Exception:
                        pass
            try:
                seg_config = self._seg_config()
                seg_config.setdefault("protect_paired_symbols", True)
                self.segment_engine = SegmentEngine(self.context, seg_config, plugin=self)
            except Exception as exc:
                logger.error("[amo] 应用分段配置失败: %s" % exc)

    async def api_config(self):
        await self._ensure_ready()
        return {"code": 0, "data": {"items": self._config_schema_items()}}

    async def api_config_save(self):
        await self._ensure_ready()
        data = await self._body()
        changes = data.get("changes") if isinstance(data.get("changes"), dict) else data
        schema = self._schema_map()
        saved = {}
        for key, value in (changes or {}).items():
            meta = schema.get(key)
            if not isinstance(meta, dict):
                continue
            try:
                coerced = self._coerce_config_value(meta.get("type", "string"), value)
            except Exception as exc:
                logger.warning("[amo] 配置 %s 值无效: %s" % (key, exc))
                continue
            self.config[key] = coerced
            saved[key] = coerced
        if saved:
            try:
                if hasattr(self.config, "save_config"):
                    self.config.save_config()
            except Exception as exc:
                logger.error("[amo] 保存插件配置失败: %s" % exc)
                return {"code": 1, "msg": "保存配置失败：" + str(exc)}
            try:
                await self._apply_runtime_config()
            except Exception as exc:
                logger.error("[amo] 应用配置失败: %s" % exc)
        return {"code": 0, "data": {"saved": saved}}

    async def api_profiles_sync(self):
        # 4.3.2 起用户画像只来自本插件聊天/手动建档；
        # 不再把记忆插件的用户导入画像，记忆由 LLM hook 读取。
        return {
            "code": 0,
            "data": {"synced": 0, "profiles": self.db.list_profiles(limit=500)},
            "msg": "原版模式：画像只从聊天建立，不再从记忆插件同步用户",
        }

    async def api_memory_candidates(self):
        await self._ensure_ready()
        selected = self.cfg_str("companion_memory_plugin_name", "").strip()
        meta = self._companion_plugin_meta()
        return {
            "code": 0,
            "data": {
                "items": self._companion_candidates(),
                "selected": selected,
                "detected": str(getattr(meta, "name", "") or "") if meta is not None else "",
            },
        }

    async def api_relations(self):
        await self._ensure_ready()
        profiles = self.db.list_profiles(limit=500)
        names = {str(item.get("uid")): (item.get("alias") or item.get("name") or item.get("uid")) for item in profiles}
        edges = []
        for edge in self.db.list_relations():
            row = dict(edge)
            row["a_name"] = names.get(str(row.get("a_uid")), row.get("a_uid"))
            row["b_name"] = names.get(str(row.get("b_uid")), row.get("b_uid"))
            edges.append(row)
        return {"code": 0, "data": {"edges": edges, "profiles": profiles, "relations": list(NETWORK_RELATIONS)}}

    async def api_relation_save(self):
        await self._ensure_ready()
        data = await self._body()
        a_uid = str(data.get("a_uid") or "").strip()
        b_uid = str(data.get("b_uid") or "").strip()
        relation = str(data.get("relation") or "朋友").strip()
        note = str(data.get("note") or "").strip()
        if not a_uid or not b_uid or a_uid == b_uid:
            return {"code": 1, "msg": "请选择两个不同的用户"}
        if relation not in NETWORK_RELATIONS:
            return {"code": 1, "msg": "关系类型无效"}
        self.db.upsert_relation(a_uid, b_uid, relation, note)
        logger.debug("[amo] 关系网更新: %s <-> %s = %s" % (a_uid, b_uid, relation))
        return await self.api_relations()

    async def api_relation_delete(self):
        await self._ensure_ready()
        data = await self._body()
        a_uid = str(data.get("a_uid") or "").strip()
        b_uid = str(data.get("b_uid") or "").strip()
        if not a_uid or not b_uid:
            return {"code": 1, "msg": "缺少用户"}
        self.db.delete_relation(a_uid, b_uid)
        return await self.api_relations()

    async def api_dispatch(self, action: str = ""):
        await self._ensure_ready()
        name = (action or "").replace("/", "_").strip("_").lower()
        try:
            if name in ("", "index", "status", "get_status"):
                return await self.api_get_status()
            if name in ("profiles", "profile_list"):
                return await self.api_profiles()
            if name in ("profile_save", "save_profile"):
                return await self.api_profile_save()
            if name in ("memories", "memory_list"):
                return await self.api_memories()
            if name in ("memory_add", "add_memory"):
                return await self.api_memory_add()
            if name in ("memory_delete", "delete_memory"):
                return await self.api_memory_delete()
            if name in ("mood_update", "update_mood"):
                return await self.api_mood_update()
            if name == "schedule":
                return await self.api_schedule()
            if name in ("scenic_kb_regen", "regen_scenic_kb"):
                return await self.api_scenic_kb_regen()
            if name in ("kb_regen", "regen_kb", "dialect_kb_regen"):
                return await self.api_kb_regen()
            if name in ("schedule_regen", "regen_schedule"):
                return await self.api_schedule_regen()
            if name in ("weather", "weather_refresh", "refresh_weather"):
                return await self.api_weather()
            if name == "worldview":
                return await self.api_worldview()
            if name in ("worldview_regen", "regen_worldview"):
                return await self.api_worldview_regen()
            if name in ("say", "send"):
                return await self.api_say()
            if name in ("refresh_status", "refresh"):
                return await self.api_refresh_status()
            if name in ("get_profile", "profile"):
                return await self.api_get_profile()
            return {"code": 1, "msg": "未知接口：" + name}
        except Exception as exc:
            logger.error("[amo] Web API %s 异常: %s" % (name, exc))
            return {"code": 1, "msg": str(exc)}

    async def api_status(self):
        await self._ensure_ready()
        data = await self._status_data()
        return {"code": 0, "data": data}

    async def api_get_status(self):
        await self._ensure_ready()
        data = await self._status_data()
        return {
            "code": 0,
            "data": {
                "mood": data["dominant"] + "（" + data["mood"].__str__() + "）",
                "schedule": data["activity"].get("activity", ""),
                "health": data["health"]["status"],
                "period": data["period"]["phase"] + " 第" + str(data["period"]["day"]) + "天",
                "weather": data["weather_text"],
                "switch_status": data["config"],
                "threshold": data["threshold"],
                "counts": data["counts"],
            },
        }

    async def api_get_profile(self):
        await self._ensure_ready()
        data = await self._body()
        uid = str(data.get("uid") or self._q("uid", "") or "")
        if uid:
            profile = self.db.get_profile(uid)
        else:
            profiles = self.db.list_profiles(limit=1)
            profile = profiles[0] if profiles else {}
        return {
            "code": 0,
            "data": {
                "relation": profile.get("relation", "普通"),
                "mem_count": self.db.count_memories(profile.get("uid", uid)),
                "profile": profile,
            },
        }

    async def api_refresh_status(self):
        await self._ensure_ready()
        await self.state.refresh_weather(force=True)
        return {"code": 0, "msg": "刷新成功"}

    async def api_profiles(self):
        await self._ensure_ready()
        data = await self._body()
        keyword = str(data.get("q") or self._q("q", "") or "")
        limit = to_int(data.get("limit") or self._q("limit", 100), 100)
        return {"code": 0, "data": self.db.list_profiles(keyword, limit)}

    async def api_profile_save(self):
        await self._ensure_ready()
        data = await self._body()
        uid = str(data.get("uid") or self._q("uid", "") or "").strip()
        if not uid:
            return {"code": 1, "msg": "uid 不能为空"}
        fields = {}
        for key in ("name", "alias", "birthday", "relation", "notes"):
            value = data.get(key, self._q(key, None))
            if value is not None:
                fields[key] = str(value)[:100]
        if "relation" in fields and fields["relation"] not in RELATIONS:
            return {"code": 1, "msg": "关系只能是：" + "、".join(RELATIONS)}
        if "birthday" in fields and fields["birthday"]:
            match = re.match(r"^(\d{4}-)?(\d{1,2})-(\d{1,2})$", fields["birthday"])
            if not match:
                return {"code": 1, "msg": "生日格式应为 MM-DD 或 YYYY-MM-DD"}
            fields["birthday"] = "%02d-%02d" % (to_int(match.group(2)), to_int(match.group(3)))
        affection = data.get("affection", self._q("affection", None))
        if affection is not None:
            fields["affection"] = int(clamp(to_int(affection, 10), 0, 100))
        if not self.db.get_profile(uid):
            self.db.touch_profile(uid, fields.get("name", ""), "web", "", "", True)
        self.db.update_profile(uid, **fields)
        if fields.get("relation") == "相恋":
            self._register_lover(uid)
        return {"code": 0, "data": self.db.get_profile(uid)}

    async def api_chat_history(self):
        await self._ensure_ready()
        data = await self._body()
        uid = str(data.get("uid") or self._q("uid", "") or "")
        if not uid:
            return {"code": 1, "msg": "uid 不能为空"}
        limit = to_int(data.get("limit") or self._q("limit", 200), 200)
        profile = self.db.get_profile(uid) or {}
        memories = self._external_profile_memories(
            uid, profile.get("name", ""), profile.get("alias", ""), limit
        )
        return {
            "code": 0,
            "data": {
                "chat": self.db.chat_history(uid, limit),
                "memories": memories,
            },
        }

    async def api_memories(self):
        await self._ensure_ready()
        data = await self._body()
        uid = str(data.get("uid") or self._q("uid", "") or "")
        if not uid:
            return {"code": 1, "msg": "uid 不能为空"}
        keyword = str(data.get("q") or self._q("q", "") or "")
        limit = self._q_int("limit", 50)
        if keyword:
            items = self.db.search_memories(
                uid, keyword, limit=limit,
                normal_days=self.cfg_int("mem_days_normal", 7),
                important_days=self.cfg_int("mem_days_important", 14),
            )
        else:
            items = self.db.list_memories(uid, limit)
        if self._companion_plugin() is not None:
            seen = {
                re.sub(r"\s+", "", str(item.get("content") or "")).lower()
                for item in items
            }
            for item in self._external_all_memories(uid, keyword, limit):
                key = re.sub(r"\s+", "", str(item.get("content") or "")).lower()
                if key and key not in seen:
                    seen.add(key)
                    items.append(item)
            items = items[:max(1, min(100, limit))]
        return {"code": 0, "data": items}

    async def api_memory_add(self):
        await self._ensure_ready()
        data = await self._body()
        uid = str(data.get("uid") or self._q("uid", "") or "").strip()
        content = str(data.get("content") or self._q("content", "") or "").strip()
        if not uid or not content:
            return {"code": 1, "msg": "uid 和 content 不能为空"}
        tier = to_int(data.get("tier", self._q("tier", 1)), 1)
        self.db.add_memory(
            uid, content, str(data.get("kind", "manual")), tier,
            self.cfg_int("mem_days_normal", 7),
            self.cfg_int("mem_days_important", 14),
        )
        return {"code": 0, "msg": "已写入记忆"}

    async def api_memory_delete(self):
        await self._ensure_ready()
        data = await self._body()
        memory_id = data.get("id", self._q("id", 0))
        self.db.delete_memory(memory_id)
        return {"code": 0, "msg": "已删除"}

    async def api_mood_update(self):
        await self._ensure_ready()
        data = await self._body()
        incoming = data.get("mood") if isinstance(data.get("mood"), dict) else data
        for key in MOOD_KEYS:
            if key in incoming:
                try:
                    self.state.mood[key] = clamp(float(incoming[key]), 0.0, 100.0)
                except Exception:
                    continue
        self.state.save()
        return {"code": 0, "data": self.state.snapshot()}

    async def api_schedule(self):
        await self._ensure_ready()
        data = await self._body()
        day = str(data.get("date") or self._q("date", "") or today_str())
        if day == today_str():
            items = await self.state.ensure_schedule(self._last_umo)
        else:
            items = self.state._cover_schedule(self.db.get_schedule(day) or [])
        return {"code": 0, "data": {"day": day, "meta": day_meta(day), "items": items, "tree": self.state.schedule_tree(), "current": self.state.current_activity()}}

    async def api_scenic_kb_regen(self):
        await self._ensure_ready()
        kb = await self._ensure_scenic_kb()
        if kb is None:
            return {
                "code": 1,
                "msg": "景区知识库创建失败：请检查 Embedding 供应商，并查看 AstrBot 日志",
            }
        return {"code": 0, "msg": "景区知识库已就绪：" + self._scenic_kb_name()}

    async def api_kb_regen(self):
        await self._ensure_ready()
        kb = await self._ensure_dialect_kb()
        if kb is None:
            return {
                "code": 1,
                "msg": "知识库创建失败：请检查是否配置了 Embedding 供应商，并查看 AstrBot 日志",
            }
        return {"code": 0, "msg": "知识库已就绪：" + self._dialect_kb_name()}

    async def api_schedule_regen(self):
        await self._ensure_ready()
        items = await self.state.ensure_schedule(self._last_umo, force=True)
        return {"code": 0, "data": items}

    async def api_weather(self):
        await self._ensure_ready()
        weather = await self.state.refresh_weather(force=True)
        return {"code": 0, "data": weather}

    async def api_worldview(self):
        await self._ensure_ready()
        await self.state.ensure_worldview(self._last_umo)
        return {"code": 0, "data": self.state.worldview}

    async def api_worldview_regen(self):
        await self._ensure_ready()
        worldview = await self.state.ensure_worldview(self._last_umo, force=True)
        return {"code": 0, "data": worldview}

    async def api_say(self):
        await self._ensure_ready()
        data = await self._body()
        text = str(data.get("text") or self._q("text", "") or "").strip()
        umo = str(data.get("umo") or self._q("umo", "") or self._last_umo)
        if not text:
            return {"code": 1, "msg": "text 不能为空"}
        ok = await self._send_to_umo(umo, text)
        return {"code": 0 if ok else 1, "msg": "已发送" if ok else "发送失败"}
