#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色设定板校验（L3 硬门）。

    python scripts/board_check.py --file "…/角色-林桂芳.txt" --variant A \
        --voice-card "…/音色-林桂芳.txt" --strict

查十项：
  1 七个必选字段齐全非空
  2 姓名 ≤4 字；年龄/身高/体重是数字格式
  3 A 版必须含模块2 六项；B 版整段不得出现「声线特征」
  4 模块1 恰好 5 条习惯；替换服装恰好 3 套；随身物品 1—2 件
  5 可选模块只能完整存在或整段不存在
  6 【必留·人物视觉规范】【风格可自由调整】逐字匹配
  7 无 <>/《》/待填/XX 占位
  8 正文 500—1200 字
  9 A 版基频与音色卡第 2 维逐字一致
  10 同一项目 style 一致（给 --style 时）

退出码：0 PASS（告警只呈现）｜2 BLOCK（结构错）｜1 仅 --strict 下告警也算失败
"""
from __future__ import annotations

import argparse
import os
import re
import sys

VISUAL = """【必留·人物视觉规范】（保证人物一致性，建议保留）
右侧人物展示区包含：
1. 全身站姿3视角：正面、侧面、背面，自然放松站姿，写实人体比例
2. 脸部特写组：正面脸部特写、75°侧脸特写，另加3-4张对应性格的表情特写
3. 局部细节组：皮肤质感、服装面料、关键服饰细节超特写"""

FIELDS = [("姓名", "name"), ("外号/小名", "alias"), ("年龄", "age"), ("身高", "height"),
          ("体重", "weight"), ("职业/身份", "occupation"), ("人物定位", "positioning")]

VOICE_FIELDS = ["声线定位", "基频区间", "虚实占比", "语速", "语调特点", "齿音强度"]


def field(text: str, label: str) -> str:
    m = re.search(r"^%s[:：]\s*(.*)$" % re.escape(label), text, re.M)
    return (m.group(1).strip() if m else "")


def section(text: str, start: str, end: str) -> str:
    i = text.find(start)
    if i < 0:
        return ""
    j = text.find(end, i + len(start))
    return text[i + len(start): j if j >= 0 else len(text)]


def main() -> int:
    ap = argparse.ArgumentParser(description="角色设定板校验")
    ap.add_argument("--file", required=True)
    ap.add_argument("--variant", choices=["A", "B"], required=True)
    ap.add_argument("--voice-card", default="")
    ap.add_argument("--style", default="", help="项目统一画风；给了就比对第一句")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.file):
        print("[BLOCK] 找不到文件：%s" % a.file)
        return 2
    text = open(a.file, encoding="utf-8").read()
    errs, warns = [], []

    # 1 七个字段
    for label, key in FIELDS:
        v = field(text, label)
        if not v:
            errs.append("必选字段为空：%s" % label)
    name = field(text, "姓名")
    if name and len(name) > 4:
        errs.append("姓名 %s 超过 4 字" % name)
    if not re.match(r"^[0-9]{1,3}岁$", field(text, "年龄")):
        errs.append("年龄必须是「58岁」这种格式")
    if not re.match(r"^[0-9]{2,3}cm$", field(text, "身高")):
        errs.append("身高必须是「161cm」这种格式")
    if not re.match(r"^[0-9]{2,3}kg$", field(text, "体重")):
        errs.append("体重必须是「56kg」这种格式")

    # 3 A/B 模块互斥
    has_voice = "声线特征" in text
    if a.variant == "A":
        if not has_voice:
            errs.append("A 版缺少「模块2：声线特征」")
        else:
            for f in VOICE_FIELDS:
                if not field(text, f):
                    errs.append("A 版声线模块缺项：%s" % f)
            hz = field(text, "基频区间")
            if hz and not re.match(r"^[0-9]{2,3}—[0-9]{2,3} ?Hz$", hz.split("，")[0].strip()):
                errs.append("基频区间格式应为「165—195 Hz」：%s" % hz)
    else:
        if has_voice:
            errs.append("B 版不允许出现「声线特征」（声线改由 wav 承载）")

    # 4/5 可选模块完整或不存在
    m1 = section(text, "▶ 模块1：性格与行为习惯", "▶ 模块")
    if "▶ 模块1" in text:
        habits = re.findall(r"^[1-5]\..+$", m1, re.M)
        if len(habits) != 5:
            errs.append("模块1 习惯动作必须恰好 5 条（现在 %d 条）" % len(habits))
        if not field(m1, "性格关键词"):
            errs.append("模块1 缺「性格关键词」")

    out_label = "▶ 模块3：替换服装" if a.variant == "A" else "▶ 模块2：替换服装"
    if out_label in text:
        blk = section(text, out_label, "▶ 模块")
        if "下方排列3套替换服装" not in blk:
            errs.append("替换服装模块缺固定说明「下方排列3套替换服装…」")
        note = blk.split("\n", 2)[-1].strip()
        if not note or note.startswith("▶") or note.startswith("【"):
            errs.append("替换服装模块没有写三套服装名称")

    prop_label = "▶ 模块4：随身物品特写" if a.variant == "A" else "▶ 模块3：随身物品特写"
    if prop_label in text:
        blk = section(text, prop_label, "▶ 模块")
        body = blk.split("\n", 2)[-1].strip()
        if not body or body.startswith("【"):
            errs.append("随身物品模块没有写物品名")

    # 6 固定段逐字
    if VISUAL not in text:
        errs.append("【必留·人物视觉规范】被改写或缺失")
    if "【风格可自由调整】" not in text:
        errs.append("缺【风格可自由调整】段")
    style_body = section(text, "【风格可自由调整】", "\n\n")
    if len(style_body.strip()) < 8:
        errs.append("【风格可自由调整】内容过短")

    # 7 占位
    for bad in ("<>", "《", "》", "待填", "XX", "{{"):
        if bad in text:
            errs.append("残留占位/模板痕迹：%s" % bad)

    # 8 长度
    if not (500 <= len(text) <= 1200):
        warns.append("正文 %d 字，建议 500—1200 字" % len(text))

    # 9 音色卡基频
    if a.variant == "A" and a.voice_card:
        if not os.path.isfile(a.voice_card):
            errs.append("音色卡不存在：%s" % a.voice_card)
        else:
            card = open(a.voice_card, encoding="utf-8").read()
            m = re.search(r"基频区间[:：]\s*([^\n，,]+)", card)
            card_hz = m.group(1).strip() if m else ""
            board_hz = field(text, "基频区间").split("，")[0].strip()
            if card_hz and board_hz != card_hz:
                errs.append("板上的基频「%s」≠ 音色卡「%s」" % (board_hz, card_hz))

    # 10 风格一致
    if a.style:
        m = re.search(r"制作一张(.+?)角色设定板", text)
        got = m.group(1).strip() if m else ""
        if got != a.style:
            errs.append("画风「%s」≠ 项目统一画风「%s」" % (got, a.style))

    for w in warns:
        print("[WARN] " + w)
    for e in errs:
        print("[BLOCK] " + e)
    if not errs:
        print("[PASS] %s 版｜%d 字%s" % (a.variant, len(text), "（有告警）" if warns else ""))
        return 1 if (a.strict and warns) else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
