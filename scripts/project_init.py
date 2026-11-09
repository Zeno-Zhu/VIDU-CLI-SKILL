#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0 项目初始化：四问落盘，缺一项不许开工。

    python scripts/project_init.py "我的项目" --root "E:/AI视频项目/剧情电商" \
        --genre 都市短剧 --aspect 9:16 --channel vidu-q4 --resolution 1080p

    python scripts/project_init.py "我的项目" --check      # 只校验已有配置

必答四问：剧本类型 / 画幅 / 渠道（含模型）/ 分辨率。
其余（单组上限、优先档、镜数、提示词上限、声音通道、设定板版式）由渠道表派生。

退出码：0 成功｜2 参数/配置不合法（含落在 C 盘被拦）
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel_profile as CP  # noqa: E402

GENRES = ["都市短剧", "古装", "玄幻", "动画漫剧", "商业带货", "其他"]
ASPECTS = ["9:16", "16:9"]

README = """# {name}

> 本项目由 `project_init.py` 建立。所有阶段先读 `项目配置.json` 的 `profile`。

## 目录

```
00_剧本与提示词/
  _剧本全文.txt          用户给的原文，唯一台词真相
  资产清单.json          唯一资产表（角色/场景/道具/音色）
  _资产提示词/           角色-<名>.json/.txt、音色-<名>.txt
  EPxx/分镜组/           EPxx_分镜组.tsv
  EPxx/EPxx_资产绑定.json pn 唯一来源（P6 产出，冻结）
  EPxx/EPxx_jobs.json    作业单（P8 产出）
01_资产库/               图片扁平存放，文件名 = 资产名
  音色/                  仅音频参考渠道使用
02_分集工程/EPxx/视频/   成片
04_最终交付/
```

## 三条规矩

1. 资产库扁平，文件名 = 资产名。
2. pn 只由 `bind_assets.py` 分配，人和 AI 都不手写。
3. 只有 `status=final` 的资产能进绑定表。
"""


def on_c_drive(path: str) -> bool:
    if os.name != "nt":
        return False
    return os.path.splitdrive(os.path.abspath(path))[0].upper().startswith("C")


def write_if(path: str, text: str, force: bool = False) -> str:
    if os.path.exists(path) and not force:
        return "keep"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return "write"


def make_config(a) -> dict:
    profile = CP.derive(
        a.channel,
        genre=a.genre,
        aspect=a.aspect,
        resolution=a.resolution,
        group_max_s=a.group_max,
        group_min_s=a.group_min,
        prompt_max_chars=a.prompt_max,
        fixed_duration_s=a.duration,
    )
    profile["genre"] = a.genre
    profile["aspect"] = a.aspect
    profile["resolution"] = a.resolution
    return {
        "schema_version": "3.0",
        "project": a.name,
        "created_at": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "profile": profile,
    }


def spec_md(cfg: dict) -> str:
    p = cfg["profile"]
    lo, hi = (p.get("group_prefer_s") or [p["group_min_s"], p["group_max_s"]])[:2]
    pref = ("固定 %ss" % lo) if lo == hi else ("%s—%ss" % (lo, hi))
    cap = p.get("prompt_max_chars")
    return """# 制作口径

> 本文件由 `project_init.py` 生成，是项目级唯一口径。改口径先改 `项目配置.json`，再重跑本脚本。

| 项 | 值 |
|---|---|
| 项目 | {project} |
| 剧本类型 | {genre} |
| 画幅 | {aspect} |
| 渠道 | {label}（`{channel}`） |
| 分辨率 | {resolution} |
| 单组时长 | ≤ **{max}s**；{pref_cell} |
| 单镜时长 | ≥ 1.2s；≤ **{shot}s** |
| 镜数 | **按剧情节奏定，不设硬上限**（建议不超过 {soft}） |
| 提示词上限 | {cap} |
| 声音通道 | {audio} |
| 设定板版式 | **{board} 版** |

## 一句话

{summary}
""".format(
        project=cfg["project"], genre=p.get("genre", ""), aspect=p.get("aspect", ""),
        label=p.get("label", p["channel"]), channel=p["channel"], resolution=p.get("resolution", ""),
        max=p["group_max_s"], pref_cell=("**固定 %ss**" % lo if lo == hi else "优先 **%s—%ss**" % (lo, hi)), shot=p["shot_max_s"], soft=p["shots_soft_max"],
        cap=("不设上限" if not cap else "≤ %d 字" % cap),
        audio=("上传音频参考（提示词写 vm 行）" if p["audio_ref"] == "required"
               else "不上传音频；声线写进设定板 + 音色卡"),
        board=p["board_variant"], summary=CP.summarize(p))


