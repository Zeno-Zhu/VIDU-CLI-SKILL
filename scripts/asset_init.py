#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建一条片子的项目骨架（资产管理目录）。

一条片子的图、音、成片会散在几十个地方，手工建文件夹迟早漏。
这条命令一次把整棵树建好，并落一份空的 资产清单.json。

用法：
    python scripts/asset_init.py 我的项目
    python scripts/asset_init.py 我的项目 --root "D:/AI视频项目/剧情电商"
    python scripts/asset_init.py 我的项目 --episodes 24 --force

约定：
    · 资产库平铺，不分子目录；文件名就是资产名
    · 图放 01_资产库/<名字>.png，音色放 01_资产库/<名字>音色.wav
    · 默认不建在 C 盘；真要在 C 盘，加 --allow-c

退出码：0 建好了｜2 参数不对｜3 落在 C 盘被拦下
"""

import argparse
import datetime
import json
import os
import re
import sys

PROJECT_ROOT_DIR = "AI视频项目/剧情电商"

GETNAME_BAT = r"""@echo off
setlocal enabledelayedexpansion
:: 列出本目录下所有资产名（不含后缀），用来核对盘点表
echo ==============================================
echo 正在扫描当前文件夹中的文件（排除本程序）...
echo ==============================================
echo.

for %%i in (*.*) do (
    if not "%%~nxi"=="%~nx0" (
        echo %%~ni
    )
)

echo.
echo ==============================================
echo 扫描完成！按任意键退出
echo ==============================================
pause >nul
endlocal
"""

README_MD = """# {name}

这条片子的工作目录。

## 目录

```
00_剧本与提示词/     剧本、大纲、每个资产的出图提示词、分镜组表、自定义模板
01_资产库/           人物 / 场景 / 道具 / 音色，平铺，文件名就是资产名
02_分集工程/EPxx/视频 成片，一组一个 mp4
03_背景音乐/
04_最终交付/创作截图/
```

## 三条规矩

1. **资产库平铺。** 别在 `01_资产库/` 下面再建子目录，写提示词时天天拼路径，错一次就换脸。
2. **文件名 = 资产名。** 提示词里写 `[@男主]`，提交时就是 `--image 01_资产库/男主.png`。
3. **音色叫「名字 + 音色」。** `男主音色.wav`，一眼看出是声音不是图。

## 每次生完资产

- 图片放进 `01_资产库/`
- 提示词存进 `00_剧本与提示词/_资产提示词/<资产名>.txt`
- `资产清单.json` 补一条（id / name / file / status）
- 跑 `python scripts/assets_check.py --file "00_剧本与提示词/资产清单.json"`

## 下一步

```bash
python scripts/asset_init.py --help
python scripts/storyboard_check.py 00_剧本与提示词/EP01/分镜组/EP01_分镜组.tsv
```
"""


def candidate_roots():
    """挑一个非系统盘作为默认位置。"""
    out = []
    if os.name == "nt":
        for drive in ("E", "D", "F", "G"):
            if os.path.isdir(drive + ":\\"):
                out.append(drive + ":/" + PROJECT_ROOT_DIR)
    out.append(os.path.expanduser("~/" + PROJECT_ROOT_DIR))
    return out


def on_c_drive(path):
    if os.name != "nt":
        return False
    drive = os.path.splitdrive(os.path.abspath(path))[0].upper()
    return drive.startswith("C")


def write_if(path, text, force=False, newline="\n"):
    if os.path.exists(path) and not force:
        return "keep"
    with open(path, "w", encoding="utf-8", newline=newline) as f:
        f.write(text)
    return "write"


def main():
    ap = argparse.ArgumentParser(description="建项目骨架：剧本 / 资产库 / 分集工程 / 背景音乐 / 最终交付")
    ap.add_argument("name", help="项目名，会当成文件夹名")
    ap.add_argument("--root", default="", help="建在哪个父目录下，默认挑一个非 C 盘")
    ap.add_argument("--episodes", type=int, default=16, help="预建多少集目录，默认 16")
    ap.add_argument("--allow-c", action="store_true", help="允许建在 C 盘（不建议）")
    ap.add_argument("--force", action="store_true", help="覆盖已存在的模板文件")
    ap.add_argument("--dry-run", action="store_true", help="只看会建在哪，不落盘")
    a = ap.parse_args()

    name = a.name.strip().strip("/\\")
    if not name or re.search(r'[\\/:*?"<>|]', name):
        print("项目名里有不能用于文件名的字符：%s" % a.name)
        return 2

    root = a.root.strip() if a.root else candidate_roots()[0]
    proj = os.path.abspath(os.path.join(root, name))

    if on_c_drive(proj) and not a.allow_c:
        print("这个位置在 C 盘，不建：%s" % proj)
        print("")
        print("视频素材几个 G 起步，放系统盘迟早出事。建议改到别的盘：")
        for c in candidate_roots()[:-1]:
            print('   python scripts/asset_init.py "%s" --root "%s"' % (name, c))
        print("")
        print("机器上确实只有 C 盘，那就加 --allow-c 硬建。")
        return 3

    eps = max(1, min(a.episodes, 99))
    dirs = [
        "00_剧本与提示词/_资产提示词",
        "00_剧本与提示词/_模板",
        "01_资产库",
        "03_背景音乐",
        "04_最终交付/创作截图",
    ]
    for i in range(1, eps + 1):
        dirs.append("02_分集工程/EP%02d/视频" % i)
        dirs.append("00_剧本与提示词/EP%02d/分镜组" % i)

    print("项目：%s" % proj)
    print("父目录：%s%s" % (root, "（C 盘，已确认）" if on_c_drive(proj) else ""))
    if a.dry_run:
        print("")
        for d in dirs:
            print("  + %s/" % d)
        print("")
        print("[dry] 没落盘。去掉 --dry-run 就建。")
        return 0

    for d in dirs:
        os.makedirs(os.path.join(proj, d), exist_ok=True)

    acts = []
    acts.append(("01_资产库/getname.bat",
                 write_if(os.path.join(proj, "01_资产库/getname.bat"), GETNAME_BAT, a.force,
                          newline="\r\n")))

    inv = {"schema_version": "3.0", "style": {"main": "", "texture": []}, "assets": []}
    acts.append(("00_剧本与提示词/资产清单.json",
                 write_if(os.path.join(proj, "00_剧本与提示词/资产清单.json"),
                          json.dumps(inv, ensure_ascii=False, indent=2), a.force)))

    acts.append(("_项目说明.md",
                 write_if(os.path.join(proj, "_项目说明.md"), README_MD.format(name=name), a.force)))

    print("")
    for d in dirs:
        print("  + %s/" % d)
    print("")
    for p, r in acts:
        print("  %s %s" % ("↻" if r == "write" else "·", p))
    print("")
    print("下一句这么说：把剧本放 00_剧本与提示词/_剧本全文.txt，然后开始盘资产。")
    print("资产库：%s" % os.path.join(proj, "01_资产库"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
