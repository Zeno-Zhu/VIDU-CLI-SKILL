#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""四方对账（L3 硬门）：分镜组表 / 绑定表 / 提示词 / 作业单。

    python scripts/bind_check.py \
      --bind "…/EP01_资产绑定.json" \
      --prompt "…/EP01_提示词_自己人.txt" \
      --jobs "…/EP01_jobs.json" \
      --assets "…/资产清单.json" --strict

只比 pn / vm 的 (n, name) 序列；顺序不一致就是换脸换嗓。
退出码：0 PASS｜2 BLOCK｜1 仅 --strict 下告警也算失败
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel_profile as CP  # noqa: E402


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_suffix(gid: str) -> str:
    return re.sub(r"_(自己人|标准|H3|B|C)$", "", gid.strip())


def prompt_blocks(text: str):
    out = {}
    for b in re.findall(r"&&start(.*?)&&end", text, re.S):
        m = re.search(r"分镜组ID[:：]\s*([^\s\n]+)", b)
        if not m:
            continue
        gid = strip_suffix(m.group(1))
        pn = [(int(n), nm.strip()) for n, nm in re.findall(r"pn(\d+),\s*([^=@，,\n]+)\s*=\s*@", b)]
        vm = [(int(n), nm.strip()) for n, nm in re.findall(r"vm(\d+),\s*([^=@，,\n]+)\s*=\s*@", b)]
        out[gid] = {"pn": pn, "vm": vm, "body": b}
    return out


def fmt(seq):
    return " ".join("%d:%s" % (n, nm) for n, nm in seq) or "（空）"


def main() -> int:
    ap = argparse.ArgumentParser(description="表 / 绑定 / 提示词 / 作业单 四方对账")
    ap.add_argument("--bind", required=True)
    ap.add_argument("--prompt", default="")
    ap.add_argument("--jobs", default="")
    ap.add_argument("--assets", default="")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.bind):
        print("[BLOCK] 找不到绑定表：%s" % a.bind)
        return 2
    bind = json.load(open(a.bind, encoding="utf-8"))
    groups = {g["gid"]: g for g in bind.get("groups", [])}
    errs, warns = [], []

    # hash
    src = bind.get("source") or {}
    if src:
        for key, path_key in (("storyboard_sha256", "storyboard"), ("assets_sha256", "assets")):
            p = src.get(path_key, "")
            if p and os.path.isfile(p):
                if sha(p) != src.get(key):
                    errs.append("%s 已改动（hash 不一致）—— 重跑 bind_assets.py --freeze" % path_key)

    # 资产状态 + 文件
    if a.assets:
        if not os.path.isfile(a.assets):
            errs.append("找不到资产清单：%s" % a.assets)
        else:
            inv = {x["id"]: x for x in json.load(open(a.assets, encoding="utf-8")).get("assets", [])}
            project = os.path.dirname(os.path.dirname(os.path.abspath(a.assets)))
            for g in groups.values():
                for p in g.get("pn", []):
                    it = inv.get(p["id"])
                    if not it:
                        errs.append("组 %s：pn%d 的 id %s 不在资产清单" % (g["gid"], p["n"], p["id"]))
                        continue
                    if it.get("status") not in ("final", "builtin"):
                        errs.append("组 %s：pn%d「%s」状态是 %s，不是 final"
                                    % (g["gid"], p["n"], p["name"], it.get("status")))
                    fp = p.get("file", "")
                    if fp and it.get("type") != "skill":
                        full = os.path.join(project, fp)
                        if not os.path.isfile(full) or os.path.getsize(full) < 1024:
                            errs.append("组 %s：pn%d 文件不存在或 <1KB：%s" % (g["gid"], p["n"], full))

    # 提示词
    if a.prompt:
        if not os.path.isfile(a.prompt):
            errs.append("找不到提示词：%s" % a.prompt)
        else:
            blocks = prompt_blocks(open(a.prompt, encoding="utf-8").read())
            for gid, g in groups.items():
                if gid not in blocks:
                    errs.append("提示词缺组：%s" % gid)
                    continue
                want = [(p["n"], p["name"]) for p in g.get("pn", [])]
                got = blocks[gid]["pn"]
                if want != got:
                    errs.append("组 %s pn 顺序不一致\n    绑定：%s\n    提示词：%s"
                                % (gid, fmt(want), fmt(got)))
                wvm = [(v["n"], v["name"]) for v in g.get("vm", [])]
                gvm = blocks[gid]["vm"]
                if wvm != gvm:
                    errs.append("组 %s vm 顺序不一致\n    绑定：%s\n    提示词：%s"
                                % (gid, fmt(wvm), fmt(gvm)))
            for gid in blocks:
                if gid not in groups:
                    warns.append("提示词有绑定表里没有的组：%s" % gid)

    # 作业单
    if a.jobs:
        if not os.path.isfile(a.jobs):
            errs.append("找不到作业单：%s" % a.jobs)
        else:
            j = json.load(open(a.jobs, encoding="utf-8"))
            jobs = {strip_suffix(x.get("id", "")): x for x in j.get("jobs", [])}
            for gid, g in groups.items():
                if gid not in jobs:
                    errs.append("作业单缺组：%s" % gid)
                    continue
                want = [p["name"] for p in g.get("pn", [])]
                got = [x.get("name") for x in jobs[gid].get("images", [])]
                if want != got:
                    errs.append("组 %s images 顺序不一致\n    绑定：%s\n    作业单：%s"
                                % (gid, " ".join(want) or "（空）", " ".join([str(x) for x in got])))
                wvm = [v["name"] for v in g.get("vm", [])]
                gvm = [x.get("name") for x in jobs[gid].get("audios", [])]
                if wvm != gvm:
                    errs.append("组 %s audios 顺序不一致\n    绑定：%s\n    作业单：%s"
                                % (gid, " ".join(wvm) or "（空）", " ".join([str(x) for x in gvm])))

    for w in warns:
        print("[WARN] " + w)
    for e in errs:
        print("[BLOCK] " + e)
    if not errs:
        print("[PASS] %d 组｜pn/vm 四方一致%s" % (len(groups), "（有告警）" if warns else ""))
        return 1 if (a.strict and warns) else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
