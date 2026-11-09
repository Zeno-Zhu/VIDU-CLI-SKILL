#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P6 资产绑定（L2+L3，零 LLM）。

    分镜组表（含「出场资产」列） + 资产清单 → EPxx_资产绑定.json

    python scripts/bind_assets.py \
      --storyboard "…/EP01_分镜组.tsv" \
      --assets "…/资产清单.json" \
      --episode 1 --out "…/EP01_资产绑定.json" --freeze

    python scripts/bind_assets.py ... --dry-run

pn 规则（写死）：
  每组独立，从 1 开始；角色（首次出场）→ 场景 → 道具 → 技能参考（符最后）。
  随身道具 bound_to 到角色时不占 pn 槽。

退出码：0 成功｜2 BLOCK（缺列/缺图/错名/状态不合法/超上限）
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel_profile as CP  # noqa: E402

HEADER = {
    "gid": ["组号", "组", "分镜组", "分镜组id", "group"],
    "shot": ["分镜", "镜号", "分镜号", "镜头id", "shot"],
    "dur": ["时长", "秒", "duration", "秒数"],
    "line": ["台词", "对白", "语音", "说话", "口播", "旁白"],
    "asset": ["出场资产", "资产", "素材", "参考", "引用"],
}
TYPE_ORDER = {"character": 0, "scene": 1, "prop": 2, "skill": 3}
TYPE_LABEL = {"character": "角色", "scene": "场景", "prop": "道具", "skill": "技能"}


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_table(path: str):
    raw = [l for l in open(path, encoding="utf-8-sig").read().splitlines() if l.strip()]
    if not raw:
        raise ValueError("分镜组表是空的")
    rows = [r.split("\t") for r in raw] if "\t" in raw[0] else [r.split(",") for r in raw]
    header = [h.strip() for h in rows[0]]
    low = [h.lower().replace(" ", "") for h in header]
    idx = {}
    for key, names in HEADER.items():
        for i, h in enumerate(low):
            if h in [n.lower().replace(" ", "") for n in names]:
                idx[key] = i
                break
    missing = [k for k in ("gid", "dur", "asset") if k not in idx]
    if missing:
        raise ValueError("表头缺列：%s\n实际表头：%s\n需要「组号 / 时长 / 出场资产」"
                         % ("/".join(missing), " | ".join(header)))
    return rows[1:], idx


def cell(row, idx, key):
    i = idx.get(key)
    return row[i].strip() if i is not None and i < len(row) else ""


def tokens(s: str):
    parts = re.split(r"[,，、;；\s]+", (s or "").strip())
    return [p for p in parts if p]


def split_state(tok: str):
    m = re.match(r"^(.+?)[：:](.+)$", tok)
    return (m.group(1).strip(), m.group(2).strip()) if m else (tok, "")