def cmd_check(path: str) -> int:
    try:
        p = CP.load_config(path)
    except Exception as e:
        print("[FAIL] %s" % e)
        return 2
    print("[OK] " + CP.summarize(p))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="P0 项目初始化（四问 + 渠道 profile）")
    ap.add_argument("name", nargs="?", help="项目名")
    ap.add_argument("--root", default="", help="父目录；默认 E:/D:/F:/G: 下 AI视频项目/剧情电商")
    ap.add_argument("--genre", choices=GENRES, help="剧本类型")
    ap.add_argument("--aspect", choices=ASPECTS, help="画幅")
    ap.add_argument("--channel", help="渠道：%s" % " / ".join(CP.CHANNELS))
    ap.add_argument("--resolution", default="", help="分辨率：720p / 1080p / 2K")
    ap.add_argument("--group-max", type=float, default=None, help="覆盖单组上限（秒）")
    ap.add_argument("--group-min", type=float, default=None, help="覆盖组最小（秒）")
    ap.add_argument("--prompt-max", type=int, default=None, help="覆盖提示词上限；0 = 不设上限")
    ap.add_argument("--duration", type=float, default=None, help="固定组时长（如 sd2.5 的 30）")
    ap.add_argument("--episodes", type=int, default=16, help="预建集数，默认 16")
    ap.add_argument("--check", action="store_true", help="只校验已有 项目配置.json")
    ap.add_argument("--allow-c", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    if a.check:
        if not a.name:
            ap.error("--check 需要项目目录或 项目配置.json 路径")
        p = a.name
        if os.path.isdir(p):
            p = os.path.join(p, "项目配置.json")
        return cmd_check(p)

    if not a.name or not a.genre or not a.aspect or not a.channel:
        ap.error("必答四问：--genre / --aspect / --channel（--resolution 缺省取渠道默认）")
    if not a.resolution:
        a.resolution = CP.derive(a.channel)["resolution_default"]

    root = a.root.strip() if a.root else ""
    if not root:
        for d in ("E", "D", "F", "G"):
            if os.path.isdir(d + ":\\"):
                root = d + ":/AI视频项目/剧情电商"
                break
        else:
            root = os.path.expanduser("~/AI视频项目/剧情电商")
    proj = os.path.abspath(os.path.join(root, a.name))

    if on_c_drive(proj) and not a.allow_c:
        print("[BLOCK] 这个位置在 C 盘，不建：%s" % proj)
        print("加 --root 指到别的盘，或明确加 --allow-c。")
        return 2

    eps = max(1, min(a.episodes, 99))
    dirs = [
        "00_剧本与提示词/_资产提示词",
        "01_资产库",
        "01_资产库/音色",
        "03_背景音乐",
        "04_最终交付/创作截图",
    ]
    for i in range(1, eps + 1):
        dirs.append("02_分集工程/EP%02d/视频" % i)
        dirs.append("00_剧本与提示词/EP%02d/分镜组" % i)

    cfg = make_config(a)
    print("项目：%s" % proj)
    print("口径：%s" % CP.summarize(cfg["profile"]))
    if a.dry_run:
        for d in dirs:
            print("  + %s/" % d)
        print("[dry] 未落盘")
        return 0

    for d in dirs:
        os.makedirs(os.path.join(proj, d), exist_ok=True)

    write_if(os.path.join(proj, "项目配置.json"),
             json.dumps(cfg, ensure_ascii=False, indent=2), True)
    write_if(os.path.join(proj, "00_剧本与提示词", "_制作口径.md"), spec_md(cfg), a.force)
    write_if(os.path.join(proj, "00_剧本与提示词", "资产清单.json"),
             json.dumps({"schema_version": "3.0", "style": {"main": "", "texture": []},
                         "assets": []}, ensure_ascii=False, indent=2), a.force)
    write_if(os.path.join(proj, "_项目说明.md"), README.format(name=a.name), a.force)

    print("")
    print("已写：项目配置.json / 00_剧本与提示词/_制作口径.md / 资产清单.json")
    print("下一步：把剧本原文放 00_剧本与提示词/_剧本全文.txt，然后跑 P2 盘点。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
