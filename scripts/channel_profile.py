# -*- coding: utf-8 -*-
"""渠道参数表（唯一口径）。

所有脚本只从这里取时长 / 镜数 / 提示词上限 / 声音通道 / 设定板版式。
改数字只改这一处。
"""
from __future__ import annotations

import json
import os

CHANNELS = {
    "vidu-q4": {
        "label": "Vidu Q4",
        "aliases": ["vidu", "q4", "vidu q4", "vidu-q4"],
        "group_max_s": 16,
        "group_prefer_s": [12, 16],
        "group_min_s": 4,
        "shot_max_s": 6,
        "shots_soft_max": 10,
        "max_images": 9,
        "prompt_max_chars": 8000,
        "audio_ref": "none",
        "board_variant": "A",
        "aspect_default": "9:16",
        "resolution_default": "1080p",
        "resolutions": ["720p", "1080p", "2K"],
        "fixed_duration_s": None,
        "executor": "vidu",
    },
    "h3": {
        "label": "H3",
        "aliases": ["h3", "h3 api", "h3 dmc", "h3云端"],
        "group_max_s": 15,
        "group_prefer_s": [12, 15],
        "group_min_s": 4,
        "shot_max_s": 6,
        "shots_soft_max": 10,
        "max_images": 9,
        "prompt_max_chars": 8000,
        "audio_ref": "none",
        "board_variant": "A",
        "aspect_default": "9:16",
        "resolution_default": "1080p",
        "resolutions": ["720p", "1080p", "2K"],
        "fixed_duration_s": None,
        "executor": "external",
    },
    "jimeng-2.0": {
        "label": "即梦 2.0 / Seedance 2.0",
        "aliases": ["jimeng2", "jimeng-2.0", "seedance2.0", "sd2.0", "即梦2.0"],
        "group_max_s": 15,
        "group_prefer_s": [12, 15],
        "group_min_s": 4,
        "shot_max_s": 6,
        "shots_soft_max": 10,
        "max_images": 9,
        "prompt_max_chars": 8000,
        "audio_ref": "required",
        "board_variant": "B",
        "aspect_default": "9:16",
        "resolution_default": "1080p",
        "resolutions": ["720p", "1080p", "2K"],
        "fixed_duration_s": None,
        "executor": "external",
    },
    "jimeng-2.5": {
        "label": "即梦 2.5 / Seedance 2.5（API）",
        "aliases": ["jimeng2.5", "seedance2.5", "sd2.5", "即梦2.5", "云鲸"],
        "group_max_s": 30,
        "group_prefer_s": [25, 30],
        "group_min_s": 15,
        "shot_max_s": 8,
        "shots_soft_max": 14,
        "max_images": 12,
        "prompt_max_chars": None,
        "audio_ref": "required",
        "board_variant": "B",
        "aspect_default": "9:16",
        "resolution_default": "1080p",
        "resolutions": ["720p", "1080p", "2K"],
        "fixed_duration_s": 30,
        "executor": "external",
    },
    "wan3": {
        "label": "Wan 3",
        "aliases": ["wan3", "wan 3", "万相3"],
        "group_max_s": 30,
        "group_prefer_s": [],
        "group_min_s": 4,
        "shot_max_s": 8,
        "shots_soft_max": 14,
        "max_images": 12,
        "prompt_max_chars": None,
        "audio_ref": "required",
        "board_variant": "B",
        "aspect_default": "9:16",
        "resolution_default": "1080p",
        "resolutions": ["720p", "1080p", "2K"],
        "fixed_duration_s": None,
        "executor": "external",
    },
}


def resolve(name: str) -> str:
    key = (name or "").strip().lower().replace(" ", "")
    if key in CHANNELS:
        return key
    for cid, p in CHANNELS.items():
        for a in p["aliases"]:
            if key == a.lower().replace(" ", ""):
                return cid
    raise KeyError("未知渠道：%s（可选：%s）" % (name, " / ".join(CHANNELS)))


def derive(channel: str, **overrides) -> dict:
    cid = resolve(channel)
    p = dict(CHANNELS[cid])
    p["channel"] = cid
    p.pop("aliases", None)
    for k, v in overrides.items():
        if v not in (None, "", []):
            p[k] = v
    if p.get("fixed_duration_s"):
        p["group_prefer_s"] = [p["fixed_duration_s"], p["fixed_duration_s"]]
    return p


def load_config(path: str) -> dict:
    """读 项目配置.json，返回补全默认值后的 profile。"""
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    prof = cfg.get("profile") or {}
    if not prof.get("channel"):
        raise ValueError("项目配置.json 缺 profile.channel —— 回 P0 初始化")
    base = derive(prof["channel"])
    merged = dict(base)
    merged.update({k: v for k, v in prof.items() if v not in (None, "", [])})
    merged["channel"] = base["channel"]
    merged.setdefault("project", cfg.get("project", ""))
    return merged


def find_config(start: str) -> str:
    cur = os.path.abspath(start)
    if os.path.isfile(cur):
        cur = os.path.dirname(cur)
    for _ in range(6):
        p = os.path.join(cur, "项目配置.json")
        if os.path.isfile(p):
            return p
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return ""


def summarize(p: dict) -> str:
    lo, hi = (p.get("group_prefer_s") or [p["group_min_s"], p["group_max_s"]])[:2]
    pref = ("固定 %ss" % lo) if lo == hi else ("优先 %s—%ss" % (lo, hi))
    cap = p.get("prompt_max_chars")
    return ("%s｜单组 ≤%ss（%s）｜单镜 ≤%ss｜提示词 %s｜声音 %s｜设定板 %s版"
            % (p.get("label", p["channel"]), p["group_max_s"], pref, p["shot_max_s"],
               ("不设上限" if not cap else "≤%d 字" % cap),
               ("音频参考" if p["audio_ref"] == "required" else "文字锁定"),
               p["board_variant"]))
