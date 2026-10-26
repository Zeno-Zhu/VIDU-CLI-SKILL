# -*- coding: utf-8 -*-
"""vidu.py —— Vidu 统一客户端（纯 Python，零第三方依赖）

激活码：包内带 scripts/license.py 才校验，没有就跳过。

命令
    python scripts/vidu.py check                  # 额度 + 积分 + 档位（开工第一件事）
    python scripts/vidu.py quota                  # 同上，只打数
    python scripts/vidu.py accounts               # 多账号额度
    python scripts/vidu.py submit --prompt-file G01.txt --image 人物/男主.png --duration 12
    python scripts/vidu.py batch  --jobs jobs.tsv # 作业表批量（带台账，断了能续）
    python scripts/vidu.py run    --jobs jobs_vidu.json   # 作业单批量（带门禁）
    python scripts/vidu.py status                 # 查台账进度
    python scripts/vidu.py pull   --out ./out      # 下载已完成（只认无水印）
    python scripts/vidu.py image  --prompt "…" --name 男主 --tail min
    python scripts/vidu.py card   --name 太极拳 --prompt-file …/prompt.txt
    python scripts/vidu.py lib                    # 符库：内置常用符 + 自己做的
    python scripts/vidu.py lib --show 符-常用运镜

Token 五个来源，先找到先用：
    1. 环境变量 VIDU_TOKEN / VIDU_TOKEN_1..N
    2. ~/.vidu-cli-skill/token.txt          （初始化脚本会写这里）
    3. 逐级向上的 .env 里的 VIDU_TOKEN(_N)   （有多账号时用这个）
    4. scripts/token.txt
    5. ./token.txt

★ 参数唯一口径：references/vidu-参数.md
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

# ── 参数口径（改这里一处，全包跟着变）─────────────────────────
VIDU_MAX_SECONDS = 16          # 参考生视频 1—16；图生视频 3—16
VIDU_MIN_SECONDS = 1
TARGET_LOW, TARGET_HIGH = 12, 16
MAX_IMAGES, MAX_AUDIOS, MAX_PROMPT_CHARS = 9, 3, 2000

DEFAULT_RATIO = "9:16"
DEFAULT_RESOLUTION = "1080p"
VIDEO_MODEL = "3.4"
IMG_MODELS = {"fast": "3.2_image_2_5_fast",
              "pro": "3.2_image_2_5_pro",
              "base": "3.2_image_2"}
IMG_MODEL = IMG_MODELS["pro"]

INFLIGHT = ("created", "queueing", "preparation", "scheduling", "processing")
DONE = ("success", "failed", "canceled", "error")

# ── 生图的两句固定话（正文一个字不改）───────────────────────
OPEN_LINE = ("请一字不改严格按照以下中文提示词生成图片，"
             "不要翻译、不要改写、不要添加内容：")
TAIL_FULL = "归约细节灭高频冗余，软泛焦均质简谐流"
TAIL_MID = "归约细节，灭高频冗余"
TAIL_MIN = "归约细节"
TAILS = {"full": TAIL_FULL, "mid": TAIL_MID, "min": TAIL_MIN, "none": ""}

DEFAULT_LEDGER = os.path.join(ROOT, "out", "_台账.json")


# ─────────────────────── 配置 / Token ───────────────────────
def load_dotenv():
    """从本目录往上找 .env（最多 6 级），只补未设置的键。"""
    d = ROOT
    for _ in range(6):
        p = os.path.join(d, ".env")
        if os.path.isfile(p):
            try:
                with open(p, encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
            except Exception:
                pass
            return p
        nd = os.path.dirname(d)
        if d == nd:
            break
        d = nd
    return None


load_dotenv()


def base_url():
    return (os.environ.get("VIDU_BASE_URL") or "https://service.vidu.cn").rstrip("/")


def tokens():
    """{序号: token}；0 = 未编号的单账号。"""
    out = {}
    if (os.environ.get("VIDU_TOKEN") or "").strip():
        out[0] = os.environ["VIDU_TOKEN"].strip()
    i = 1
    while (os.environ.get("VIDU_TOKEN_%d" % i) or "").strip():
        out[i] = os.environ["VIDU_TOKEN_%d" % i].strip()
        i += 1
    if out:
        return out
    # 文件兜底（先看用户目录，再看包内）
    cands = [os.path.join(HOME_DIR, "token.txt"),
             os.path.join(HERE, "token.txt"),
             os.path.join(os.getcwd(), "token.txt")]
    for p in cands:
        if os.path.isfile(p):
            v = open(p, encoding="utf-8").read().strip()
            if v:
                return {0: v}
    return {}


def need_token(account=None):
    t = tokens()
    if not t:
        print("还没配 Token。三选一：")
        print("  1) 双击 skill 目录下的「1-初始化环境.cmd」，它会带你走一遍")
        print("  2) 在本目录建 .env，写一行 VIDU_TOKEN=vda_xxx")
        print("  3) 在 %s 建 token.txt，里面写 token" % HOME_DIR)
        print("")
        print("Token 在 vidu.cn 左下角头像 → Vidu Token")
        sys.exit(2)
    if account is not None and account in t:
        return t[account]
    if 0 in t:
        return t[0]
    k = int(os.environ.get("VIDU_DEFAULT_ACCOUNT", "1"))
    return t.get(k) or t[sorted(t)[0]]


# ─────────────────────── 客户端 ───────────────────────
class Vidu:
    def __init__(self, token=None, account=None):
        self.token = token or need_token(account)
        self.h = {"Authorization": "Token " + self.token,
                  "Content-Type": "application/json",
                  "User-Agent": "vidu-unified-cli/2.0"}

    def req(self, method, path, payload=None, timeout=180):
        data = json.dumps(payload).encode() if payload is not None else None
        url = path if path.startswith("http") else base_url() + path
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
        total, used = nq.get("total") or 0, nq.get("used") or 0
        _, me = self.jget("/credit/v1/credits/me")
        return {"total": total, "used": used,
                "left": max(0, total - used) if total else 0,
                "credits": me.get("credits"),
                "concurrency": me.get("concurrency")}

    def history(self, pagesz=100, pages=1, types=None):
        """最新优先。★ offset = pagesz × page，page=0 才是第一页（2026-10-24 实测）。"""
        seen, out = set(), []
        for pg in range(0, max(1, pages)):
            q = "/vidu/v1/tasks/history/me?pager.pagesz=%d&pager.page=%d" % (min(pagesz, 100), pg)
            if types:
                q += "&types=" + types
            _, j = self.jget(q)
            ts = j.get("tasks") or []
            for t in ts:
                tid = str(t.get("id"))
                if tid not in seen:
                    seen.add(tid)
                    out.append(t)
            if len(ts) < pagesz:
                break
        return out

    def inflight(self):
        return [t for t in self.history(100, 2) if t.get("state") in INFLIGHT]

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
        if not os.path.isfile(path):
            raise RuntimeError("找不到素材：%s" % path)
        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if kind == "audio":
            d = self._probe(path, "format=duration")
            try:
                secs = max(1, int(math.ceil(float(d))))
            except (TypeError, ValueError):
                secs = 1
            meta = {"duration": str(secs)}          # ★ 字段名必须是 duration
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
def _path_of(x):
    return x.get("path") if isinstance(x, dict) else x


def _name_of(x, default=""):
    if isinstance(x, dict):
        return (x.get("name") or os.path.basename(_path_of(x) or "")).strip() or default
    return os.path.basename(x or "") or default


def _up(api, path, cache, kind="image", fresh=False):
    if not path or not os.path.isfile(path):
        raise RuntimeError("素材不存在：%s" % path)
    st = os.stat(path)
    k = "%s|%d|%d|%s" % (os.path.abspath(path), st.st_size, int(st.st_mtime), kind)
    if fresh or k not in cache:
        cache[k] = api.upload(path, kind=kind)
    return cache[k]


def build_video_payload(job, api, mode, cache):
    dur = int(job.get("duration") or 0)
    if not (VIDU_MIN_SECONDS <= dur <= VIDU_MAX_SECONDS):
        raise RuntimeError("时长 %s 超界（参考生视频 %d—%d 秒）"
                           % (dur, VIDU_MIN_SECONDS, VIDU_MAX_SECONDS))
    imgs = job.get("images") or []
    auds = job.get("audios") or []
    # ★ 2026-10-26 实测：闲时（nopeak）无法参考音色 —— 在提交前就拦，别等排完队才发现没生效
    #   ⚠ 拦的是「参考音色」，不是「配音」：台词照样会被平台原生配音念出来，别顺手把台词删了
    if auds and mode == "nopeak":
        raise RuntimeError(
            "闲时（nopeak）无法参考音色：本组登记了 %d 条音色（%s）。"
            "二选一：① 删掉 audios，把声线写进【音色文字锁定】（锚点串抄自 音色-<角色名>.txt）；"
            "② 确需参考音色就改 --mode normal（花积分）。"
            "⚠ 只是不能指定声线，台词仍会由平台原生配音念出来，不要把台词删掉。"
            % (len(auds), "、".join(str(_name_of(x) or _path_of(x) or "?") for x in auds)))
    if len(imgs) > MAX_IMAGES:
        raise RuntimeError("图片 %d 张 > %d 上限" % (len(imgs), MAX_IMAGES))
    if len(auds) > MAX_AUDIOS:
        print("⚠ 音色 %d 条超过上限 %d，只取前 %d 条" % (len(auds), MAX_AUDIOS, MAX_AUDIOS))
        auds = auds[:MAX_AUDIOS]

    settings = {
        "duration": dur,
        "model_version": job.get("model_version") or VIDEO_MODEL,
        "resolution": job.get("resolution") or DEFAULT_RESOLUTION,
        "aspect_ratio": job.get("ratio") or DEFAULT_RATIO,
        "sample_count": int(job.get("count") or 1),
        "schedule_mode": mode,
        "codec": "h265",
        "movement_amplitude": "auto",
        "use_trial": False,
    }
    prompts = [{"type": "text", "content": job["prompt"]}]
    for img in imgs:
        prompts.append({"type": "image", "content": _up(api, _path_of(img), cache, "image")})
    for au in auds:
        p = _path_of(au)
        prompts.append({"type": "audio", "content": _up(api, p, cache, "audio"),
                        "name": _name_of(au) or os.path.basename(p)})
    return {"type": job.get("type") or "character2video",
            "input": {"prompts": prompts, "editor_mode": "normal", "enhance": True},
            "settings": settings}


def build_image_payload(job, api, mode, cache):
    """无 ref ⇒ text2image；有 ref ⇒ reference2image。

    ★ r2i 的每张参考图要**上传两次**：`content`（裁剪图）+ `src_imgs[0]`（原图），
      两个必须是**不同的 upload id**（复用同一个会丢参考）。
    """
    refs = job.get("refs") or []
    mv = IMG_MODELS.get(job.get("model") or "pro", job.get("model") or IMG_MODEL)
    settings = {
        "duration": 0,
        "resolution": job.get("resolution") or DEFAULT_RESOLUTION,
        "aspect_ratio": job.get("ratio") or "16:9",
        "sample_count": int(job.get("count") or 1),
        "movement_amplitude": "auto",
        "schedule_mode": mode,
        "model_version": mv,
        "use_trial": True,
        "image_count": max(1, len(refs)),
        "codec": "h265",
    }
    prompts = [{"type": "text", "content": job["prompt"]}]
    for i, p in enumerate(refs, 1):
        a = _up(api, p, cache, "image")
        b = api.upload(p, "image")            # ★ 不复用缓存，必须另一个 id
        w, h = _wh(p)
        prompts.append({"type": "image", "content": a, "src_imgs": [b],
                        "selected_region": {"top_left": {"x": 0, "y": 0},
                                            "bottom_right": {"x": w, "y": h}},
                        "name": "图%d" % i})
    return {"type": "reference2image" if refs else "text2image",
            "input": {"prompts": prompts, "editor_mode": "normal", "enhance": True},
            "settings": settings}


def _wh(path):
    o = Vidu._probe(path, "stream=width,height").replace(",", "x").split("x")
    try:
        return int(o[0]), int(o[1])
    except Exception:
        return 1024, 1024


def quote_image(api, payload):
    s = payload["settings"]
    q = ("/vidu/v1/tasks/credits?type=%s&settings.duration=0&settings.resolution=%s"
         "&settings.aspect_ratio=%s&settings.model_version=%s&settings.schedule_mode=%s"
         "&settings.sample_count=%d&settings.image_count=%d"
         % (payload["type"], s["resolution"], s["aspect_ratio"], s["model_version"],
            s["schedule_mode"], s["sample_count"], s["image_count"]))
    c, j = api.jget(q)
    return j if isinstance(j, dict) else {}


# ─────────────────────── 台账 ───────────────────────
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


def pick_url(c, allow_watermark=False):
    """★ 只认无水印：download_uri / nomark_uri。只有 uri = 中间态，继续等。"""
    for k in ("download_uri", "nomark_uri"):
        if c.get(k):
            return str(c[k])
    if allow_watermark and c.get("uri"):
        print("⚠ 显式允许水印版：这张/这段会带「Vidu AI 生成」角标")
        return str(c["uri"])
    return None


# ─────────────────────── 命令：查 ───────────────────────
def cmd_check(a):
    api = Vidu(account=a.account)
    q = api.quota()
    total = q["total"]
    if not total:
        tier = "查不到闲时额度"
    elif total >= 100:
        tier = "旗舰版（200 条/天）"
    elif total <= 30:
        tier = "专业版（20 条/天）"
    else:
        tier = "自定义额度（%d 条/天）" % total
    print("账号版本：%s" % tier)
    print("闲时额度：%d/%d（今天还能跑 %d 条）" % (q["used"], total, q["left"]))
    print("积分余额：%s" % q["credits"])
    print("进行中任务：%d 条（并发上限 100）" % len(api.inflight()))
    print("")
    print("单组时长 1—16 秒（目标 12—16）；默认只走闲时，不扣积分。")
    return 0


def cmd_quota(a):
    api = Vidu(account=a.account)
    q = api.quota()
    print("闲时 %d/%d（余 %d）｜积分 %s｜进行中 %d"
          % (q["used"], q["total"], q["left"], q["credits"], len(api.inflight())))
    return 0


def cmd_accounts(a):
    t = tokens()
    if not t:
        print("未配置任何账号")
        return 1
    for n in sorted(t):
        try:
            q = Vidu(token=t[n]).quota()
            print("账号%-2s 闲时 %d/%d（余 %d）  积分 %s"
                  % (n or "-", q["used"], q["total"], q["left"], q["credits"]))
        except Exception as e:
            print("账号%-2s ✗ %s" % (n or "-", e))
    return 0


def gate(api, need, quiet=False):
    """提交前的额度门禁：不够就停（不是等）。"""
    q = api.quota()
    left = q["left"]
    if q["total"] and left < need:
        print("=" * 66)
        print(" ⛔ 闲时额度不足 —— 已停止作业（不硬跑到平台报错，也不空转等待）")
        print("=" * 66)
        print(" 今日闲时：%d / %d（剩余 %d）" % (q["used"], q["total"], left))
        print(" 本次需要：%d" % need)
        print("")
        print(" ⇒ 二选一：")
        print("   A. 换账号：改 .env 里的 VIDU_DEFAULT_ACCOUNT，或加 --account N")
        print("   B. 等明天：额度 0 点重置，明早重跑同一条命令，已完成的组会自动跳过")
        print("=" * 66)
        return False
    if not quiet:
        print("闲时额度：%d/%d，剩余 %d ≥ 本次 %d ⇒ 放行" % (q["used"], q["total"], left, need))
    return True


# ─────────────────────── 命令：提交 ───────────────────────
def cmd_submit(a):
    text = (a.prompt or "").strip()
    if not text and a.prompt_file:
        if not os.path.isfile(a.prompt_file):
            sys.exit("找不到提示词文件：%s" % a.prompt_file)
        text = open(a.prompt_file, encoding="utf-8").read().strip()
    if not text:
        sys.exit("需要 --prompt 或 --prompt-file")
    if len(text) > MAX_PROMPT_CHARS:
        print("⚠ 提示词 %d 字，超过 %d 上限，容易被拒或只记住前半段" % (len(text), MAX_PROMPT_CHARS))

    job = {"id": a.name or "single", "prompt": text,
           "duration": a.duration, "ratio": a.ratio,
           "images": a.image, "audios": a.audio,
           "type": a.type, "model_version": a.model or VIDEO_MODEL,
           "resolution": a.resolution, "count": a.count}
    api = Vidu(account=a.account)
    if a.dry_run:
        print("[dry] %s %ss 图%d 音%d 模式%s 比例%s"
              % (job["type"], a.duration, len(a.image), len(a.audio), a.mode, a.ratio))
        for au in a.audio:
            print("      音色参考：%s" % os.path.basename(au))
        print(text[:160].replace("\n", " "))
        return 0
    try:
        payload = build_video_payload(job, api, a.mode, {})
    except RuntimeError as e:
        print("提交失败：%s" % e)
        return 1
    try:
        r = api.submit(payload)
    except RuntimeError as e:
        print("提交失败：%s" % e)
        print("常见原因：时长超界 / 没给图 / 提示词太长 / 音色超 3 条 / 开了 lip_sync 又用闲时")
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
    """作业表：组号 / 提示词文件 / 图片(逗号) / 时长 / 音色(逗号，可选)"""
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
            print("⚠ 第 %d 行缺组号或提示词文件，跳过" % ln)
            continue
        rows.append({"id": sid, "prompt_file": pfile,
                     "images": [x.strip() for x in imgs.split(",") if x.strip()],
                     "audios": [x.strip() for x in auds.split(",") if x.strip()],
                     "duration": int(dur or a.duration)})
    led = load_ledger(a.ledger)
    todo = [r for r in rows if a.force or r["id"] not in led]
    print("共 %d 条，待提交 %d 条" % (len(rows), len(todo)))
    if not todo:
        print("都提交过了，用 status 看进度")
        return 0

    api = Vidu(account=a.account)
    if len(todo) > 100:
        print("⚠ 同时最多 100 条在跑，本次 %d 条；建议先交 100 条，跑完一批再补" % len(todo))
        if not a.force:
            return 1
    if a.dry_run:
        for r in todo:
            print("[dry] %s %ss 图%d 音%d" % (r["id"], r["duration"],
                                              len(r["images"]), len(r["audios"])))
        return 0
    if not gate(api, len(todo)):
        return 2

    cache, ok, fail = {}, 0, 0
    for r in todo:
        if not os.path.isfile(r["prompt_file"]):
            print("[%s] ✗ 找不到 %s" % (r["id"], r["prompt_file"]))
            fail += 1
            continue
        job = {"id": r["id"],
               "prompt": open(r["prompt_file"], encoding="utf-8").read(),
               "duration": r["duration"], "ratio": a.ratio,
               "images": r["images"], "audios": r["audios"], "type": a.type}
        try:
            res = api.submit(build_video_payload(job, api, a.mode, cache))
            tid = str(res.get("id"))
            led[r["id"]] = {"task_id": tid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                            "duration": job["duration"]}
            save_ledger(a.ledger, led)
            ok += 1
            print("[%s] → %s" % (r["id"], tid), flush=True)
        except Exception as e:
            fail += 1
            print("[%s] ✗ %s" % (r["id"], e), flush=True)
        time.sleep(a.pause)
    print("")
    print("提交成功 %d ｜ 失败 %d" % (ok, fail))
    if ok:
        print("接着跑：python scripts/vidu.py status")
    return 0 if not fail else 1


def cmd_run(a):
    """作业单 jobs_vidu.json（批量格式）。带台账、带门禁、可续跑。"""
    if not os.path.isfile(a.jobs):
        sys.exit("找不到作业单：%s" % a.jobs)
    d = json.load(open(a.jobs, encoding="utf-8"))
    jobs = d.get("jobs") if isinstance(d, dict) else d
    if a.job:
        jobs = [j for j in jobs if a.job in (j.get("id"), j.get("src_id"))]
    led = load_ledger(a.ledger)
    for j in jobs:
        if j.get("task_id") and j.get("id") not in led:
            led[j["id"]] = {"task_id": str(j["task_id"]), "at": j.get("at") or ""}
    todo = jobs if a.force else [j for j in jobs if j.get("id") not in led]
    if a.limit:
        todo = todo[:a.limit]
    print("作业单 %d 组 ｜ 已有台账 %d 组 ｜ 待提交 %d 组"
          % (len(jobs), len(jobs) - len([j for j in jobs if j.get("id") not in led]), len(todo)))
    if not todo:
        print("都提交过了，用 status / pull 收片")
        return 0
    api = Vidu(account=a.account)
    if a.dry_run:
        for j in todo:
            print("[dry] %-22s %ss %s 图%d 音%d %s"
                  % (j.get("id"), j.get("duration"), j.get("ratio") or DEFAULT_RATIO,
                     len(j.get("images") or []), len(j.get("audios") or []), a.mode))
        return 0
    if not gate(api, len(todo)):
        return 2

    cache, ok, fail = {}, [], []
    for j in todo:
        jid = j.get("id")
        try:
            payload = build_video_payload(j, api, a.mode, cache)
            r = api.submit(payload)
            tid = str(r.get("id"))
            ok.append((jid, tid))
            led[jid] = {"task_id": tid, "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                        "duration": j.get("duration")}
            save_ledger(a.ledger, led)
            print("%-22s → %s" % (jid, tid), flush=True)
        except Exception as e:
            fail.append((jid, str(e)))
            print("%-22s ✗ %s" % (jid, e), flush=True)
        time.sleep(a.pause)
    print("\n提交成功 %d｜失败 %d" % (len(ok), len(fail)))
    for jid, e in fail:
        print("  失败 %s：%s" % (jid, e))
    return 0 if not fail else 1


def cmd_status(a):
    api = Vidu(account=a.account)
    led = load_ledger(a.ledger)
    if a.jobs and os.path.isfile(a.jobs):
        d = json.load(open(a.jobs, encoding="utf-8"))
        for j in (d.get("jobs") if isinstance(d, dict) else d):
            if j.get("task_id"):
                led.setdefault(j.get("id"), {"task_id": str(j["task_id"])})
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
        print("%-16s %s%s" % (sid, st, extra))
    print("")
    print("汇总：" + " ｜ ".join("%s %d" % (k, v) for k, v in sorted(stat.items())))
    return 0


def cmd_pull(a):
    api = Vidu(account=a.account)
    led = load_ledger(a.ledger)
    if a.jobs and os.path.isfile(a.jobs):
        d = json.load(open(a.jobs, encoding="utf-8"))
        for j in (d.get("jobs") if isinstance(d, dict) else d):
            if j.get("task_id"):
                led.setdefault(j.get("id"), {"task_id": str(j["task_id"])})
    if not led:
        sys.exit("台账是空的：%s" % a.ledger)
    os.makedirs(a.out, exist_ok=True)
    got = 0
    for sid, rec in led.items():
        dst = os.path.join(a.out, "%s%s.mp4" % (sid, a.suffix))
        if os.path.isfile(dst) and os.path.getsize(dst) > 1024:
            continue
        d = api.task(rec["task_id"])
        if d.get("state") != "success":
            continue
        try:
            cs = api.creations(rec["task_id"])
            total, n = len(cs), 0
            for i, c in enumerate(cs):
                url = pick_url(c, a.allow_watermark)
                if not url:
                    continue
                one = dst if total == 1 else os.path.join(
                    a.out, "%s%s_%d.mp4" % (sid, a.suffix, i + 1))
                api.download(url, one)
                n += 1
            if not n:
                print("[%s] success 但还没有无水印地址（中间态）⇒ 稍后重跑同一条命令" % sid)
                continue
            got += n
            print("[%s] ✓ %.1f MB" % (sid, os.path.getsize(dst) / 1048576), flush=True)
        except Exception as e:
            print("[%s] ✗ %s" % (sid, e))
    print("")
    print("新下载 %d 个，目录 %s" % (got, a.out))
    return 0


# ─────────────────────── 命令：生图 ───────────────────────
def _wrap(text, tail="min"):
    text = (text or "").strip()
    if not text:
        return text
    if not text.startswith(OPEN_LINE):
        text = OPEN_LINE + "\n\n" + text
    t = TAILS.get(tail, TAIL_MIN)
    if t and not text.rstrip().endswith(t):
        text = text.rstrip() + "\n\n" + t
    return text


def _tail_label(tail):
    return TAILS.get(tail, TAIL_MIN) or "无"


def _read_items(a):
    items = []
    if (getattr(a, "prompt", "") or "").strip():
        items.append(((a.name or "").strip(), a.prompt.strip()))
    if getattr(a, "prompt_file", ""):
        if not os.path.isfile(a.prompt_file):
            sys.exit("找不到提示词文件：%s" % a.prompt_file)
        for line in open(a.prompt_file, encoding="utf-8"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "||" in line:
                t, body = line.split("||", 1)
                items.append((t.strip(), body.strip()))
            else:
                items.append(("", line))
    if not items:
        sys.exit("需要 --prompt 或 --prompt-file")
    return items


def _safe(s, n=60):
    s = "".join(ch for ch in (s or "image") if ch not in '\\/:*?"<>|\r\n\t').strip()
    return (s[:n] or "image").strip(".")


def cmd_image(a):
    api = Vidu(account=a.account)
    items = _read_items(a)
    mode = a.mode
    if a.ref and mode == "nopeak":
        print("⚠ 参考图生图不支持闲时（平台 403）⇒ 本条强制走 normal（花积分）")
        mode = "normal"
    os.makedirs(a.out, exist_ok=True)
    cache, ok, fail = {}, 0, 0
    for idx, (nm, text) in enumerate(items, 1):
        wrapped = _wrap(text, a.tail)
        if len(wrapped) > MAX_PROMPT_CHARS:
            print("⚠ 提示词 %d 字，超过 %d 易被拒；压到 1500 内更稳"
                  % (len(wrapped), MAX_PROMPT_CHARS))
        job = {"prompt": wrapped, "refs": a.ref, "model": a.model, "ratio": a.ratio,
               "resolution": a.resolution, "count": a.count}
        try:
            payload = build_image_payload(job, api, mode, cache)
        except Exception as e:
            print("[%d/%d] ✗ 组装失败：%s" % (idx, len(items), e))
            fail += 1
            continue
        q = quote_image(api, payload)
        cost, left = q.get("cost_credits"), q.get("current_credits")
        tag = "%s/%s" % (payload["type"], payload["settings"]["model_version"])
        if a.dry_run:
            print("[dry] %-16s %-24s %s 积分（余额 %s）｜%s 字"
                  % (nm or "image", tag, cost, left, len(wrapped)))
            continue
        print("[%d/%d] %-16s %-24s 预计 %s 积分（余额 %s）"
              % (idx, len(items), nm or "image", tag, cost, left), flush=True)
        try:
            r = api.submit(payload)
        except Exception as e:
            print("      ✗ 提交失败：%s" % e)
            fail += 1
            continue
        tid = str(r.get("id"))
        print("      task_id = %s" % tid, flush=True)
        st, waited = "created", 0
        while waited < a.timeout:
            st = (api.task(tid) or {}).get("state") or st
            if st in DONE:
                break
            time.sleep(a.interval)
            waited += a.interval
        if st != "success":
            print("      ✗ %s（%s）" % (st, (api.task(tid) or {}).get("err_code") or ""))
            fail += 1
            continue
        cs = api.creations(tid)
        got = 0
        for i, c in enumerate(cs):
            url = pick_url(c, a.allow_watermark)
            if not url:
                continue
            base = _safe(nm or text)
            name = base + (".png" if len(cs) == 1 else "_%d.png" % (i + 1))
            dest = os.path.join(a.out, name)
            api.download(url, dest)
            got += 1
            print("      ✅ %s（%.1f MB）" % (dest, os.path.getsize(dest) / 1048576))
        if got:
            ok += 1
        else:
            print("      ⚠ success 但拿不到无水印地址（中间态）⇒ 稍后重跑同一命令即可")
            fail += 1
    if a.dry_run:
        print("\n[dry] 共 %d 条，未提交" % len(items))
        return 0
    print("\n出图成功 %d｜失败 %d" % (ok, fail))
    return 0 if not fail else 1


# ─────────────────────── 命令：符（做 / 库）───────────────────────
BUILTIN_CARD_ROOT = os.path.join(ROOT, "assets", "常用符")
USER_CARD_ROOT = os.path.join(ROOT, "out", "符")


def card_roots():
    roots = []
    env = os.environ.get("VIDU_CARD_ROOT")
    if env:
        roots.append(env)
    for r in (BUILTIN_CARD_ROOT, USER_CARD_ROOT):
        if os.path.isdir(r) and r not in roots:
            roots.append(r)
    return roots


def _card_index(root):
    p = os.path.join(root, "_库.json")
    if os.path.isfile(p):
        try:
            j = json.load(open(p, encoding="utf-8-sig"))
            if isinstance(j, dict) and isinstance(j.get("cards"), list):
                return j
        except Exception:
            print("⚠ 符库索引坏了（%s），这次当空库用" % p)
    return {"version": 1, "cards": []}


def save_card_index(root, lib):
    os.makedirs(root, exist_ok=True)
    lib["version"] = 1
    lib["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with open(os.path.join(root, "_库.json"), "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=1)


def all_cards():
    """内置常用符 + 用户自建，一起返回（带 _root / _builtin）。"""
    out = []
    for root in card_roots():
        lib = _card_index(root)
        builtin = os.path.abspath(root) == os.path.abspath(BUILTIN_CARD_ROOT)
        for c in lib.get("cards") or []:
            c = dict(c)
            c["_root"] = root
            c["_builtin"] = builtin
            out.append(c)
    return out


def _tags(v):
    if isinstance(v, str):
        s = v
        for ch in (",", "，", "、", "/", "|", ";"):
            s = s.replace(ch, " ")
        v = s.split()
    return [str(t).strip() for t in (v or []) if str(t).strip()]


def _strs(v):
    """字符串列表原样保留，不像 _tags 那样按标点拆开（锁/禁都是整句）。"""
    if isinstance(v, str):
        return [v.strip()] if v.strip() else []
    return [str(x).strip() for x in (v or []) if str(x).strip()]


def _read_meta(path):
    if not path or not os.path.isfile(path):
        if path:
            print("⚠ 找不到 meta：%s，按文件夹名入库" % path)
        return {}
    try:
        j = json.load(open(path, encoding="utf-8-sig"))
        return j if isinstance(j, dict) else {}
    except Exception as e:
        print("⚠ meta 不是合法 JSON（%s）" % e)
        return {}


def _card_entry(folder, meta):
    cid = _safe(os.path.basename(os.path.normpath(folder)), 60)
    return {
        "id": cid,
        "name": (meta.get("name") or cid).strip(),
        "type": (meta.get("type") or "未分类").strip(),
        "intro": (meta.get("intro") or "").strip(),
        "call": (meta.get("prompt") or "").strip(),
        "tags": _tags(meta.get("tags")),
        "status": (meta.get("status") or "候选").strip(),
        "parent": (meta.get("parent") or "").strip(),
        "file": os.path.relpath(os.path.join(folder, "panel.png"), USER_CARD_ROOT).replace("\\", "/"),
        "created": meta.get("created") or time.strftime("%Y-%m-%d"),
        # ── 参数卡字段（有就带，没有不影响老符）──
        "chain": (meta.get("chain") or "").strip(),
        "locks": _strs(meta.get("locks")),
        "variables": _strs(meta.get("variables")),
        "negatives": _strs(meta.get("negatives")),
        "defer": _strs(meta.get("defer")),
        "grade": (meta.get("grade") or "").strip(),
        "grade_basis": (meta.get("grade_basis") or "").strip(),
        "score_total": (sum(v for v in (meta.get("score") or {}).values()
                            if isinstance(v, (int, float)))
                        if isinstance(meta.get("score"), dict) else 0),
    }


def cmd_card(a):
    """做一张符：16:9 能力面板。存 out/符/符-<名字>/，出完自动入库。"""
    items = _read_items(a)
    _, text = items[0]
    wrapped = _wrap(text, a.tail)
    raw = (a.name or "").strip() or time.strftime("符-%m%d-%H%M")
    name = _safe(raw, 60)
    if not name.startswith("符"):
        name = "符-" + name
    out = a.out or os.path.join(USER_CARD_ROOT, name)

    if a.dry_run:
        print("[dry] %s ｜ %d 字 ｜ 尾缀：%s ｜ → %s"
              % (a.ratio, len(wrapped), _tail_label(a.tail), os.path.join(out, "panel.png")))
        print(wrapped[:160].replace("\n", " "))
        return 0
    os.makedirs(out, exist_ok=True)
    api = Vidu(account=a.account)
    job = {"prompt": wrapped, "refs": a.ref, "model": a.model, "ratio": a.ratio,
           "resolution": a.resolution, "count": 1}
    payload = build_image_payload(job, api, "normal", {})
    q = quote_image(api, payload)
    print("预计 %s 积分（余额 %s）" % (q.get("cost_credits"), q.get("current_credits")))
    open(os.path.join(out, "prompt.txt"), "w", encoding="utf-8").write(wrapped)

    r = api.submit(payload)
    tid = str(r.get("id"))
    print("生图任务 %s，等它出…（尾缀：%s）" % (tid, _tail_label(a.tail)))
    st, waited = "created", 0
    while waited < a.wait:
        st = (api.task(tid) or {}).get("state") or st
        if st in DONE:
            break
        time.sleep(3)
        waited += 3
    if st != "success":
        print("失败：%s %s" % ((api.task(tid) or {}).get("err_code"),
                              (api.task(tid) or {}).get("err_msg")))
        return 1
    dest = os.path.join(out, "panel.png")
    url = None
    for c in api.creations(tid):
        url = pick_url(c, a.allow_watermark)
        if url:
            break
    if not url:
        print("success 但还没有无水印地址（中间态）⇒ 稍后重跑同一条命令")
        return 1
    api.download(url, dest)
    print("符出好了：%s（%d KB）" % (dest, os.path.getsize(dest) // 1024))
    print("错字就改 %s 再跑一遍，别重画整段。" % os.path.join(out, "prompt.txt"))

    if not a.no_lib:
        mp = a.meta or os.path.join(out, "meta.json")
        meta = dict(_read_meta(mp)) if os.path.isfile(mp) else {}
        meta["tail"] = _tail_label(a.tail)
        if a.tag:
            meta["tags"] = a.tag
        json.dump(meta, open(os.path.join(out, "meta.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        root = USER_CARD_ROOT
        lib = _card_index(root)
        e = _card_entry(out, meta)
        old = next((c for c in lib["cards"] if c.get("id") == e["id"]), {})
        if old.get("created"):
            e["created"] = old["created"]
        if old.get("tags") and not e["tags"]:
            e["tags"] = old["tags"]
        lib["cards"] = [c for c in lib["cards"] if c.get("id") != e["id"]] + [e]
        save_card_index(root, lib)
        print("入库：%s ｜ 状态 %s ｜ 库里现在 %d 张"
              % (e["name"], e["status"], len(lib["cards"])))
        if e["status"] == "候选":
            print("   现在是候选。用户点头后把 meta.json 的 status 改成「定稿」，再 lib --add 一次。")
        if not meta:
            print("   ⚠ 没给 --meta，这张符在库里只有名字。补一个：lib --add %s" % out)
    return 0


def cmd_lib(a):
    cards = all_cards()

    if a.rm:
        root = USER_CARD_ROOT
        lib = _card_index(root)
        hit = [c for c in lib["cards"] if a.rm in (c.get("id"), c.get("name"))]
        if not hit:
            sys.exit("库里没这个符（内置符不可移除）：%s" % a.rm)
        for c in hit:
            print("移出库：%s（图没删）" % c.get("name"))
        lib["cards"] = [c for c in lib["cards"] if c not in hit]
        save_card_index(root, lib)
        print("库里现在 %d 张（不含内置）。" % len(lib["cards"]))
        return 0

    if a.add:
        p = os.path.abspath(a.add)
        folder = os.path.dirname(p) if os.path.isfile(p) else p
        if not os.path.isdir(folder):
            sys.exit("找不到目录：%s" % folder)
        if not os.path.isfile(os.path.join(folder, "panel.png")):
            print("⚠ 这个目录里没有 panel.png，入库了也用不了")
        meta = _read_meta(os.path.join(folder, "meta.json"))
        if a.tag:
            meta["tags"] = a.tag
        e = _card_entry(folder, meta)
        if os.path.abspath(folder) != os.path.abspath(BUILTIN_CARD_ROOT) and \
                not os.path.abspath(folder).startswith(os.path.abspath(USER_CARD_ROOT)):
            print("⚠ 这张符不在 out/符 底下，库只记相对路径，换机器会找不到")
        root = USER_CARD_ROOT
        lib = _card_index(root)
        lib["cards"] = [c for c in lib["cards"] if c.get("id") != e["id"]] + [e]
        save_card_index(root, lib)
        print("补录：%s ｜ 库里现在 %d 张" % (e["name"], len(lib["cards"])))
        return 0

    if not cards:
        print("库里还没有符。")
        print("  · 内置库在 assets/常用符/（随包附带时这里有东西）；")
        print("  · 自己做一张：python scripts/vidu.py card --name 太极拳 --prompt-file …/prompt.txt")
        return 0

    q = (a.q or "").strip().lower()
    if q:
        cards = [c for c in cards if q in json.dumps(c, ensure_ascii=False).lower()]
    if a.tag:
        want = [t.lower() for t in a.tag]
        cards = [c for c in cards
                 if all(t in [str(x).lower() for x in (c.get("tags") or [])] for t in want)]
    if a.status:
        cards = [c for c in cards if (c.get("status") or "候选") == a.status]
    if getattr(a, "grade", ""):
        cards = [c for c in cards if (c.get("grade") or "").startswith(a.grade)]

    if a.show:
        c = next((x for x in all_cards() if a.show in (x.get("id"), x.get("name"))), None)
        if not c:
            sys.exit("库里没这个符：%s" % a.show)
        print("ID　　：%s" % c.get("id"))
        print("名字　：%s" % c.get("name"))
        print("类型　：%s" % c.get("type"))
        print("管什么：%s" % (c.get("intro") or "（没写）"))
        print("何时调：%s" % (c.get("call") or "（没写）"))
        print("状态　：%s%s" % (c.get("status") or "候选", " ［内置］" if c.get("_builtin") else ""))
        print("父系　：%s" % (c.get("parent") or "（无）"))
        print("称号　：%s" % {"main": "主符（可直接当主符）",
                              "aux": "辅符（给主符打补丁）"}.get(c.get("chain"), "（未标）"))
        grade = c.get("grade") or ""
        if grade:
            print("评级　：%s  %d/100 ｜ %s" % (grade, c.get("score_total") or 0,
                                            c.get("grade_basis") or "设计评级"))
        else:
            print("评级　：（未评）")
        for k, label in (("locks", "锁（不可改）"), ("variables", "变（必须给）"),
                         ("negatives", "禁（本符专属）"), ("defer", "让（交给下游）")):
            v = c.get(k) or []
            print("%-6s：%s" % (label, ("；".join(v) if v else "（未填）")))
        print("标签　：%s" % (" / ".join(c.get("tags") or []) or "（没打标签）"))
        f = os.path.join(c["_root"], c.get("file") or "")
        print("图　　：%s%s" % (f, "" if os.path.isfile(f) else "  ⚠ 图丢了"))
        return 0

    print("库里 %d 张符（内置 %d ｜ 自建 %d）"
          % (len(cards), len([c for c in cards if c.get("_builtin")]),
             len([c for c in cards if not c.get("_builtin")])))
    print("")
    for c in cards:
        f = os.path.join(c["_root"], c.get("file") or "")
        mark = "［内置］" if c.get("_builtin") else ""
        print("%s ｜ %s ［%s］%s%s" % (c.get("id"), c.get("name"),
                                       c.get("status") or "候选", mark,
                                       ("  " + c["grade"]) if c.get("grade") else ""))
        print("   %s" % (c.get("intro") or "（没写简介）"))
        print("   何时调：%s" % (c.get("call") or "（没写）"))
        if not os.path.isfile(f):
            print("   ⚠ 图丢了：%s" % f)
        print("")
    print("看详情：lib --show <ID>")
    return 0


# ─────────────────────── main ───────────────────────
def main():
    # 激活码：包内有 license.py 才校验，没有就跳过
    try:
        from license import ensure_activated  # type: ignore
    except Exception:
        ensure_activated = None
    if ensure_activated and not ensure_activated():
        return 3

    ap = argparse.ArgumentParser(description="Vidu 统一客户端（提交/查询/下载/生图/做符/符库）")
    ap.add_argument("--account", type=int, default=None, help="用哪个账号（.env 的 VIDU_TOKEN_N）")
    ap.add_argument("--ledger", default=DEFAULT_LEDGER, help="台账路径")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="额度 + 积分 + 档位").set_defaults(fn=cmd_check)
    sub.add_parser("quota", help="只打额度数字").set_defaults(fn=cmd_quota)
    sub.add_parser("accounts", help="多账号额度").set_defaults(fn=cmd_accounts)

    p = sub.add_parser("submit", help="提交一条")
    p.add_argument("--prompt", default="")
    p.add_argument("--prompt-file", default="")
    p.add_argument("--image", action="append", default=[], help="可重复，顺序对应 pn1/pn2…")
    p.add_argument("--audio", action="append", default=[], help="音色参考，可重复（≤3），对应 vm1…")
    p.add_argument("--duration", type=int, default=12, help="1—16 整数秒，目标 12—16")
    p.add_argument("--ratio", default=DEFAULT_RATIO)
    p.add_argument("--resolution", default=DEFAULT_RESOLUTION)
    p.add_argument("--type", default="character2video", choices=["character2video", "img2video"])
    p.add_argument("--mode", choices=["nopeak", "normal"], default="nopeak")
    p.add_argument("--model", default="", help="一般不用填（默认 3.4）")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--name", default="")
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_submit)

    p = sub.add_parser("batch", help="作业表批量（TSV，五列）")
    p.add_argument("--jobs", required=True)
    p.add_argument("--ratio", default=DEFAULT_RATIO)
    p.add_argument("--resolution", default=DEFAULT_RESOLUTION)
    p.add_argument("--type", default="character2video")
    p.add_argument("--mode", choices=["nopeak", "normal"], default="nopeak")
    p.add_argument("--duration", type=int, default=12)
    p.add_argument("--pause", type=float, default=1.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true", help="已提交过的也重交")
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.set_defaults(fn=cmd_batch)

    p = sub.add_parser("run", help="作业单批量（jobs_vidu.json）")
    p.add_argument("--jobs", required=True)
    p.add_argument("--job", default="", help="只跑某一组")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--mode", choices=["nopeak", "normal"], default="nopeak")
    p.add_argument("--pause", type=float, default=1.0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.set_defaults(fn=cmd_run)

    p = sub.add_parser("status", help="查台账进度")
    p.add_argument("--jobs", default="")
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser("pull", help="下载已完成（只认无水印）")
    p.add_argument("--out", default=os.path.join(ROOT, "out"))
    p.add_argument("--jobs", default="")
    p.add_argument("--suffix", default="", help="落盘后缀，例如 _vidu")
    p.add_argument("--allow-watermark", action="store_true")
    p.add_argument("--ledger", default=DEFAULT_LEDGER)
    p.set_defaults(fn=cmd_pull)

    p = sub.add_parser("image", help="生图（资产图 / 参考图）")
    p.add_argument("--prompt", default="")
    p.add_argument("--prompt-file", default="", help="每行一条；『标题||正文』可指定文件名")
    p.add_argument("--ref", action="append", default=[], help="参考图，可重复（给了就是 r2i）")
    p.add_argument("--name", default="")
    p.add_argument("--out", default=os.path.join(ROOT, "out"))
    p.add_argument("--ratio", default=DEFAULT_RATIO)
    p.add_argument("--resolution", default=DEFAULT_RESOLUTION)
    p.add_argument("--model", default="pro", help="fast / pro / base")
    p.add_argument("--count", type=int, default=1)
    p.add_argument("--mode", choices=["normal", "nopeak"], default="normal",
                   help="生图默认花积分；r2i 不支持闲时")
    p.add_argument("--tail", default="min", choices=list(TAILS),
                   help="尾缀：min 真人写实（默认）/ mid 带字面板 / full 动漫 / none")
    p.add_argument("--interval", type=float, default=5.0)
    p.add_argument("--timeout", type=int, default=900)
    p.add_argument("--allow-watermark", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_image)

    p = sub.add_parser("card", help="做一张符（16:9 能力面板）")
    p.add_argument("--prompt", default="")
    p.add_argument("--prompt-file", default="")
    p.add_argument("--name", default="")
    p.add_argument("--meta", default="", help="meta.json 路径（入库用）")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--ref", action="append", default=[])
    p.add_argument("--out", default="")
    p.add_argument("--ratio", default="16:9")
    p.add_argument("--resolution", default=DEFAULT_RESOLUTION)
    p.add_argument("--model", default="pro")
    p.add_argument("--tail", default="mid", choices=list(TAILS),
                   help="带字面板默认 mid；full 会把小字糊掉")
    p.add_argument("--wait", type=int, default=300)
    p.add_argument("--no-lib", action="store_true")
    p.add_argument("--allow-watermark", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_card)

    p = sub.add_parser("lib", help="符库：列出 / 搜索 / 详情 / 补录 / 移除")
    p.add_argument("--q", default="")
    p.add_argument("--tag", action="append", default=[])
    p.add_argument("--show", default="")
    p.add_argument("--status", default="", choices=["", "候选", "定稿", "弃用"])
    p.add_argument("--grade", default="", help="按评级筛：S / A+ / A / B / C（A 会带出 A+）")
    p.add_argument("--add", default="")
    p.add_argument("--rm", default="")
    p.set_defaults(fn=cmd_lib)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
