#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""资产清单校验（L3 硬门）。

    python scripts/assets_check.py --file "…/资产清单.json"
    python scripts/assets_check.py --file "…/资产清单.json" --files --require-final
    python scripts/assets_check.py --file "…/资产清单.json" --strict

退出码：0 PASS（告警只呈现）｜2 BLOCK（结构错）｜1 仅 --strict 下告警也算失败
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel_profile as CP  # noqa: E402

TYPES = {"character", "scene", "prop", "skill"}
STATUS = {"planned", "candidate", "final", "rejected", "builtin"}


def main() -> int:
    ap = argparse.ArgumentParser(description="资产清单校验")
    ap.add_argument("--file", required=True)
    ap.add_argument("--config", default="", help="项目配置.json；不给就向上找")
    ap.add_argument("--files", action="store_true", help="检查 final 资产的文件是否存在")
    ap.add_argument("--require-final", action="store_true", help="不允许 candidate/planned 混入")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    if not os.path.isfile(a.file):
        print("[BLOCK] 找不到文件：%s" % a.file)
        return 2
    try:
        d = json.load(open(a.file, encoding="utf-8"))
    except Exception as e:
        print("[BLOCK] JSON 解析失败：%s" % e)
        return 2

    errs, warns = [], []
    if d.get("schema_version") != "3.0":
        errs.append("schema_version 必须是 3.0")
    style = d.get("style") or {}
    if not str(style.get("main", "")).strip():
        errs.append("style.main 为空（全剧统一画风）")
    assets = d.get("assets")
    if not isinstance(assets, list) or not assets:
        errs.append("assets 必须是非空数组")
        assets = []

    prof = None
    cfg_path = a.config or CP.find_config(a.file)
    if cfg_path and os.path.isfile(cfg_path):
        try:
            prof = CP.load_config(cfg_path)
        except Exception as e:
            warns.append("项目配置读取失败：%s" % e)

    ids, names = set(), set()
    pending_bind = []
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(a.file)))
    for i, x in enumerate(assets, 1):
        tag = "assets[%d]" % i
        if not isinstance(x, dict):
            errs.append("%s 不是对象" % tag)
            continue
        aid, name, typ = x.get("id", ""), x.get("name", ""), x.get("type", "")
        if not aid:
            errs.append("%s 缺 id" % tag)
        elif aid in ids:
            errs.append("id 重复：%s" % aid)
        ids.add(aid)
        if not name:
            errs.append("%s 缺 name" % tag)
        elif name in names:
            errs.append("name 重复：%s" % name)
        names.add(name)
        if typ not in TYPES:
            errs.append("%s type 非法：%s" % (tag, typ))
        st = x.get("status", "")
        if st not in STATUS:
            errs.append("%s status 非法：%s" % (tag, st))
        if a.require_final and st in ("planned", "candidate", "rejected"):
            errs.append("%s（%s）状态是 %s，不能进绑定" % (tag, name, st))

        f = x.get("file", "")
        if typ != "skill":
            if not f:
                errs.append("%s 缺 file" % tag)
            elif f != name + ".png":
                errs.append("%s file 必须等于 name + .png：%s ≠ %s.png" % (tag, f, name))

        if typ == "character":
            bv = x.get("board_variant", "")
            if bv not in ("A", "B"):
                errs.append("%s board_variant 必须是 A/B" % tag)
            if prof and bv != prof["board_variant"]:
                errs.append("%s 板式 %s ≠ 项目 %s" % (tag, bv, prof["board_variant"]))
            if not isinstance(x.get("speaks"), bool):
                errs.append("%s speaks 必须是 true/false" % tag)
            states = x.get("states") or []
            if not states:
                errs.append("%s 缺 states" % tag)
            snames, eps = set(), {}
            for s in states:
                sn = s.get("name", "")
                if not sn:
                    errs.append("%s 有 state 缺 name" % tag)
                elif sn in snames:
                    errs.append("%s state 重名：%s" % (tag, sn))
                snames.add(sn)
                if not (s.get("episodes") or []):
                    errs.append("%s 状态「%s」没有 episodes" % (tag, sn))
                if a.files and sn and st in ("final", "builtin"):
                    sf = s.get("file") or (x.get("file") if s is states[0] else "%s-%s.png" % (name, sn))
                    sp = os.path.join(project_dir, "01_资产库", sf)
                    if not os.path.isfile(sp) or os.path.getsize(sp) < 1024:
                        errs.append("%s 状态「%s」文件不存在或 <1KB：%s" % (tag, sn, sp))
                for ep in (s.get("episodes") or []):
                    if ep in eps:
                        errs.append("%s 第 %s 集同时属于状态「%s」和「%s」" % (tag, ep, eps[ep], sn))
                    eps[ep] = sn
            if len(states) > 3:
                warns.append("%s 有 %d 个状态（硬规矩 ≤3，优先 1—2）" % (tag, len(states)))
            voice = x.get("voice") or {}
            if x.get("speaks"):
                mode = voice.get("mode")
                if mode not in ("text", "audio"):
                    errs.append("%s 有台词但 voice.mode 不是 text/audio" % tag)
                if mode == "text":
                    if bv == "B":
                        errs.append("%s 是 B 版，声线应走 audio，不该用 text" % tag)
                    card = voice.get("card", "")
                    if not card:
                        errs.append("%s 缺 voice.card" % tag)
                    elif a.files and not os.path.isfile(os.path.join(project_dir, "00_剧本与提示词", "_资产提示词", card)):
                        errs.append("%s 音色卡不存在：%s" % (tag, card))
                if mode == "audio":
                    if bv == "A":
                        errs.append("%s 是 A 版，声线应走 text，不该用 audio" % tag)
                    wav = voice.get("file", "")
                    if not wav:
                        errs.append("%s 缺 voice.file" % tag)
                    elif a.files and not os.path.isfile(os.path.join(project_dir, "01_资产库", wav)):
                        errs.append("%s 音色 wav 不存在：%s" % (tag, wav))
            elif voice:
                warns.append("%s 没台词却填了 voice" % tag)

        if typ == "scene" and not (x.get("subscenes") or []):
            warns.append("%s 没有 subscenes（单场景可以忽略）" % tag)
        if typ == "prop" and x.get("bound_to"):
            pending_bind.append((tag, x["bound_to"]))

        if a.files and st in ("final", "builtin") and f:
            if typ == "skill":
                root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                cand = [os.path.join(root, "assets", "常用符", f),
                        os.path.join(root, "assets", "常用符", name, "panel.png")]
                if not any(os.path.isfile(x) and os.path.getsize(x) >= 1024 for x in cand):
                    errs.append("%s 符面板不存在：%s" % (tag, " / ".join(cand)))
            else:
                p = os.path.join(project_dir, "01_资产库", f)
                if not os.path.isfile(p) or os.path.getsize(p) < 1024:
                    errs.append("%s 文件不存在或 <1KB：%s" % (tag, p))

    for tag, ref in pending_bind:
        if ref not in ids:
            errs.append("%s bound_to 指向不存在的 id：%s" % (tag, ref))

    for w in warns:
        print("[WARN] " + w)
    for e in errs:
        print("[BLOCK] " + e)
    if not errs:
        print("[PASS] %d 个资产%s" % (len(assets), "（有告警）" if warns else ""))
        return 1 if (a.strict and warns) else 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
