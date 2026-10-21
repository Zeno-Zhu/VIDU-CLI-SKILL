#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""vidu.py —— 提交 / 查进度 / 下载 的小包装。

它不是调度器。它只做三件事：把作业表提交上去、查一下跑到哪了、把好的拉下来。
**排队补位、分批、盯进度这些，交给你自己的 AI 去做。**

用法：
    python vidu.py quota
    python vidu.py submit --jobs jobs.tsv --out ./out
    python vidu.py status --ledger ./out/_台账.json
    python vidu.py pull   --ledger ./out/_台账.json --out ./out

jobs.tsv 每行一条，制表符分隔，四列：
    镜头号 <TAB> 提示词文件 <TAB> 图片路径(逗号分隔，可空) <TAB> 时长
例：
    S01	prompts/S01.txt	img/male.png,img/room.png	15
    S02	prompts/S02.txt	img/male.png	8

提交前请确认环境变量 VIDU_TOKEN 已设置。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

MODEL = "3.4"          # Q4
RESOLUTION = "1080p"
MAX_INFLIGHT = 100     # 闲时同时最多 100 条


def exe():
    return shutil.which("vidu-cli") or "vidu-cli"


def run_cli(args, timeout=180):
    """调 vidu-cli，返回解析后的 JSON。"""
    try:
        p = subprocess.run([exe()] + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout,
                           env=os.environ)
    except FileNotFoundError:
        sys.exit("找不到 vidu-cli。先装：npm install -g vidu-cli@latest")
    out = (p.stdout or "").strip()
    try:
        return json.loads(out)
    except Exception:
        return {"ok": False, "error": {"message": (out or p.stderr or "")[:300]}}


