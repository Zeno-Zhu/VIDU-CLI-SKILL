# -*- coding: utf-8 -*-
"""init_env.py —— 一次性初始化：查 Python、配 Token、自检。

用法：
    python scripts/init_env.py              # 交互式，一步步来
    python scripts/init_env.py --check      # 只检查，不改任何东西
    python scripts/init_env.py --token vda_xxx   # 直接写入 Token

状态存在 ~/.vidu-cli-skill/，不写 skill 目录（那边会被 git pull 覆盖）。
"""
from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOME_DIR = os.path.join(os.path.expanduser("~"), ".vidu-cli-skill")
TOKEN_FILE = os.path.join(HOME_DIR, "token.txt")
STATE_FILE = os.path.join(HOME_DIR, "state.json")

sys.path.insert(0, HERE)


def say(msg=""):
    print(msg, flush=True)


def mask(t):
    return (t[:8] + "…" + t[-4:]) if len(t) > 14 else "****"


def write_token(tok):
    os.makedirs(HOME_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as f:
        f.write(tok.strip() + "\n")
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except Exception:
        pass
    return TOKEN_FILE


def read_token():
    if os.path.isfile(TOKEN_FILE):
        return open(TOKEN_FILE, encoding="utf-8").read().strip()
    return ""


def save_state(d):
    os.makedirs(HOME_DIR, exist_ok=True)
    d["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    json.dump(d, open(STATE_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def main():
    check_only = "--check" in sys.argv
    tok_arg = ""
    if "--token" in sys.argv:
        i = sys.argv.index("--token")
        if i + 1 < len(sys.argv):
            tok_arg = sys.argv[i + 1].strip()

    say("=" * 56)
    say("  一句话做视频 · 环境检查")
    say("=" * 56)
    say()

    # ---- 1. Python ----
    v = sys.version_info
    ok_py = (v.major, v.minor) >= (3, 8)
    say("[1/3] Python")
    say("      版本 %d.%d.%d  %s" % (v.major, v.minor, v.micro, "OK" if ok_py else "太旧，需要 3.8 以上"))
    if not ok_py:
        say("      去 python.org 装个新的，勾上 Add python.exe to PATH")
        return 1
    say("      位置 %s" % sys.executable)
    say()

    # ---- 2. 依赖 ----
    say("[2/3] 依赖")
    say("      这个工具只用 Python 自带的库，不需要 pip install 任何东西。")
    say("      OK")
    say()

    # ---- 3. Token ----
    say("[3/3] Token")
    cur = tok_arg or read_token() or (os.environ.get("VIDU_TOKEN") or "").strip()
    if tok_arg:
        p = write_token(tok_arg)
        say("      已写入 %s" % p)
    elif cur:
        say("      已经配过了：%s" % mask(cur))
        say("      存在 %s" % TOKEN_FILE)
    else:
        if check_only:
            say("      没配 Token（--check 模式，不写入）")
            return 2
        say("")
        say("      还没配。Token 在你 Vidu 账号里：")
        say("        1. 打开 vidu.cn，登录")
        say("        2. 点左下角头像 → Vidu Token")
        say("        3. 复制那一串（vda_ 开头）")
        say("")
        say("      ⚠ 这一串等于钱包密码，别发群里、别截图给别人。")
        say("")
        try:
            t = input("      把 Token 粘在这里，回车确认：").strip()
        except (EOFError, KeyboardInterrupt):
            say("")
            say("      跳过了。想配的时候再跑一次这个脚本。")
            return 2
        if not t:
            say("      空的，跳过了。")
            return 2
        p = write_token(t)
        cur = t
        say("      存好了：%s" % p)
    say()

    # ---- 自检 ----
    say("-" * 56)
    say("连一下服务器看看…")
    say()
    os.environ["VIDU_TOKEN"] = cur
    try:
        import vidu
        api = vidu.API(token=cur)
        q = api.quota()
        live = api.inflight()
    except SystemExit:
        raise
    except Exception as e:
        say("连不上：%s" % e)
        say("检查一下网络，或者 Token 是不是抄漏了。")
        save_state({"ok": False, "error": str(e)})
        return 1

    if q.get("credits") is None and not q.get("total"):
        say("服务器没返回额度，Token 可能不对。")
        save_state({"ok": False, "error": "bad token"})
        return 1

    say("  闲时额度  %d/%d（今天还能跑 %d 条）" % (q["used"], q["total"], q["left"]))
    say("  积分余额  %s" % q["credits"])
    say("  进行中    %d 条" % len(live))
    say()
    say("=" * 56)
    say("  好了，可以开工。")
    say("=" * 56)
    save_state({"ok": True, "nopeak_total": q["total"], "nopeak_used": q["used"],
                "credits": q["credits"]})
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
