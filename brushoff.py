# -*- coding: utf-8 -*-
"""赶人话术清理：她说「你先忙 / 不打扰你了」时，把它删掉。

用户在聊天，不是来请假的；除非用户自己说在忙，否则这类句子会让体验断掉。
纯函数，方便单测。
"""

from __future__ import annotations

import re

BRUSHOFF = (
    "你先忙", "你去忙", "先忙吧", "忙你的", "那你先忙", "你忙吧",
    "不打扰你", "不打扰了", "晚点聊", "改天聊", "有空再说", "忙完再说",
)

BUSY = ("我在忙", "我忙", "加班", "开会", "没空", "在上班", "赶时间", "在路上", "在写", "在赶")

FALLBACK = "我在呢，怎么啦？"


def user_is_busy(text):
    body = str(text or "")
    return any(word in body for word in BUSY)


def strip_brushoff(reply, user_text=""):
    """返回 (处理后的回复, 被删掉的那句)。用户自己说忙时不动。"""
    text = str(reply or "")
    if not text or user_is_busy(user_text):
        return text, ""
    sentences = re.split(r"(?<=[。！？!?~～\n])", text)
    kept, hit = [], ""
    for sentence in sentences:
        if any(word in sentence for word in BRUSHOFF):
            if not hit:
                hit = sentence.strip()
            continue
        kept.append(sentence)
    if not hit:
        return text, ""
    new = "".join(kept).strip()
    if not new:
        new = FALLBACK
    return new, hit
