#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P8 作业单（L2，零 LLM）：绑定表 + 终稿 → jobs JSON。

    python scripts/jobs_build.py \
      --bind "…/EP01_资产绑定.json" \
      --prompt "…/EP01_提示词_自己人.txt" \
      --out "…/EP01_jobs.json"

images 顺序逐字抄绑定表的 pn；audios 抄 vm。
退出码：0 成功｜2 BLOCK（pn 不一致 / 文件缺失 / 配置缺失）
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel_profile as CP  # noqa: E402


def strip_suffix(gid: str) -> str:
    return re.sub(r"_(自己人|标准|H3|B|C)$", "", gid.strip())


def blocks(text: str):
    out = {}
    for b in re.findall(r"&&start(.*?)&&end", text, re.S):
        m = re.search(r"分镜组ID[:：]\s*([^\s\n]+)", b)
        if not m:
            continue
        gid = m.group(1).strip()
        pn = [(int(n), nm.strip()) for n, nm in re.findall(r"pn(\d+),\s*([^=@，,\n]+)\s*=\s*@", b)]
        vm = [(int(n), nm.strip()) for n, nm in re.findall(r"vm(\d+),\s*([^=@，,\n]+)\s*=\s*@", b)]
        out[strip_suffix(gid)] = {"id": gid, "body": b.strip(), "pn": pn, "vm": vm}
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="绑定表 + 提示词 → 作业单")
    ap.add_argument("--bind", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--out", default="")
    ap.add_argument("--config", default="")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    for p in (a.bind, a.prompt):
        if not os.path.isfile(p):
            print("[BLOCK] 找不到文件：%s" % p)
            return 2
    cfg_path = a.config or CP.find_config(a.prompt) or CP.find_config(a.bind)
    if not cfg_path:
        print("[BLOCK] 找不到 项目配置.json")
        return 2
    prof = CP.load_config(cfg_path)
    bind = json.load(open(a.bind, encoding="utf-8"))
    project = os.path.dirname(os.path.abspath(cfg_path))
    bs = blocks(open(a.prompt, encoding="utf-8").read())

    errs, jobs = [], []
    for g in bind.get("groups", []):
        gid = g["gid"]
        b = bs.get(gid)
        if not b:
            errs.append("提示词缺组：%s" % gid)
            continue
        want = [(p["n"], p["name"]) for p in g["pn"]]
        if want != b["pn"]:
            errs.append("组 %s pn 不一致：绑定 %s / 提示词 %s" % (gid, want, b["pn"]))
            continue
        wvm = [(v["n"], v["name"]) for v in g.get("vm", [])]
        if wvm != b["vm"]:
            errs.append("组 %s vm 不一致：绑定 %s / 提示词 %s" % (gid, wvm, b["vm"]))
            continue

        images = []
        for p in g["pn"]:
            if p.get("type") == "skill":
                root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                cand = [os.path.join(root, "assets", "常用符", p["name"] + ".png"),
                        os.path.join(root, "assets", "常用符", p["name"], "panel.png")]
                fp = next((x for x in cand if os.path.isfile(x)), "")
                if not fp or os.path.getsize(fp) < 1024:
                    errs.append("组 %s：pn%d 符面板不存在：%s" % (gid, p["n"], p["name"]))
                    continue
            else:
                fp = os.path.join(project, p["file"])
                if not os.path.isfile(fp) or os.path.getsize(fp) < 1024:
                    errs.append("组 %s：pn%d 文件不存在或 <1KB：%s" % (gid, p["n"], fp))
                    continue
            images.append({"name": p["name"], "path": fp})
        audios = []
        for v in g.get("vm", []):
            fp = os.path.join(project, v["file"])
            if not os.path.isfile(fp) or os.path.getsize(fp) < 1024:
                errs.append("组 %s：vm%d 文件不存在或 <1KB：%s" % (gid, v["n"], fp))
                continue
            audios.append({"speaker": v["name"].replace("音色", ""),
                           "name": v["name"], "path": fp})

        jobs.append({
            "id": b["id"],
            "src_id": gid,
            "duration": g["duration"],
            "ratio": prof["aspect"],
            "model": prof["label"],
            "resolution": prof["resolution"],
            "executor": prof["executor"],
            "n_images": len(images),
            "n_audios": len(audios),
            "images": images,
            "audios": audios,
            "prompt": b["body"],
            "prompt_chars": len(b["body"]),
        })

    if errs:
        for e in errs:
            print("[BLOCK] " + e)
        return 2
    out = {
        "_note": "由 jobs_build.py 从绑定表 + 提示词生成；pnN↔images[N-1]，vmN↔audios[N-1]。",
        "source": {"bind": os.path.abspath(a.bind), "prompt": os.path.abspath(a.prompt)},
        "channel": prof["channel"],
        "defaults": {"resolution": prof["resolution"], "ratio": prof["aspect"], "quantity": 1},
        "constraints": {"max_images": int(prof.get("max_images", 9)), "max_audios": 3,
                        "max_duration": prof["group_max_s"],
                        "prompt_max_chars": prof.get("prompt_max_chars")},
        "jobs": jobs,
    }
    dest = a.out or os.path.join(os.path.dirname(os.path.abspath(a.prompt)),
                                 "EP%02d_jobs.json" % bind.get("episode", 1))
    if a.dry_run:
        print("[dry] %d 组｜%d 图（最多）｜%d 音（最多）｜%s"
              % (len(jobs), max([j["n_images"] for j in jobs] or [0]),
                 max([j["n_audios"] for j in jobs] or [0]), CP.summarize(prof)))
        return 0
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with open(dest, "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("[OK] %d 组 → %s" % (len(jobs), dest))
    if prof["executor"] != "vidu":
        print("[NOTE] 当前渠道 %s 的执行层不在本包内；本作业单供对应渠道 skill 读取。" % prof["channel"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
