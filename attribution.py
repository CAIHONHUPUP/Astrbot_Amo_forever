# -*- coding: utf-8 -*-
"""归属判定：他说的经历属于他，不能安到自己身上。

用户跟她说「我在外面吃了碗面」，她回「我也在外面吃了碗面」——这就是「幻视」。
这里只做两件事：

- ``first_person_experience(text)``：这句话是不是他在讲自己的经历；
- ``attribution_leak(user_text, reply)``：她的回复有没有把他的经历接成自己的。

纯函数、无依赖，方便单测。
"""

from __future__ import annotations

import re

# 第一人称 + 经历动词
_EXPERIENCE = re.compile(
    r"我(?:今天|刚才|刚|昨天|昨晚|上午|中午|下午|晚上|现在)?[^，。！？!?；;\n]{0,12}"
    r"(?:吃|喝|去|到|在|买|看|逛|玩|加班|上班|睡|住|点|回)"
)

# 「吃了碗面」→ 碗面 ；「在楼下那家面馆吃了」→ 楼下那家面馆
_FOOD = re.compile(r"(?:吃|喝)了?([\u4e00-\u9fff]{2,6})")
_PLACE = re.compile(r"在([\u4e00-\u9fff]{2,8}?)(?:吃|喝|逛|玩|待|上班|加班|睡)")

_STOPWORDS = {"什么", "这个", "那个", "一下", "一点", "的时", "时候", "东西", "地方"}


def first_person_experience(text):
    """他是不是在讲自己的经历（我吃了/我在哪/我刚去…）。"""
    body = str(text or "")
    if not body:
        return False
    return bool(_EXPERIENCE.search(body))


def _tokens(text):
    body = str(text or "")
    out = set()
    for pattern in (_FOOD, _PLACE):
        for match in pattern.finditer(body):
            token = match.group(1).strip()
            token = re.sub(r"^(个|了)", "", token)
            if len(token) >= 2 and token not in _STOPWORDS:
                out.add(token)
    return out


def attribution_leak(user_text, reply):
    """回复里是否出现了「我 + 他的食物/地点」，也就是把他的经历安到自己身上。"""
    tokens = _tokens(user_text)
    if not tokens:
        return False
    for sentence in re.split(r"[。！？!?；;\n]", str(reply or "")):
        if "我" not in sentence:
            continue
        for token in tokens:
            if token in sentence:
                return True
    return False


def leak_tokens(user_text, reply):
    """返回命中的那些词，方便打日志定位。"""
    tokens = _tokens(user_text)
    hit = []
    for sentence in re.split(r"[。！？!?；;\n]", str(reply or "")):
        if "我" not in sentence:
            continue
        for token in tokens:
            if token in sentence and token not in hit:
                hit.append(token)
    return hit
