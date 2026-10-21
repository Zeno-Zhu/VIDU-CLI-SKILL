# -*- coding: utf-8 -*-
"""vidu.py —— 内置的 Vidu 客户端（纯 Python，不需要 Node / npm）。

只做几件事：查额度、提交、查进度、下载，外加生图。
**它不是调度器**，排队补位这些交给 AI 做。

    python scripts/vidu.py check
    python scripts/vidu.py submit --prompt-file S01.txt --image 人物/男主.png --duration 10
    python scripts/vidu.py batch --jobs jobs.tsv
    python scripts/vidu.py status
    python scripts/vidu.py pull --out ./out
    python scripts/vidu.py image --prompt "人物设定图：..." --name 男主

Token 从四个地方找，先找到先用：
    1. 环境变量 VIDU_TOKEN
    2. ~/.vidu-cli-skill/token.txt   ← 初始化脚本写这里，git pull 不会丢
    3. skill 目录的 .env 里的 VIDU_TOKEN
    4. 本目录的 token.txt
"""
from __future__ import annotations

import argparse
import json
import mimetypes
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOME_DIR = os.path.join(os.path.expanduser("~"), ".vidu-cli-skill")
BASE = os.environ.get("VIDU_BASE_URL", "https://service.vidu.cn").rstrip("/")
DEFAULT_LEDGER = os.path.join(ROOT, "out", "_台账.json")
INFLIGHT = ("created", "queueing", "preparation", "scheduling", "processing")
DONE = ("success", "failed", "canceled", "error")

IMG_MODEL = "3.2_image_2_5_pro"


# ─────────────────────── Token ───────────────────────
def load_token():
    t = (os.environ.get("VIDU_TOKEN") or "").strip()
    if t:
        return t, "环境变量"
    p = os.path.join(HOME_DIR, "token.txt")
    if os.path.isfile(p):
        v = open(p, encoding="utf-8").read().strip()
        if v:
            return v, p
    for d in (ROOT, os.path.dirname(ROOT)):
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("VIDU_TOKEN="):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if v:
                            return v, p
    p = os.path.join(HERE, "token.txt")
    if os.path.isfile(p):
        v = open(p, encoding="utf-8").read().strip()
        if v:
            return v, p
    return None, None


def need_token():
    t, _ = load_token()
    if not t:
        print("还没配 Token。两个办法：")
        print("  1) 双击 skill 目录下的「1-初始化环境.cmd」，它会带你走一遍")
        print("  2) 手动：在 %s 建 token.txt，里面写 token" % HOME_DIR)
        print("")
        print("Token 在 vidu.cn 左下角头像 → Vidu Token")
        sys.exit(2)
    return t


