#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P7.5 提示词注入（L1：结构稿 → 注入固定串 → 校验）。

    python scripts/prompt_assemble.py \
      --draft "…/EP01_提示词_自己人_草稿.txt" \
      --bind "…/EP01_资产绑定.json" \
      --out "…/EP01_提示词_自己人.txt"

做的事（全部逐字，不让模型抄）：
  1. 用绑定表重写每组的【资产盘点】块（pn / vm）
  2. 重写【强制声明】为 C2 常量
  3. 缺 C1 禁用句就补进【质感与一致性】
  4. 校验：每组 pn 行数 = 绑定表；否则不落盘

退出码：0 成功｜2 BLOCK
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

C1 = ("参考图仅用于人物长相、发型与服装 / 空间结构与材质，"
      "画面中不得出现多视角拼贴、画中画、分格线、文字标注与色卡。")
C2 = ("【强制声明】无背景音乐；画面无字幕/台词文字/水印/Logo/角标/UI；"
      "声音：不要配乐，仅保留同期声；全程无背景音乐，仅保留真实环境音效与动作同期声。")


def strip_suffix(gid: str) -> str:
    return re.sub(r"_(自己人|标准|H3|B|C)$", "", gid.strip())


def block_for(g) -> str:
    chars = [p for p in g["pn"] if p.get("type") == "character"]
    scenes = [p for p in g["pn"] if p.get("type") == "scene"]
    props = [p for p in g["pn"] if p.get("type") == "prop"]
    skills = [p for p in g["pn"] if p.get("type") == "skill"]
    lines = ["【资产盘点】"]
    if chars:
        lines.append("人物视觉资产：" + "，".join("pn%d,%s=@" % (p["n"], p["name"]) for p in chars))
    if g.get("vm"):
        lines.append("人物音色资产：" + "，".join("vm%d,%s=@" % (v["n"], v["name"]) for v in g["vm"]))
    if scenes:
        lines.append("场景资产：" + "，".join("pn%d,%s=@" % (p["n"], p["name"]) for p in scenes))
    if props:
        lines.append("道具资产：" + "，".join("pn%d,%s=@" % (p["n"], p["name"]) for p in props))
    if skills:
        lines.append("技能参考资产：" + "，".join("pn%d,%s=@" % (p["n"], p["name"]) for p in skills))
    return "\n".join(lines)


def inject(block: str, g) -> str:
    new = block_for(g)
    if "【资产盘点】" in block:
        block = re.sub(r"【资产盘点】.*?(?=\n【|\n&&end)", new + "\n", block, count=1, flags=re.S)
    else:
        block = re.sub(r"(【统一风格模块】.*?)(?=\n【)", r"\1\n" + new + "\n", block, count=1, flags=re.S)

    if "【强制声明】" in block:
        block = re.sub(r"^【强制声明】.*$", C2, block, count=1, flags=re.M)
    else:
        block = block.replace(new, new + "\n" + C2, 1)

    if C1 not in block:
        if "【质感与一致性】" in block:
            block = re.sub(r"(【质感与一致性】[^\n]*\n)", r"\1" + C1 + "\n", block, count=1)
        else:
            block = block.replace("&&end", "【质感与一致性】\n" + C1 + "\n\n&&end")
    return block


def main() -> int:
    ap = argparse.ArgumentParser(description="提示词注入：pn 块 / 强制声明 / 禁用句")
    ap.add_argument("--draft", required=True)
    ap.add_argument("--bind", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    for p in (a.draft, a.bind):
        if not os.path.isfile(p):
            print("[BLOCK] 找不到文件：%s" % p)
            return 2
    bind = json.load(open(a.bind, encoding="utf-8"))
    groups = {g["gid"]: g for g in bind.get("groups", [])}
    text = open(a.draft, encoding="utf-8").read()

    def repl(m):
        inner = m.group(1)
        gid_m = re.search(r"分镜组ID[:：]\s*([^\s\n]+)", inner)
        if not gid_m:
            return m.group(0)
        gid = strip_suffix(gid_m.group(1))
        g = groups.get(gid)
        if not g:
            return m.group(0)
        return "&&start" + inject(inner, g) + "&&end"

    out = re.sub(r"&&start(.*?)&&end", repl, text, flags=re.S)

    # 校验：每组 pn 行数与绑定一致
    errs = []
    for b in re.findall(r"&&start(.*?)&&end", out, re.S):
        m = re.search(r"分镜组ID[:：]\s*([^\s\n]+)", b)
        if not m:
            continue
        gid = strip_suffix(m.group(1))
        g = groups.get(gid)
        if not g:
            errs.append("提示词有绑定表里没有的组：%s" % gid)
            continue
        got = [(p["n"], p["name"]) for p in g["pn"]]
        pn = [(int(n), nm.strip()) for n, nm in re.findall(r"pn(\d+),\s*([^=@，,\n]+)\s*=\s*@", b)]
        if got != pn:
            errs.append("组 %s pn 注入后仍不一致：绑定 %s / 稿子 %s" % (gid, got, pn))
        if g.get("vm"):
            vm = [(int(n), nm.strip()) for n, nm in re.findall(r"vm(\d+),\s*([^=@，,\n]+)\s*=\s*@", b)]
            want = [(v["n"], v["name"]) for v in g["vm"]]
            if want != vm:
                errs.append("组 %s vm 注入后不一致：绑定 %s / 稿子 %s" % (gid, want, vm))

    if errs:
        for e in errs:
            print("[BLOCK] " + e)
        return 2
    if a.dry_run:
        print("[dry] %d 组｜%d 字｜将写 %s" % (len(groups), len(out), a.out))
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)
    print("[OK] 注入完成｜%d 组｜%d 字 → %s" % (len(groups), len(out), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
