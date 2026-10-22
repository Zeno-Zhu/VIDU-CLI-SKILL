# -*- coding: utf-8 -*-
"""vidu.py —— 内置的 Vidu 客户端（纯 Python，不需要 Node / npm）。

只做几件事：查额度、提交、查进度、下载，外加生图、做符、管符库。
**它不是调度器**，排队补位这些交给 AI 做。

    python scripts/vidu.py check
    python scripts/vidu.py submit --prompt-file S01.txt --image 人物/男主.png --duration 10
    python scripts/vidu.py batch --jobs jobs.tsv
    python scripts/vidu.py status
    python scripts/vidu.py pull --out ./out
    python scripts/vidu.py image --prompt "人物设定图：..." --name 男主
    python scripts/vidu.py card --name 太极拳 --prompt-file out/符/符-太极拳/prompt.txt
    python scripts/vidu.py lib
    python scripts/vidu.py lib --q 太极 --show 符-太极拳

Token 从四个地方找，先找到先用：
    1. 环境变量 VIDU_TOKEN
    2. ~/.vidu-cli-skill/token.txt   ← 初始化脚本写这里，git pull 不会丢
    3. skill 目录的 .env 里的 VIDU_TOKEN
    4. 本目录的 token.txt
"""
from __future__ import annotations

import argparse
import json
import math
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

# ── 生图提示词的两句固定话 ───────────────────────────────────
# 开场语：堵住模型自己翻译、自己改写术语、自己加戏。
OPEN_LINE = ("请一字不改严格按照以下中文提示词生成图片，"
             "不要翻译、不要改写、不要添加内容：")

# 尾缀：压碎噪点与冗余高频细节。按风格化程度伸缩，不是越长越好。
# 完整版出处：倒放《一体成型：image 2.5 碎噪点已攻克》
TAIL_FULL = "归约细节灭高频冗余，软泛焦均质简谐流"
TAIL_MID = "归约细节，灭高频冗余"
TAIL_MIN = "归约细节"
TAILS = {"full": TAIL_FULL, "mid": TAIL_MID, "min": TAIL_MIN, "none": ""}