# ─────────────────────── 请求层 ───────────────────────
class API:
    def __init__(self, token=None):
        self.token = token or need_token()
        self.h = {"Authorization": "Token " + self.token,
                  "Content-Type": "application/json",
                  "User-Agent": "vidu-cli-skill/1.0"}

    def req(self, method, path, payload=None, timeout=120):
        data = json.dumps(payload).encode() if payload is not None else None
        url = path if path.startswith("http") else BASE + path
        r = urllib.request.Request(url, data=data, method=method, headers=self.h)
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                return resp.status, resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode("utf-8", "replace")
        except Exception as e:
            return -1, repr(e)

    def jget(self, path):
        c, b = self.req("GET", path)
        try:
            return c, json.loads(b)
        except Exception:
            return c, {"_raw": b[:300]}

    def quota(self):
        _, q = self.jget("/vidu/v1/tasks/quota")
        nq = q.get("nopeak_quota") or {}
        total = nq.get("total") or 0
        used = nq.get("used") or 0
        _, me = self.jget("/credit/v1/credits/me")
        return {"total": total, "used": used,
                "left": max(0, total - used) if total else 0,
                "credits": me.get("credits")}

    def inflight(self):
        _, j = self.jget("/vidu/v1/tasks/history/me?pager.pagesz=100&pager.page=0")
        return [t for t in (j.get("tasks") or []) if t.get("state") in INFLIGHT]

    @staticmethod
    def _probe(path, entries):
        try:
            r = subprocess.run(["ffprobe", "-v", "quiet", "-show_entries", entries,
                                "-of", "csv=p=0", path],
                               capture_output=True, text=True, timeout=20)
            return (r.stdout or "").strip()
        except Exception:
            return ""

    def upload(self, path):
        if not os.path.isfile(path):
            raise RuntimeError("找不到素材：%s" % path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        wh = self._probe(path, "stream=width,height").replace(",", "x").split("x")
        meta = {"image-width": wh[0] if wh[0].isdigit() else "1024",
                "image-height": wh[1] if len(wh) > 1 and wh[1].isdigit() else "1024"}
        c, b = self.req("POST", "/tools/v1/files/uploads", {"metadata": meta, "scene": "vidu"})
        if c != 200:
            raise RuntimeError("建上传失败 %s: %s" % (c, b[:200]))
        j = json.loads(b)
        uid, put = str(j.get("id") or ""), j.get("put_url") or ""
        if not uid or not put:
            raise RuntimeError("建上传返回异常：%s" % b[:200])
        ph = dict(j.get("headers") or {})
        if not any(k.lower() == "content-type" for k in ph):
            ph["Content-Type"] = mime
        with open(path, "rb") as f:
            blob = f.read()
        r = urllib.request.Request(put, data=blob, method="PUT", headers=ph)
        try:
            with urllib.request.urlopen(r, timeout=300) as resp:
                etag = resp.headers.get("ETag") or resp.headers.get("Etag") or ""
        except urllib.error.HTTPError as e:
            raise RuntimeError("上传失败 %s: %s" % (e.code, e.read()[:150]))
        c, b = self.req("PUT", "/tools/v1/files/uploads/%s/finish" % uid, {"etag": etag, "id": uid})
        if c != 200:
            raise RuntimeError("上传收尾失败 %s: %s" % (c, b[:150]))
        return "ssupload:?id=%s" % uid

    def submit(self, payload):
        c, b = self.req("POST", "/vidu/v1/tasks", payload)
        if c != 200:
            raise RuntimeError("%s %s" % (c, b[:300]))
        return json.loads(b)

    def task(self, tid):
        return self.jget("/vidu/v1/tasks/%s" % tid)[1]

    def creations(self, tid):
        j = self.task(tid)
        cs = j.get("creations") or []
        if isinstance(j.get("creation"), dict):
            cs = [j["creation"]] + list(cs)
        return cs

    def download(self, url, dest, tries=3):
        os.makedirs(os.path.dirname(dest) or ".", exist_ok=True)
        part = dest + ".part"
        for _ in range(tries):
            try:
                r = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                n = 0
                with urllib.request.urlopen(r, timeout=300) as resp, open(part, "wb") as f:
                    while True:
                        b = resp.read(1 << 16)
                        if not b:
                            break
                        f.write(b)
                        n += len(b)
                if n < 1024:
                    raise RuntimeError("文件太小")
                os.replace(part, dest)
                return n
            except Exception:
                if os.path.exists(part):
                    try:
                        os.remove(part)
                    except Exception:
                        pass
        raise RuntimeError("下载失败：%s" % url[:80])


# ─────────────────────── 请求体 ───────────────────────
def build_payload(job, api, mode, cache):
    kind = job.get("type") or "character2video"
    is_image = kind in ("text2image", "reference2image")
    settings = {
        "duration": 0 if is_image else int(job.get("duration") or 10),
        "model_version": job.get("model") or (IMG_MODEL if is_image else "3.4"),
        "resolution": job.get("resolution") or "1080p",
        "aspect_ratio": job.get("ratio") or "9:16",
        "sample_count": 1,
        "schedule_mode": "normal" if is_image else mode,
        "movement_amplitude": "auto",
        "use_trial": bool(is_image),
    }
    if not is_image:
        settings["codec"] = "h265"

    prompts = [{"type": "text", "content": job["prompt"]}]
    for img in job.get("images") or []:
        prompts.append({"type": "image", "content": _up(api, img, cache)})
    return {"type": kind,
            "input": {"prompts": prompts, "editor_mode": "normal", "enhance": True},
            "settings": settings}


def _up(api, path, cache):
    st = os.stat(path)
    k = "%s|%d|%d" % (os.path.abspath(path), st.st_size, int(st.st_mtime))
    if k not in cache:
        cache[k] = api.upload(path)
    return cache[k]


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


# ─────────────────────── 命令 ───────────────────────
def cmd_check(a):
    api = API()
    q = api.quota()
    live = api.inflight()
    print("闲时额度：%d/%d（今天还能跑 %d 条）" % (q["used"], q["total"], q["left"]))
    print("积分余额：%s" % q["credits"])
    print("进行中的任务：%d 条" % len(live))
    print("")
    print("可以开工了。")
    return 0


def cmd_submit(a):
    api = API()
    text = a.prompt or (open(a.prompt_file, encoding="utf-8").read() if a.prompt_file else "")
    if not text.strip():
        sys.exit("需要 --prompt 或 --prompt-file")
    job = {"id": a.name or "single", "prompt": text.strip(),
           "duration": a.duration, "ratio": a.ratio,
           "images": a.image, "type": a.type, "model": a.model}
    payload = build_payload(job, api, a.mode, {})
    if a.dry_run:
        print("[dry] %s %ss 图%d 模式%s"
              % (payload["type"], payload["settings"]["duration"],
                 len(a.image), payload["settings"]["schedule_mode"]))
        print(text.strip()[:200])
        return 0
    try:
        r = api.submit(payload)
    except RuntimeError as e:
        print("提交失败：%s" % e)
        print("常见原因：时长超界 / 没给图 / 提示词太长 / 闲时带了音频")
        return 1
    tid = str(r.get("id"))
    print("task_id = %s" % tid)
    led = load_ledger(a.ledger)
    led[job["id"]] = {"task_id": tid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                      "duration": job["duration"]}
    save_ledger(a.ledger, led)
    print("台账已记：%s" % a.ledger)
    return 0


def cmd_batch(a):
    api = API()
    if not os.path.isfile(a.jobs):
        sys.exit("找不到作业表：%s" % a.jobs)
    rows = []
    for ln, raw in enumerate(open(a.jobs, encoding="utf-8-sig"), 1):
        line = raw.rstrip("\r\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        c = line.split("\t") + [""] * 4
        sid, pfile, imgs, dur = c[0].strip(), c[1].strip(), c[2].strip(), c[3].strip()
        if not sid or not pfile:
            print("⚠ 第 %d 行缺镜头号或提示词文件，跳过" % ln)
            continue
        rows.append({"id": sid, "prompt_file": pfile,
                     "images": [x.strip() for x in imgs.split(",") if x.strip()],
                     "duration": int(dur or a.duration)})

    led = load_ledger(a.ledger)
    todo = [r for r in rows if r["id"] not in led]
    print("共 %d 条，待提交 %d 条" % (len(rows), len(todo)))
    if not todo:
        print("都提交过了，用 status 看进度")
        return 0

    q = api.quota()
    if q["left"] and len(todo) > q["left"]:
        print("⚠ 今天闲时还剩 %d 条，你要交 %d 条，超了会失败" % (q["left"], len(todo)))
    if len(todo) > 100:
        print("⚠ 闲时同时最多 100 个任务在跑，你交 %d 条。" % len(todo))
        print("  建议先交 100 条，跑完一批再补；或者加 --force 硬提交。")
        if not a.force:
            return 1

    cache, ok, fail = {}, 0, 0
    for r in todo:
        if not os.path.isfile(r["prompt_file"]):
            print("[%s] ✗ 找不到 %s" % (r["id"], r["prompt_file"]))
            fail += 1
            continue
        job = {"id": r["id"], "prompt": open(r["prompt_file"], encoding="utf-8").read(),
               "duration": r["duration"], "ratio": a.ratio,
               "images": r["images"], "type": a.type}
        if a.dry_run:
            print("[dry] %s %ss 图%d" % (r["id"], job["duration"], len(r["images"])))
            ok += 1
            continue
        try:
            res = api.submit(build_payload(job, api, a.mode, cache))
            tid = str(res.get("id"))
            led[r["id"]] = {"task_id": tid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "duration": job["duration"]}
            ok += 1
            print("[%s] → %s" % (r["id"], tid), flush=True)
            save_ledger(a.ledger, led)
        except Exception as e:
            fail += 1
            print("[%s] ✗ %s" % (r["id"], e), flush=True)
        time.sleep(a.pause)

    print("")
    print("提交成功 %d ｜ 失败 %d" % (ok, fail))
    if ok:
        print("接着跑：python scripts/vidu.py status")
    return 0 if not fail else 1


def cmd_status(a):
    api = API()
    led = load_ledger(a.ledger)
    if not led:
        sys.exit("台账是空的：%s" % a.ledger)
    stat = {}
    for sid, rec in led.items():
        d = api.task(rec["task_id"])
        st = d.get("state", "?")
        stat[st] = stat.get(st, 0) + 1
        extra = ""
        if st == "failed":
            extra = " %s %s" % (d.get("err_code") or "", d.get("err_msg") or "")
        print("%-12s %s%s" % (sid, st, extra))
    print("")
    print("汇总：" + " ｜ ".join("%s %d" % (k, v) for k, v in sorted(stat.items())))
    return 0


def cmd_pull(a):
    api = API()
    led = load_ledger(a.ledger)
    if not led:
        sys.exit("台账是空的：%s" % a.ledger)
    os.makedirs(a.out, exist_ok=True)
    got = 0
    for sid, rec in led.items():
        dst = os.path.join(a.out, sid + ".mp4")
        if os.path.isfile(dst) and os.path.getsize(dst) > 1024:
            continue
        d = api.task(rec["task_id"])
        if d.get("state") != "success":
            continue
        try:
            cs = api.creations(rec["task_id"])
            url = next((str(c[k]) for c in cs for k in ("download_uri", "nomark_uri", "uri")
                        if c.get(k)), None)
            if not url:
                print("[%s] 没拿到下载地址" % sid)
                continue
            api.download(url, dst)
            got += 1
            print("[%s] ✓ %.1f MB" % (sid, os.path.getsize(dst) / 1048576), flush=True)
        except Exception as e:
            print("[%s] ✗ %s" % (sid, e))
    print("")
    print("新下载 %d 个，目录 %s" % (got, a.out))
    return 0


def cmd_image(a):
    api = API()
    os.makedirs(a.out, exist_ok=True)
    job = {"id": a.name or "img", "prompt": a.prompt,
           "type": "reference2image" if a.ref else "text2image",
           "ratio": a.ratio, "images": a.ref or [], "model": a.model}
    payload = build_payload(job, api, "normal", {})
    if a.dry_run:
        print("[dry]", json.dumps(payload["settings"], ensure_ascii=False))
        return 0
    r = api.submit(payload)
    tid = str(r.get("id"))
    print("生图任务 %s，等它出…" % tid)
    d = {}
    for _ in range(60):
        d = api.task(tid)
        if d.get("state") in DONE:
            break
        time.sleep(3)
    if d.get("state") != "success":
        print("失败：%s %s" % (d.get("err_code"), d.get("err_msg")))
        return 1
    cs = api.creations(tid)
    url = next((str(c[k]) for c in cs for k in ("download_uri", "nomark_uri", "uri")
                if c.get(k)), None)
    if not url:
        print("没拿到图片地址")
        return 1
    dest = os.path.join(a.out, (a.name or tid) + ".png")
    api.download(url, dest)
    print("存好了：%s" % dest)
    return 0


def main():
    ap = argparse.ArgumentParser(description="Vidu 客户端（纯 Python，免装 Node）")
    ap.add_argument("--ledger", default=DEFAULT_LEDGER, help="台账路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="查闲时额度和积分").set_defaults(fn=cmd_check)

    p = sub.add_parser("submit", help="提交一条")
    p.add_argument("--prompt", default="")
    p.add_argument("--prompt-file", default="")
    p.add_argument("--image", action="append", default=[], help="可重复，顺序对应 pn1/pn2")
    p.add_argument("--duration", type=int, default=10)
    p.add_argument("--ratio", default="9:16")
    p.add_argument("--type", default="character2video",
                   choices=["character2video", "img2video"])
    p.add_argument("--mode", choices=["nopeak", "normal"], default="nopeak")
    p.add_argument("--model", default="")
    p.add_argument("--name", default="")
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_submit)

    p = sub.add_parser("batch", help="按作业表批量提交")
    p.add_argument("--jobs", required=True)
    p.add_argument("--ratio", default="9:16")
    p.add_argument("--type", default="character2video")
    p.add_argument("--mode", choices=["nopeak", "normal"], default="nopeak")
    p.add_argument("--duration", type=int, default=10)
    p.add_argument("--pause", type=float, default=1.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.set_defaults(fn=cmd_batch)

    p = sub.add_parser("status", help="查进度")
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("pull", help="下载已完成的")
    p.add_argument("--out", default=os.path.join(ROOT, "out"))
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.set_defaults(fn=cmd_pull)

    p = sub.add_parser("image", help="生图（资产图 / 参考图）")
    p.add_argument("--prompt", required=True)
    p.add_argument("--ref", action="append", default=[], help="参考图，可重复")
    p.add_argument("--name", default="")
    p.add_argument("--out", default=os.path.join(ROOT, "out"))
    p.add_argument("--ratio", default="9:16")
    p.add_argument("--model", default=IMG_MODEL)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_image)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
