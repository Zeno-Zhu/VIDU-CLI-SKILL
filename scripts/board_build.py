#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""角色设定板渲染（L1：数据 → 固定骨架）。

    python scripts/board_build.py --data "…/角色-林桂芳.json"
    python scripts/board_build.py --data "…/角色-林桂芳.json" --variant B --out "…/角色-林桂芳.txt"
    python scripts/board_build.py --data "…/角色-林桂芳.json" --dry-run

骨架来自 templates/character_board.{A,B}.txt，一字不改；只替换 {{槽位}}。
退出码：0 成功｜2 数据/模板不合法
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(ROOT, "templates")

DEFAULT_STYLE = ("整体为棚拍写实质感、真实皮肤纹理、自然布料褶皱、柔和均匀光影，"
                 "同一角色五官、发型、体型全程统一，无崩坏、无卡通化、无文字乱码。")

BLOCK = re.compile(r"\{\{#(\w+)\}\}(.*?)\{\{/\1\}\}", re.S)
VAR = re.compile(r"\{\{([\w.]+)\}\}")


def flatten(d: dict) -> dict:
    core = d.get("core") or {}
    opt = d.get("optional") or {}
    out = {
        "style": d.get("style", ""),
        "name": core.get("name", ""),
        "alias": core.get("alias", ""),
        "age": core.get("age", ""),
        "height": core.get("height", ""),
        "weight": core.get("weight", ""),
        "occupation": core.get("occupation", ""),
        "positioning": core.get("positioning", ""),
        "style_note": d.get("style_note") or DEFAULT_STYLE,
    }
    p = opt.get("personality")
    if p:
        out["personality"] = True
        out["p_keywords"] = p.get("keywords", "")
        for i, h in enumerate((p.get("habits") or [])[:5], 1):
            out["h%d" % i] = h
    v = opt.get("voice")
    if v:
        out["voice"] = True
        out["v_range"] = v.get("range", "")
        out["v_hz"] = v.get("hz", "")
        out["v_breath"] = v.get("breath", "")
        out["v_speed"] = v.get("speed", "")
        out["v_tone"] = v.get("tone", "")
        out["v_sibilance"] = v.get("sibilance", "")
    o = opt.get("outfits")
    if o:
        out["outfits"] = True
        items = [x for x in (o.get("items") or []) if x]
        note = (o.get("note") or "").strip()
        merged = "／".join(items)
        if note and note not in merged and merged not in note:
            merged = (merged + "；" + note).strip("；")
        elif note and not items:
            merged = note
        out["o_note"] = merged
    pr = opt.get("props")
    if pr:
        out["props"] = True
        out["pr_note"] = "、".join([x for x in (pr.get("items") or []) if x])
    return out


def render(tpl: str, data: dict) -> str:
    def block(m):
        key, body = m.group(1), m.group(2)
        return body if data.get(key) else ""
    prev = None
    text = tpl
    while prev != text:
        prev = text
        text = BLOCK.sub(block, text)
    text = VAR.sub(lambda m: str(data.get(m.group(1), "")), text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip() + "\n"
    return text


def validate(d: dict, variant: str) -> list:
    errs = []
    core = d.get("core") or {}
    for k, label in (("name", "姓名"), ("alias", "外号"), ("age", "年龄"), ("height", "身高"),
                     ("weight", "体重"), ("occupation", "职业/身份"), ("positioning", "人物定位")):
        if not str(core.get(k, "")).strip():
            errs.append("core.%s（%s）为空" % (k, label))
    name = str(core.get("name", ""))
    if len(name) > 4:
        errs.append("姓名 %s 超过 4 字（生图模型容易写错）" % name)
    if not re.match(r"^[0-9]{1,3}岁$", str(core.get("age", ""))):
        errs.append("age 必须是「58岁」这种格式")
    if not re.match(r"^[0-9]{2,3}cm$", str(core.get("height", ""))):
        errs.append("height 必须是「161cm」这种格式")
    if not re.match(r"^[0-9]{2,3}kg$", str(core.get("weight", ""))):
        errs.append("weight 必须是「56kg」这种格式")

    opt = d.get("optional") or {}
    p = opt.get("personality")
    if p is not None:
        habits = p.get("habits") or []
        if len(habits) != 5:
            errs.append("personality.habits 必须恰好 5 条（现在 %d 条）" % len(habits))
    o = opt.get("outfits")
    if o is not None and len(o.get("items") or []) != 3:
        errs.append("outfits.items 必须恰好 3 套")
    pr = opt.get("props")
    if pr is not None and not (1 <= len(pr.get("items") or []) <= 2):
        errs.append("props.items 必须 1—2 件")

    if variant == "A":
        v = opt.get("voice") or {}
        for k in ("range", "hz", "breath", "speed", "tone", "sibilance"):
            if not str(v.get(k, "")).strip():
                errs.append("A 版 voice.%s 为空（声线必须上板）" % k)
        if v.get("hz") and not re.match(r"^[0-9]{2,3}—[0-9]{2,3} ?Hz$", v["hz"]):
            errs.append("voice.hz 必须是「165—195 Hz」这种格式")
    elif variant == "B":
        if opt.get("voice"):
            errs.append("B 版不允许 optional.voice（声线不进板，改用 wav）")
    else:
        errs.append("variant 只能是 A 或 B")
    return errs


def main() -> int:
    ap = argparse.ArgumentParser(description="角色设定板：JSON → 固定骨架")
    ap.add_argument("--data", required=True, help="角色-<名>.json")
    ap.add_argument("--variant", choices=["A", "B"], default="", help="覆盖 JSON 里的 variant")
    ap.add_argument("--out", default="", help="输出 txt（默认与 data 同名 .txt）")
    ap.add_argument("--template-dir", default=TPL_DIR)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.data):
        print("[BLOCK] 找不到数据文件：%s" % a.data)
        return 2
    try:
        d = json.load(open(a.data, encoding="utf-8"))
    except Exception as e:
        print("[BLOCK] JSON 解析失败：%s" % e)
        return 2

    variant = a.variant or d.get("variant") or ""
    errs = validate(d, variant)
    if errs:
        print("[BLOCK] 数据不合法：")
        for e in errs:
            print("  - " + e)
        return 2

    tpl_path = os.path.join(a.template_dir, "character_board.%s.txt" % variant)
    if not os.path.isfile(tpl_path):
        print("[BLOCK] 找不到模板：%s" % tpl_path)
        return 2
    tpl = open(tpl_path, encoding="utf-8").read()
    text = render(tpl, flatten(d))

    if "{{" in text or "}}" in text:
        print("[BLOCK] 模板仍有未替换槽位：")
        for m in sorted(set(re.findall(r"\{\{[^}]+\}\}", text)))[:10]:
            print("  - " + m)
        return 2

    out = a.out or os.path.splitext(a.data)[0] + ".txt"
    if a.dry_run:
        print("[dry] %s 版｜%d 字｜将写 %s" % (variant, len(text), out))
        print(text[:400] + ("…" if len(text) > 400 else ""))
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[OK] %s 版｜%d 字 → %s" % (variant, len(text), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