def speakers(line: str):
    out = []
    for seg in re.split(r"[；;\n]", line or ""):
        m = re.match(r"^\s*([^\s：:<>{}]{1,12})\s*[（(]?(?:VO|画外)?[)）]?\s*[：:]", seg)
        if m:
            out.append(m.group(1).strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="分镜组 + 资产清单 → 绑定表（pn 唯一来源）")
    ap.add_argument("--storyboard", required=True)
    ap.add_argument("--assets", required=True)
    ap.add_argument("--episode", type=int, required=True)
    ap.add_argument("--out", default="", help="默认与分镜组表同目录 EPxx_资产绑定.json")
    ap.add_argument("--config", default="", help="项目配置.json；不给就向上找")
    ap.add_argument("--freeze", action="store_true", help="写入源文件 sha256")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--strict", action="store_true")
    a = ap.parse_args()

    for p in (a.storyboard, a.assets):
        if not os.path.isfile(p):
            print("[BLOCK] 找不到文件：%s" % p)
            return 2
    cfg_path = a.config or CP.find_config(a.storyboard) or CP.find_config(a.assets)
    if not cfg_path:
        print("[BLOCK] 找不到 项目配置.json —— 回 P0 初始化")
        return 2
    try:
        prof = CP.load_config(cfg_path)
    except Exception as e:
        print("[BLOCK] 项目配置不合法：%s" % e)
        return 2

    inv = json.load(open(a.assets, encoding="utf-8"))
    by_id = {x.get("id"): x for x in inv.get("assets", [])}
    by_name = {x.get("name"): x for x in inv.get("assets", [])}
    if not by_id:
        print("[BLOCK] 资产清单是空的")
        return 2

    try:
        rows, idx = read_table(a.storyboard)
    except Exception as e:
        print("[BLOCK] 分镜组表读不进来：%s" % e)
        return 2

    # 按组聚合
    order, groups = [], {}
    for n, row in enumerate(rows, 2):
        gid = cell(row, idx, "gid")
        if not gid:
            continue
        if gid not in groups:
            order.append(gid)
            groups[gid] = {"dur": 0.0, "tokens": [], "lines": []}
        try:
            groups[gid]["dur"] += float(re.sub(r"[^\d.]", "", cell(row, idx, "dur")) or 0)
        except ValueError:
            pass
        for t in tokens(cell(row, idx, "asset")):
            if t not in groups[gid]["tokens"]:
                groups[gid]["tokens"].append(t)
        if cell(row, idx, "line"):
            groups[gid]["lines"].append(cell(row, idx, "line"))

    errs, warns, out_groups = [], [], []
    max_img = int(prof.get("max_images", 9))

    for gid in order:
        g = groups[gid]
        if not g["tokens"]:
            errs.append("组 %s：出场资产列为空 —— 每组必填（角色 / 场景 / 道具）" % gid)
            continue
        picked, seen_char = [], set()
        scene = None
        for raw in g["tokens"]:
            base, state = split_state(raw)
            item = by_id.get(base) or by_name.get(base)
            if not item:
                errs.append("组 %s：资产「%s」不在资产清单里" % (gid, base))
                continue
            if item["id"] in seen_char:
                continue
            if item.get("status") not in ("final", "builtin"):
                errs.append("组 %s：资产「%s」状态是 %s，不是 final —— 先定稿"
                            % (gid, item["name"], item.get("status")))
                continue
            typ = item["type"]
            if typ == "character":
                states = item.get("states") or []
                if state:
                    names = [s.get("name") for s in states]
                    if state not in names:
                        errs.append("组 %s：角色「%s」没有状态「%s」（有：%s）"
                                    % (gid, item["name"], state, "/".join(names)))
                        continue
                else:
                    # 取本集对应的状态；不止一个就报错
                    hit = [s for s in states if a.episode in (s.get("episodes") or [])]
                    if len(hit) == 1:
                        state = hit[0]["name"]
                    elif len(hit) == 0 and len(states) == 1:
                        state = states[0]["name"]
                    else:
                        errs.append("组 %s：角色「%s」有多个状态，本组必须写「名字:状态」（本集命中：%s）"
                                    % (gid, item["name"], "/".join([s.get("name", "") for s in hit]) or "无"))
                        continue
                ep_ok = any(state == s.get("name") and a.episode in (s.get("episodes") or [])
                            for s in states)
                if not ep_ok:
                    errs.append("组 %s：角色「%s」的状态「%s」不在第 %d 集"
                                % (gid, item["name"], state, a.episode))
                    continue
                picked.append((typ, item, state))
                seen_char.add(item["id"])
            elif typ == "scene":
                if scene is not None:
                    errs.append("组 %s：出现两个场景「%s」「%s」—— 一组只能在一个场景"
                                % (gid, scene[1]["name"], item["name"]))
                    continue
                sub = state or ""
                if sub and sub not in (item.get("subscenes") or []):
                    errs.append("组 %s：场景「%s」没有子场景「%s」（有：%s）"
                                % (gid, item["name"], sub, "/".join(item.get("subscenes") or [])))
                    continue
                scene = (typ, item, sub)
                picked.append(scene)
            elif typ == "prop":
                if item.get("bound_to"):
                    picked.append((typ, item, state))
                    continue
                picked.append((typ, item, state))
            else:
                picked.append((typ, item, state))
        if scene is None:
            errs.append("组 %s：没有场景资产 —— 每组必须且只能有一个场景" % gid)
            continue

        # 说话人：必须在角色里
        sp = []
        for line in g["lines"]:
            for s in speakers(line):
                if s not in sp:
                    sp.append(s)
        char_names = [i["name"] for t, i, _ in picked if t == "character"]
        for s in sp:
            if s not in char_names:
                errs.append("组 %s：台词说话人「%s」不在出场角色里（当前：%s）"
                            % (gid, s, "/".join(char_names) or "无"))
        if len(sp) > 3:
            errs.append("组 %s：发言者 %d 名 > 3（平台音色上限）—— 拆组" % (gid, len(sp)))

        # 排序：角色（首次出场顺序）→ 场景 → 道具 → 技能；bound_to 道具不占槽
        picked.sort(key=lambda x: TYPE_ORDER[x[0]])
        final = []
        for typ, item, state in picked:
            if typ == "prop" and item.get("bound_to"):
                continue
            final.append((typ, item, state))
        if len(final) > max_img:
            errs.append("组 %s：图片 %d 张 > %s 上限 %d" % (gid, len(final), prof["channel"], max_img))

        pn = []
        for n, (typ, item, state) in enumerate(final, 1):
            f = item.get("file", "")
            if typ == "character" and state:
                st = next((s for s in item.get("states") or [] if s.get("name") == state), {})
                f = st.get("file") or (f if state == (item.get("states") or [{}])[0].get("name")
                                       else "%s-%s.png" % (item["name"], state))
            pn.append({"n": n, "id": item["id"], "name": item["name"],
                       "type": typ, "state": state,
                       "file": os.path.join("01_资产库", f) if typ != "skill" else f})
        if not any(t == "character" for t, _, _ in final):
            warns.append("组 %s：没有角色资产（纯空镜/环境组）" % gid)

        vm = []
        if prof["audio_ref"] == "required":
            for typ, item, state in final:
                if typ != "character" or not item.get("speaks"):
                    continue
                if item["name"] not in sp:
                    continue
                vf = (item.get("voice") or {}).get("file") or ("%s.wav" % item["name"])
                vm.append({"n": len(vm) + 1, "id": item["id"],
                           "name": "%s音色" % item["name"],
                           "file": os.path.join("01_资产库", "音色", os.path.basename(vf))})
            if len(vm) > 3:
                errs.append("组 %s：音色 %d 条 > 3" % (gid, len(vm)))

        out_groups.append({
            "gid": gid,
            "duration": int(round(g["dur"])) if g["dur"] else 0,
            "scene": {"id": scene[1]["id"], "name": scene[1]["name"], "subscene": scene[2]},
            "assets": [{"id": i["id"], "state": s, "speaks": (i["name"] in sp)}
                       for t, i, s in final],
            "pn": pn,
            "vm": vm,
        })

    if errs:
        for e in errs:
            print("[BLOCK] " + e)
        return 2
    for w in warns:
        print("[WARN] " + w)

    out = {
        "schema_version": "3.0",
        "episode": a.episode,
        "channel": prof["channel"],
        "frozen_at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "source": {
            "storyboard": os.path.abspath(a.storyboard),
            "assets": os.path.abspath(a.assets),
            "config": os.path.abspath(cfg_path),
            "storyboard_sha256": sha(a.storyboard),
            "assets_sha256": sha(a.assets),
        },
        "groups": out_groups,
    }
    if not a.freeze:
        out.pop("source", None)

    sb_dir = os.path.dirname(os.path.abspath(a.storyboard))
    if os.path.basename(sb_dir) == "分镜组":
        sb_dir = os.path.dirname(sb_dir)
    dest = a.out or os.path.join(sb_dir, "EP%02d_资产绑定.json" % a.episode)
    if a.dry_run:
        print("[dry] 第 %d 集｜%d 组｜%s" % (a.episode, len(out_groups), CP.summarize(prof)))
        for g in out_groups:
            print("  %s %2ds  " % (g["gid"], g["duration"])
                  + " ".join("pn%d=%s" % (p["n"], p["name"]) for p in g["pn"]))
        return 0

    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("[OK] 第 %d 集｜%d 组 → %s" % (a.episode, len(out_groups), dest))
    return 1 if (a.strict and warns) else 0


if __name__ == "__main__":
    sys.exit(main())