def _wrap(text, tail="full"):
    """开场语 + 正文 + 尾缀。正文一个字不改，重复调用不会叠加。"""
    text = (text or "").strip()
    if not text:
        return text
    if not text.startswith(OPEN_LINE):
        text = OPEN_LINE + "\n\n" + text
    t = TAILS.get(tail, TAIL_FULL)
    if t and not text.rstrip().endswith(t):
        text = text.rstrip() + "\n\n" + t
    return text


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

    def upload(self, path, kind="image"):
        """上传素材。kind="audio" 时按音频元数据建单（duration 取整秒）。"""
        if not os.path.isfile(path):
            raise RuntimeError("找不到素材：%s" % path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if kind == "audio":
            d = self._probe(path, "format=duration")
            try:
                secs = max(1, int(math.ceil(float(d))))
            except (TypeError, ValueError):
                secs = 1
            meta = {"duration": str(secs)}
        else:
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
        prompts.append({"type": "image", "content": _up(api, img, cache, "image")})
    # 音色参考：≤3 条（官方上限，超出会被静默忽略）
    auds = job.get("audios") or []
    if len(auds) > 3:
        print("⚠ 音色 %d 条超过上限 3，只取前 3 条" % len(auds))
        auds = auds[:3]
    for au in auds:
        prompts.append({"type": "audio", "content": _up(api, au, cache, "audio"),
                        "name": os.path.basename(au)})
    return {"type": kind,
            "input": {"prompts": prompts, "editor_mode": "normal", "enhance": True},
            "settings": settings}


def _up(api, path, cache, kind="image"):
    st = os.stat(path)
    k = "%s|%d|%d|%s" % (os.path.abspath(path), st.st_size, int(st.st_mtime), kind)
    if k not in cache:
        cache[k] = api.upload(path, kind=kind)
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
           "images": a.image, "audios": a.audio, "type": a.type, "model": a.model}
    payload = build_payload(job, api, a.mode, {})
    if a.dry_run:
        print("[dry] %s %ss 图%d 音%d 模式%s"
              % (payload["type"], payload["settings"]["duration"],
                 len(a.image), len(a.audio), payload["settings"]["schedule_mode"]))
        for au in a.audio:
            print("      音色参考：%s" % os.path.basename(au))
        print(text.strip()[:200])
        return 0
    try:
        r = api.submit(payload)
    except RuntimeError as e:
        print("提交失败：%s" % e)
        print("常见原因：时长超界 / 没给图 / 提示词太长 / 音色超过 3 条 / 开了 lip_sync 又用闲时")
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
        c = line.split("\t") + [""] * 5
        sid, pfile, imgs, dur, auds = (c[0].strip(), c[1].strip(), c[2].strip(),
                                       c[3].strip(), c[4].strip())
        if not sid or not pfile:
            print("⚠ 第 %d 行缺镜头号或提示词文件，跳过" % ln)
            continue
        rows.append({"id": sid, "prompt_file": pfile,
                     "images": [x.strip() for x in imgs.split(",") if x.strip()],
                     "audios": [x.strip() for x in auds.split(",") if x.strip()],
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
               "images": r["images"], "audios": r.get("audios") or [], "type": a.type}
        if a.dry_run:
            print("[dry] %s %ss 图%d 音%d"
                  % (r["id"], job["duration"], len(r["images"]), len(job["audios"])))
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
    text = _wrap(_read_prompt(a), getattr(a, "tail", "full"))
    os.makedirs(a.out, exist_ok=True)
    name = a.name or "img"
    if a.dry_run:
        print("[dry] %s ｜ %d 字 ｜ 尾缀：%s ｜ → %s"
              % (a.ratio, len(text), _tail_label(a),
                 os.path.join(a.out, name + ".png")))
        return 0
    api = API()
    job = {"id": name, "prompt": text,
           "type": "reference2image" if a.ref else "text2image",
           "ratio": a.ratio, "images": a.ref or [], "model": a.model,
           "resolution": a.resolution}
    payload = build_payload(job, api, "normal", {})
    _warn_long(text)
    r = api.submit(payload)
    tid = str(r.get("id"))
    print("生图任务 %s，等它出…（尾缀：%s）" % (tid, _tail_label(a)))
    d = _wait_image(api, tid, a.wait)
    if d.get("state") != "success":
        print("失败：%s %s" % (d.get("err_code"), d.get("err_msg")))
        return 1
    dest = os.path.join(a.out, name + ".png")
    if not _save_image(api, tid, dest):
        return 1
    print("存好了：%s（%d KB）" % (dest, os.path.getsize(dest) // 1024))
    return 0


def cmd_card(a):
    """符：16:9 能力面板。一张图讲清一个 AI 视频能力。"""
    text = _wrap(_read_prompt(a), getattr(a, "tail", "full"))
    raw = (a.name or "").strip() or time.strftime("符-%m%d-%H%M")
    name = _slug(raw)
    if not name.startswith("符"):
        name = "符-" + name
    out = a.out or os.path.join(ROOT, "out", "符", name)

    if a.dry_run:
        print("[dry] %s ｜ %d 字 ｜ 尾缀：%s ｜ → %s"
              % (a.ratio, len(text), _tail_label(a),
                 os.path.join(out, "panel.png")))
        print(text[:160].replace("\n", " "))
        return 0

    os.makedirs(out, exist_ok=True)
    api = API()
    job = {"id": name, "prompt": text,
           "type": "reference2image" if a.ref else "text2image",
           "ratio": a.ratio, "images": a.ref or [], "model": a.model,
           "resolution": a.resolution}
    payload = build_payload(job, api, "normal", {})

    _warn_long(text)
    # 存一份实际用的提示词（含开场语和尾缀），改字重跑时直接改它
    open(os.path.join(out, "prompt.txt"), "w", encoding="utf-8").write(text)

    r = api.submit(payload)
    tid = str(r.get("id"))
    print("生图任务 %s，等它出…（尾缀：%s）" % (tid, _tail_label(a)))
    d = _wait_image(api, tid, a.wait)
    if d.get("state") != "success":
        print("失败：%s %s" % (d.get("err_code"), d.get("err_msg")))
        return 1
    dest = os.path.join(out, "panel.png")
    if not _save_image(api, tid, dest):
        return 1
    print("符出好了：%s（%d KB）" % (dest, os.path.getsize(dest) // 1024))
    print("错字就改 %s 再跑一遍，别重画整段。" % os.path.join(out, "prompt.txt"))

    if not a.no_lib:
        if a.meta:
            meta = dict(_read_meta(a.meta))
        else:
            mp = os.path.join(out, "meta.json")
            meta = dict(_read_meta(mp)) if os.path.isfile(mp) else {}
        # 实际用的尾缀登记进档案，别人照着跑能得到同样结果
        meta["tail"] = _tail_label(a)
        if a.meta and os.path.abspath(a.meta) != os.path.abspath(os.path.join(out, "meta.json")):
            with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f, ensure_ascii=False, indent=1)
        if a.tag:
            meta["tags"] = a.tag
        n = upsert_card(_card_entry(out, meta))
        print("入库：%s ｜ 库里现在 %d 张，`lib` 可以看" % (meta.get("name") or name, n))
        if not meta:
            print("   ⚠ 没给 --meta，这张符在库里只有名字，没有「管什么 / 何时调」。"
                  "补一个：lib --add %s" % out)
    return 0


def _tail_label(a):
    t = getattr(a, "tail", "full")
    return TAILS.get(t, TAIL_FULL) or "无"


def _read_prompt(a):
    text = (getattr(a, "prompt", "") or "").strip()
    if not text and getattr(a, "prompt_file", ""):
        if not os.path.isfile(a.prompt_file):
            sys.exit("找不到提示词文件：%s" % a.prompt_file)
        text = open(a.prompt_file, encoding="utf-8").read().strip()
    if not text:
        sys.exit("需要 --prompt 或 --prompt-file")
    return text


def _slug(s):
    bad = '\\/:*?"<>|\n\r\t'
    s = "".join(("_" if c in bad else c) for c in s).strip().strip(".")
    return s or "符"


def _warn_long(text):
    if len(text) > 2000:
        print("⚠ 提示词 %d 字，超过 2000 字容易被拒，或者模型只记住前半段。"
              "压到 1500 字内再跑。" % len(text))


def _wait_image(api, tid, limit):
    d, t0 = {}, time.time()
    while time.time() - t0 < limit:
        d = api.task(tid)
        if d.get("state") in DONE:
            return d
        time.sleep(3)
    print("等了 %d 秒还没出完，拿 task_id 去 vidu.cn 上看：%s" % (limit, tid))
    return d


def _save_image(api, tid, dest):
    cs = api.creations(tid)
    url = next((str(c[k]) for c in cs for k in ("download_uri", "nomark_uri", "uri")
                if c.get(k)), None)
    if not url:
        print("没拿到图片地址")
        return None
    try:
        api.download(url, dest)
    except Exception as e:
        print("下载失败：%s" % e)
        return None
    return dest


# ─────────────────────── 符库 ───────────────────────
# 一张符 = 一个文件夹 + 一条索引。索引是纯 JSON，手改也行，改完别动 id。
# 默认跟着脚本走：skill 装在哪，库就在哪。有两份 skill 想共用一个库，设 VIDU_CARD_ROOT。
CARD_ROOT = os.environ.get("VIDU_CARD_ROOT") or os.path.join(ROOT, "out", "符")
LIB = os.path.join(CARD_ROOT, "_库.json")


def load_lib():
    if os.path.isfile(LIB):
        try:
            j = json.load(open(LIB, encoding="utf-8-sig"))
            if isinstance(j, dict) and isinstance(j.get("cards"), list):
                return j
        except Exception:
            print("⚠ 符库索引坏了（%s），这次先当空库用，别急着重写它" % LIB)
    return {"version": 1, "cards": []}


def save_lib(lib):
    os.makedirs(CARD_ROOT, exist_ok=True)
    lib["version"] = 1
    lib["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(LIB, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=1)


def _rel(p):
    try:
        return os.path.relpath(p, CARD_ROOT).replace("\\", "/")
    except Exception:
        return p


def _read_meta(path):
    if not path or not os.path.isfile(path):
        if path:
            print("⚠ 找不到 meta：%s，按文件夹名入库" % path)
        return {}
    try:
        j = json.load(open(path, encoding="utf-8-sig"))
        return j if isinstance(j, dict) else {}
    except Exception as e:
        print("⚠ meta 不是合法 JSON（%s），按文件夹名入库" % e)
        return {}


def _tags(v):
    """标签手写成字符串也行：「动作, 教学」或「动作、教学」都认。"""
    if isinstance(v, str):
        s = v
        for ch in (",", "，", "、", "/", "|", ";"):
            s = s.replace(ch, " ")
        v = s.split()
    return [str(t).strip() for t in (v or []) if str(t).strip()]


def _card_entry(folder, meta):
    """meta 就是符系统第一个代码块：name / type / intro / prompt。"""
    cid = _slug(os.path.basename(os.path.normpath(folder)))
    return {
        "id": cid,
        "name": (meta.get("name") or cid).strip(),
        "type": (meta.get("type") or "未分类").strip(),
        "intro": (meta.get("intro") or "").strip(),
        "call": (meta.get("prompt") or "").strip(),
        "tags": _tags(meta.get("tags")),
        "file": _rel(os.path.join(folder, "panel.png")),
        "created": time.strftime("%Y-%m-%d"),
    }


def upsert_card(entry):
    lib = load_lib()
    old = next((c for c in lib["cards"] if c.get("id") == entry["id"]), {})
    if old.get("created"):
        entry["created"] = old["created"]
    if old.get("tags") and not entry["tags"]:
        entry["tags"] = old["tags"]
    lib["cards"] = [c for c in lib["cards"] if c.get("id") != entry["id"]]
    lib["cards"].append(entry)
    lib["cards"].sort(key=lambda c: (c.get("created") or "", c.get("id") or ""), reverse=True)
    save_lib(lib)
    return len(lib["cards"])


def _clip(s, n):
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[:n - 1] + "…"


def cmd_lib(a):
    lib = load_lib()

    if a.rm:
        hit = [c for c in lib["cards"] if a.rm in (c.get("id"), c.get("name"))]
        if not hit:
            sys.exit("库里没这个符：%s" % a.rm)
        for c in hit:
            print("移出库：%s（图没删，还在 out/符/%s）"
                  % (c.get("name"), os.path.dirname(c.get("file") or "")))
        lib["cards"] = [c for c in lib["cards"] if c not in hit]
        save_lib(lib)
        print("库里现在 %d 张。" % len(lib["cards"]))
        return 0

    if a.add:
        p = os.path.abspath(a.add)
        folder = os.path.dirname(p) if os.path.isfile(p) else p
        if not os.path.isdir(folder):
            sys.exit("找不到目录：%s" % folder)
        if not os.path.isfile(os.path.join(folder, "panel.png")):
            print("⚠ 这个目录里没有 panel.png，入库了也用不了，先确认图在哪")
        mp = os.path.join(folder, "meta.json")
        meta = _read_meta(mp) if os.path.isfile(mp) else {}
        if a.tag:
            meta["tags"] = a.tag
        e = _card_entry(folder, meta)
        if e["file"].startswith(".."):
            print("⚠ 这张符不在 out/符 底下，库只记了个相对路径，换台机器就找不着了")
        n = upsert_card(e)
        print("补录：%s ｜ 库里现在 %d 张" % (e["name"], n))
        return 0

    cards = lib["cards"]
    q = (a.q or "").strip().lower()
    if q:
        cards = [c for c in cards if q in json.dumps(c, ensure_ascii=False).lower()]
    if a.tag:
        want = [t.lower() for t in a.tag]
        cards = [c for c in cards
                 if all(t in [str(x).lower() for x in (c.get("tags") or [])] for t in want)]

    if a.show:
        c = next((x for x in lib["cards"]
                  if a.show in (x.get("id"), x.get("name"))), None)
        if not c:
            sys.exit("库里没这个符：%s" % a.show)
        f = os.path.join(CARD_ROOT, c.get("file") or "")
        rel = (c.get("file") or "").replace("\\", "/")
        print("ID　　：%s" % c.get("id"))
        print("名字　：%s" % c.get("name"))
        print("类型　：%s" % c.get("type"))
        print("管什么：%s" % (c.get("intro") or "（没写）"))
        print("何时调：%s" % (c.get("call") or "（没写）"))
        print("标签　：%s" % (" / ".join(c.get("tags") or []) or "（没打标签）"))
        print("图　　：out/符/%s%s" % (rel, "" if os.path.isfile(f) else "  ⚠ 图丢了"))
        if os.path.isfile(f):
            print("　　　　%d KB" % (os.path.getsize(f) // 1024))
        print("建档　：%s" % c.get("created"))
        return 0

    if not cards:
        if lib["cards"]:
            print("没搜到。库里有 %d 张，去掉 --q / --tag 再看一遍。" % len(lib["cards"]))
        else:
            print("库里还没有符。")
            print("做一张：python scripts/vidu.py card --name 太极拳 "
                  "--prompt-file out/符/符-太极拳/prompt.txt --meta out/符/符-太极拳/meta.json")
        return 0

    print("库里 %d 张符%s" % (len(cards), "（筛过）" if (q or a.tag) else ""))
    print("")
    for c in cards:
        f = os.path.join(CARD_ROOT, c.get("file") or "")
        print("%s ｜ %s" % (c.get("id"), c.get("name")))
        print("   %s" % (c.get("intro") or "（没写简介）"))
        tag = " / ".join(c.get("tags") or [])
        note = "" if os.path.isfile(f) else "  ⚠ 图丢了"
        if tag or note:
            print("   %s%s" % (tag or "—", note))
        print("")
    print("看详情：python scripts/vidu.py lib --show <ID>")
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
    p.add_argument("--audio", action="append", default=[],
                   help="音色参考，可重复（上限 3）；顺序对应 vm1/vm2")
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
    p.add_argument("--prompt", default="")
    p.add_argument("--prompt-file", default="")
    p.add_argument("--ref", action="append", default=[], help="参考图，可重复")
    p.add_argument("--name", default="")
    p.add_argument("--out", default=os.path.join(ROOT, "out"))
    p.add_argument("--ratio", default="9:16")
    p.add_argument("--resolution", default="", help="留空用默认；文字糊了可试 2k / 4k")
    p.add_argument("--model", default=IMG_MODEL)
    p.add_argument("--wait", type=int, default=300, help="最多等多少秒")
    p.add_argument("--tail", default="full", choices=list(TAILS),
                   help="尾缀档位：full 风格化（默认）/ mid 还嫌锐 / min 真人写实 / none 不加")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_image)

    p = sub.add_parser("card", help="做一张符（16:9 能力面板）")
    p.add_argument("--prompt", default="")
    p.add_argument("--prompt-file", default="")
    p.add_argument("--name", default="", help="能力名，出图存 out/符/符-名字/panel.png")
    p.add_argument("--meta", default="", help="第一个代码块的 JSON，用来入库")
    p.add_argument("--tag", action="append", default=[], help="标签，可重复")
    p.add_argument("--ref", action="append", default=[], help="参考图，可重复")
    p.add_argument("--out", default="", help="默认 out/符/<名字>/")
    p.add_argument("--ratio", default="16:9")
    p.add_argument("--resolution", default="", help="留空用默认；文字糊了可试 2k / 4k")
    p.add_argument("--model", default=IMG_MODEL)
    p.add_argument("--wait", type=int, default=300, help="最多等多少秒")
    p.add_argument("--no-lib", action="store_true", help="生完不入库")
    p.add_argument("--tail", default="full", choices=list(TAILS),
                   help="尾缀档位：full 风格化（默认）/ mid 还嫌锐 / min 真人写实 / none 不加")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_card)

    p = sub.add_parser("lib", help="符库：列出 / 搜索 / 详情 / 补录 / 移除")
    p.add_argument("--q", default="", help="搜 id、名字、简介、标签")
    p.add_argument("--tag", action="append", default=[], help="按标签筛，可重复")
    p.add_argument("--show", default="", help="看某张符的详情（ID 或名字）")
    p.add_argument("--add", default="", help="把已有符目录补录进库")
    p.add_argument("--rm", default="", help="只从库里移除条目，不删图")
    p.set_defaults(fn=cmd_lib)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