def load_ledger(path):
    if path and os.path.isfile(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_ledger(path, data):
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ─────────────────────── 子命令 ───────────────────────
def cmd_quota(_a):
    d = run_cli(["quota", "pass"])
    print("闲时额度：", json.dumps(d, ensure_ascii=False))
    c = run_cli(["quota", "credit"])
    print("积分余额：", c.get("credits"))
    return 0


def cmd_submit(a):
    if not os.path.isfile(a.jobs):
        sys.exit("找不到作业表：%s" % a.jobs)
    rows = []
    for ln, raw in enumerate(open(a.jobs, encoding="utf-8-sig"), 1):
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        cols = line.split("\t") + [""] * 4
        sid, pfile, imgs, dur = cols[0].strip(), cols[1].strip(), cols[2].strip(), cols[3].strip()
        if not sid or not pfile:
            print("⚠ 第 %d 行缺镜头号或提示词文件，跳过" % ln)
            continue
        rows.append({"id": sid, "prompt_file": pfile,
                     "images": [x for x in imgs.split(",") if x.strip()],
                     "duration": int(dur or 15)})

    if not rows:
        sys.exit("作业表是空的")

    todo = [r for r in rows if r["id"] not in load_ledger(a.ledger)]
    print("共 %d 条，待提交 %d 条" % (len(rows), len(todo)))
    if not todo:
        print("都提交过了，用 status 看进度")
        return 0
    if len(todo) > MAX_INFLIGHT:
        print("⚠ 待提交 %d 条，超过闲时并发上限 %d。" % (len(todo), MAX_INFLIGHT))
        print("  建议先提交前 %d 条，跑完一批再补下一批：" % MAX_INFLIGHT)
        print("  给作业表加 --limit %d 重新跑，或者手动切分。" % MAX_INFLIGHT)
        if not a.force:
            return 1

    ledger = load_ledger(a.ledger)
    ok = fail = 0
    for r in todo:
        if not os.path.isfile(r["prompt_file"]):
            print("[%s] ✗ 找不到提示词文件 %s" % (r["id"], r["prompt_file"]))
            fail += 1
            continue
        prompt = open(r["prompt_file"], encoding="utf-8").read().strip()
        args = ["task", "submit",
                "--type", "character2video",
                "--prompt", prompt,
                "--duration", str(r["duration"]),
                "--model-version", MODEL,
                "--resolution", RESOLUTION,
                "--aspect-ratio", a.ratio,
                "--schedule-mode", a.mode]
        for img in r["images"]:
            args += ["--image", img]

        if a.dry_run:
            print("[dry] %s %ss 图%d" % (r["id"], r["duration"], len(r["images"])))
            ok += 1
            continue

        res = run_cli(args)
        if res.get("ok") and res.get("task_id"):
            ledger[r["id"]] = {"task_id": res["task_id"],
                               "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                               "duration": r["duration"]}
            ok += 1
            print("[%s] → %s" % (r["id"], res["task_id"]), flush=True)
        else:
            fail += 1
            print("[%s] ✗ %s" % (r["id"], json.dumps(res.get("error"), ensure_ascii=False)), flush=True)
        time.sleep(a.pause)

    if a.ledger and not a.dry_run:
        save_ledger(a.ledger, ledger)
        print("台账：%s" % a.ledger)
    print("\n提交成功 %d ｜ 失败 %d" % (ok, fail))
    if ok:
        print("接下来：python vidu.py status --ledger %s" % a.ledger)
    return 0 if not fail else 1


def cmd_status(a):
    ledger = load_ledger(a.ledger)
    if not ledger:
        sys.exit("台账是空的：%s" % a.ledger)
    stat = {}
    for sid, rec in ledger.items():
        d = run_cli(["task", "get", rec["task_id"]])
        st = d.get("state", "?")
        stat[st] = stat.get(st, 0) + 1
        print("%-10s %-14s %s" % (sid, st,
                                  json.dumps({k: d.get(k) for k in ("err_code", "err_msg") if d.get(k)},
                                             ensure_ascii=False) if st == "failed" else ""))
    print("\n汇总：" + " ｜ ".join("%s %d" % (k, v) for k, v in sorted(stat.items())))
    return 0


def cmd_pull(a):
    ledger = load_ledger(a.ledger)
    if not ledger:
        sys.exit("台账是空的：%s" % a.ledger)
    os.makedirs(a.out, exist_ok=True)
    got = 0
    for sid, rec in ledger.items():
        dst = os.path.join(a.out, sid + ".mp4")
        if os.path.isfile(dst) and os.path.getsize(dst) > 1024:
            continue
        d = run_cli(["task", "get", rec["task_id"]])
        if d.get("state") != "success":
            continue
        r = run_cli(["task", "get", rec["task_id"], "--output", a.out], timeout=600)
        files = r.get("downloaded_files") or []
        mp4 = next((f for f in files if f.lower().endswith(".mp4")), None)
        if not mp4:
            print("[%s] 没拿到 mp4" % sid)
            continue
        if os.path.abspath(mp4) != os.path.abspath(dst):
            os.replace(mp4, dst)
        got += 1
        print("[%s] ✓ %s" % (sid, dst), flush=True)
    print("\n新下载 %d 个，目录 %s" % (got, a.out))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Vidu 提交/查询/下载小工具")
    ap.add_argument("--ledger", default="./out/_台账.json", help="台账路径（记录镜头号→task_id）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("quota").set_defaults(fn=cmd_quota)

    p = sub.add_parser("submit", help="按作业表提交")
    p.add_argument("--jobs", required=True)
    p.add_argument("--out", default="./out")
    p.add_argument("--ratio", default="9:16")
    p.add_argument("--mode", choices=["nopeak", "normal"], default="nopeak")
    p.add_argument("--pause", type=float, default=1.0, help="每条之间停几秒，别连发")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="超过 100 条也硬提交")
    p.set_defaults(fn=cmd_submit)

    p = sub.add_parser("status", help="查进度")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("pull", help="下载已完成的")
    p.add_argument("--out", default="./out")
    p.set_defaults(fn=cmd_pull)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
