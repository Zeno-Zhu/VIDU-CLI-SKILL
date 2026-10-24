# -*- coding: utf-8 -*-
"""init_env.py —— 一次性初始化：查 Python、配 Token、连服务器自检。

用法
    python scripts/init_env.py                  # 交互式，一步步来
    python scripts/init_env.py --check          # 只检查，不改任何东西（0=就绪 / 2=缺 Token）
    python scripts/init_env.py --token vda_xxx  # 直接写入 Token
    python scripts/init_env.py --with-browser   # 额外检查网页兜底通道（Edge + websocket-client）

Token 写两处，谁先读到用谁：
    · 本包 .env 的 VIDU_TOKEN（或 VIDU_TOKEN_1..N）
    · ~/.vidu-cli-skill/token.txt（老版本习惯，兼容保留）
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOME_DIR = os.path.join(os.path.expanduser("~"), ".vidu-cli-skill")
TOKEN_FILE = os.path.join(HOME_DIR, "token.txt")
STATE_FILE = os.path.join(HOME_DIR, "state.json")
ENV_FILE = os.path.join(ROOT, ".env")
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

OK, WARN, BAD = "[OK]", "[! ]", "[X ]"


def say(msg=""):
    print(msg, flush=True)


def mask(t):
    return (t[:8] + "…" + t[-4:]) if len(t) > 14 else "****"


def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except Exception as e:
        return -1, str(e)


# ─────────────────────── Token 落盘 ───────────────────────
def env_lines():
    if os.path.isfile(ENV_FILE):
        return open(ENV_FILE, encoding="utf-8").read().splitlines()
    return []


def write_env(tok):
    lines = env_lines()
    key = "VIDU_TOKEN_1" if any(l.strip().startswith("VIDU_TOKEN_") for l in lines) else "VIDU_TOKEN"
    hit = False
    out = []
    for l in lines:
        if l.strip().startswith(key + "="):
            out.append("%s=%s" % (key, tok))
            hit = True
        else:
            out.append(l)
    if not hit:
        out.append("%s=%s" % (key, tok))
    if not lines:
        out = ["# 本机私有配置（.env 不进仓库）",
               "# Token：vidu.cn → 左下角头像 → Vidu Token",
               "VIDU_BASE_URL=https://service.vidu.cn",
               "%s=%s" % (key, tok)]
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    return ENV_FILE


def write_token_file(tok):
    os.makedirs(HOME_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(tok.strip() + "\n")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass
    return TOKEN_FILE


def current_token():
    """按 vidu.py 的顺序找一遍，不写任何东西。"""
    if (os.environ.get("VIDU_TOKEN") or "").strip():
        return os.environ["VIDU_TOKEN"].strip()
    i = 1
    while (os.environ.get("VIDU_TOKEN_%d" % i) or "").strip():
        return os.environ["VIDU_TOKEN_%d" % i].strip()
    for l in env_lines():
        s = l.strip()
        if s.startswith("VIDU_TOKEN=") or s.startswith("VIDU_TOKEN_1="):
            return s.split("=", 1)[1].strip().strip('"').strip("'")
    if os.path.isfile(TOKEN_FILE):
        v = open(TOKEN_FILE, encoding="utf-8").read().strip()
        if v:
            return v
    return ""


def save_state(d):
    os.makedirs(HOME_DIR, exist_ok=True)
    d["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    json.dump(d, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


# ─────────────────────── 检查项 ───────────────────────
def step_python():
    v = sys.version_info
    ok = (v.major, v.minor) >= (3, 8)
    say("      版本 %d.%d.%d  %s" % (v.major, v.minor, v.micro, "OK" if ok else "太旧，需要 3.8+"))
    say("      位置 %s" % sys.executable)
    if not ok:
        say("      去 python.org 装个新的，勾上 Add python.exe to PATH")
    return ok


def step_browser(no_pip=False):
    say("      （网页兜底通道，可选）")
    try:
        import websocket  # noqa: F401
        say("%s 依赖 websocket-client 已安装" % OK)
    except ImportError:
        if no_pip:
            say("%s 缺 websocket-client（--no-pip，跳过）" % WARN)
            return False
        say("%s 正在安装 websocket-client…" % WARN)
        rc, _ = run([sys.executable, "-m", "pip", "install", "websocket-client"])
        if rc != 0:
            rc, _ = run([sys.executable, "-m", "pip", "install", "--user", "websocket-client"])
        if rc != 0:
            say("%s 装不上。手动：\"%s\" -m pip install websocket-client" % (BAD, sys.executable))
            return False
        say("%s websocket-client 安装完成" % OK)
    edge = next((p for p in EDGE_CANDIDATES if os.path.exists(p)), "")
    if edge:
        say("%s Edge 已安装：%s" % (OK, edge))
        return True
    say("%s 没找到 Edge（不影响 Token 直连，只是没有网页兜底）" % WARN)
    return False


def probe(tok):
    sys.path.insert(0, HERE)
    try:
        import vidu
        api = vidu.Vidu(token=tok)
        q = api.quota()
        live = api.inflight()
    except SystemExit:
        raise
    except Exception as e:
        return None, str(e)
    if q.get("credits") is None and not q.get("total"):
        return None, "服务器没返回额度，Token 可能不对"
    return {"total": q["total"], "used": q["used"], "left": q["left"],
            "credits": q["credits"], "inflight": len(live)}, ""


def main():
    ap = argparse.ArgumentParser(description="Vidu 统一包 —— 一次性环境自检")
    ap.add_argument("--check", action="store_true", help="只检查，不写任何东西")
    ap.add_argument("--token", default="", help="直接写入 Token")
    ap.add_argument("--account", type=int, default=None, help="多账号：用第几个")
    ap.add_argument("--with-browser", action="store_true", help="额外检查网页兜底通道")
    ap.add_argument("--no-pip", action="store_true")
    a = ap.parse_args()

    say("=" * 58)
    say("  Vidu 漫剧工作流 —— 环境检查")
    say("  包目录：%s" % ROOT)
    say("=" * 58)
    say()
    say("[1/3] Python")
    ok_py = step_python()
    say()

    say("[2/3] 依赖")
    say("      提交/查询/下载/生图只用 Python 标准库，不需要 pip install 任何东西。")
    if a.with_browser:
        step_browser(a.no_pip)
    say()

    say("[3/3] Token")
    tok = (a.token or "").strip() or current_token()
    if a.token and not a.check:
        say("      已写入 %s" % write_env(tok.strip()))
        say("      已写入 %s" % write_token_file(tok.strip()))
        tok = tok.strip()
    elif tok:
        say("      已经配过了：%s" % mask(tok))
    else:
        if a.check:
            say("      没配 Token（--check 模式，不写入）")
            say()
            say("⇒ 返回 2：只问 Token，别的一概不问。")
            return 2
        say("")
        say("      还没配。Token 在你 Vidu 账号里：")
        say("        1. 打开 vidu.cn，登录")
        say("        2. 点左下角头像 → Vidu Token")
        say("        3. 复制那一串（vda_ 开头）")
        say("")
        say("      找不到的话，看这张图：assets/vidu-token.png")
        say("")
        say("      ⚠ 这一串等于钱包密码，别发群里、别截图给别人。")
        say("")
        try:
            t = input("      把 Token 粘在这里，回车确认：").strip()
        except (EOFError, KeyboardInterrupt):
            say("")
            say("      跳过了。想配的时候再跑一次。")
            return 2
        if not t:
            say("      空的，跳过了。")
            return 2
        say("      已写入 %s" % write_env(t))
        say("      已写入 %s" % write_token_file(t))
        tok = t
    say()

    say("-" * 58)
    say("连一下服务器看看…")
    q, err = probe(tok)
    if not q:
        say("%s 连不上：%s" % (BAD, err))
        say("     检查网络，或 Token 是不是抄漏了。")
        save_state({"ok": False, "error": err})
        return 1

    say("  账号档位  %s" % ("旗舰版（200 条/天）" if q["total"] >= 100 else
                            ("专业版（20 条/天）" if q["total"] else "未识别")))
    say("  闲时额度  %d/%d（今天还能跑 %d 条）" % (q["used"], q["total"], q["left"]))
    say("  积分余额  %s" % q["credits"])
    say("  进行中    %d 条" % q["inflight"])
    say()
    say("=" * 58)
    say("  好了，可以开工。")
    say("=" * 58)
    save_state({"ok": True, "nopeak_total": q["total"], "nopeak_used": q["used"],
                "credits": q["credits"]})
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
