# -*- coding: utf-8 -*-
"""init_env.py —— 一次性初始化：查 Python、配 Token、连服务器自检。

用法
    python scripts/init_env.py                  # 交互式，一步步来
    python scripts/init_env.py --check          # 只检查，不写任何配置（0=就绪 / 2=缺 Token）
    python scripts/init_env.py --token vda_xxx  # 直接写入 Token
    python scripts/init_env.py --with-browser   # 额外检查网页兜底通道（Edge + websocket-client）
    python scripts/init_env.py --open-login     # 只打开 Vidu 登录页，不做别的
    python scripts/init_env.py --check --no-browser   # 无人值守：不弹浏览器

★ 没 Token 时：尽力拉起系统浏览器，并输出固定路径引导（宿主网页预览 + 代码块链接
  → 请登录 → 取 Token 三步 → 参考图）。真正把页面展示给用户，由 AI 用宿主网页预览完成。
  默认用户已经买过会员，绝不引导购买 / 开通 / 升级。
  Windows 上优先**显式启动 Edge / Chrome / Firefox 并强制开新窗口**，不依赖可能失效的
  https 默认关联（os.startfile / webbrowser.open 会「成功」但可能一个窗口都不弹）。
  ⚠ 脚本只是**尽力**拉起系统浏览器：沙箱、远程桌面、默认关联失效、命令结束即回收子进程的
    宿主里，窗口可能压根不出现。真正把登录页展示给用户，靠 AI 用宿主的「网页预览」能力；
    **脚本的 [OK] 不等于「用户看得见」**。
  --check 会打开一次浏览器并记一个时间戳（10 分钟内不重复弹），但不写 Token、不写配置；
  --no-browser 或环境变量 VIDU_NO_BROWSER=1 可完全关掉自动打开。

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
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HOME_DIR = os.path.join(os.path.expanduser("~"), ".vidu-cli-skill")
TOKEN_FILE = os.path.join(HOME_DIR, "token.txt")

# 登录入口（默认已购会员，这里只当「去登录 / 找 Token」的入口，不做购买引导）
LOGIN_URL = "https://www.vidu.cn/my-subscription?bonus-code=LAOZHU"
SUB_URL = LOGIN_URL  # 兼容旧引用
TOKEN_GUIDE_IMG = os.path.join(ROOT, "assets", "vidu-token.png")
STATE_FILE = os.path.join(HOME_DIR, "state.json")
BROWSER_STATE = os.path.join(HOME_DIR, "login_prompt.json")
BROWSER_COOLDOWN = 600  # 秒：AI 反复跑 --check 时，10 分钟内不重复弹浏览器
ENV_FILE = os.path.join(ROOT, ".env")
EDGE_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
]

# 显式启动浏览器：不依赖 https 默认关联；--new-window 保证弹的是可见新窗口而不是后台标签
BROWSER_CANDIDATES = [
    (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "--new-window"),
    (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "--new-window"),
    (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "--new-window"),
    (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "--new-window"),
    (os.path.join(os.environ.get("LOCALAPPDATA", ""), "Google", "Chrome",
                  "Application", "chrome.exe"), "--new-window"),
    (r"C:\Program Files\Mozilla Firefox\firefox.exe", "-new-window"),
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


# ─────────────── 缺 Token：开浏览器 + 取 Token 引导 ───────────────
def launch_visible_browser(url):
    """显式启动一个确实存在的浏览器并强制新窗口，返回 (浏览器名, 是否启动)。

    故意不走 https 默认关联：UserChoice 可能指向已卸载的浏览器（如残留的
    QuarkHTMX），这时 os.startfile / webbrowser.open 会返回 True 却一个窗口都不弹。
    """
    for exe, flag in BROWSER_CANDIDATES:
        if exe and os.path.isfile(exe):
            try:
                subprocess.Popen([exe, flag, url], close_fds=True)
                return os.path.basename(exe), True
            except Exception:
                continue
    return "", False


def open_login_page(no_browser=False, force=False):
    """没 Token 时尽力拉起登录页。返回「启动请求是否成功」，**不代表窗口可见**。

    force=True 用于显式的 --open-login：绕过 --no-browser 和 10 分钟去重。
    """
    if not force and (no_browser or os.environ.get("VIDU_NO_BROWSER", "").strip().lower()
                      in ("1", "true", "yes")):
        say("      （--no-browser / VIDU_NO_BROWSER：这次不自动打开）")
        say("      手动打开：%s" % LOGIN_URL)
        return False
    try:
        last = float(json.load(open(BROWSER_STATE, encoding="utf-8")).get("opened_at", 0))
    except Exception:
        last = 0.0
    if not force and time.time() - last < BROWSER_COOLDOWN:
        say("      （10 分钟内已经打开过一次，不重复弹；地址仍是 %s）" % LOGIN_URL)
        return False
    exe, ok = launch_visible_browser(LOGIN_URL)
    if ok:
        say("      %s 已用 %s 请求打开新窗口（不保证用户看得见）：%s" % (WARN, exe, LOGIN_URL))
    else:
        # 兜底：非 Windows / 找不到已知浏览器时才用系统默认关联
        # 注意 webbrowser.open 返回 True 只代表 ShellExecute 没报错，不等于窗口可见
        try:
            ok = bool(webbrowser.open(LOGIN_URL))
        except Exception as e:
            ok = False
            say("      %s 请求系统默认浏览器失败（%s）" % (WARN, e))
        if ok:
            say("      %s 已请求系统默认浏览器打开（可能只在后台开标签）：%s" % (WARN, LOGIN_URL))
        else:
            say("      %s 没能自动打开浏览器，请把地址发给用户手动打开：%s" % (WARN, LOGIN_URL))
    say("      ⚠ 请 AI 用宿主的「网页预览」能力展示页面，并用代码块把链接再发一遍；别把这里当成已打开。")
    if ok:
        try:
            os.makedirs(HOME_DIR, exist_ok=True)
            json.dump({"opened_at": time.time(), "url": LOGIN_URL,
                       "via": exe or "webbrowser"},
                      open(BROWSER_STATE, "w", encoding="utf-8"))
        except Exception:
            pass
    return ok


def print_token_guide():
    """发给用户看的取 Token 三步（默认他已经有账号）。"""
    say("      ── 取 Token，三步 ──")
    say("      1. 打开登录页 %s（没看到窗口就手动贴到浏览器），先登录你的 Vidu 账号。" % LOGIN_URL)
    say("      2. 点左下角头像 → 菜单里的「<> Vidu Token」。")
    say("      3. 复制那一串（vda_ 开头）贴回来；只贴给我，别发群里、别截图给别人。")
    say("")
    say("      参考图（照着点就行）：%s" % TOKEN_GUIDE_IMG)
    say("      图里红框圈的就是：左下角头像 → 菜单里的 <> Vidu Token。")


def print_agent_orders():
    """给 AI 的动作指令：一次性把登录要求、步骤、图片都发出去。"""
    say("      ⇒ AI 固定操作路径，按顺序一次做完，不要等用户追问：")
    say("        ① ★ 用宿主的「网页预览 / 打开链接」能力把登录页展示给用户看：%s" % LOGIN_URL)
    say("           并且**无论打开成功与否，都用代码块把这个链接原样再发一遍**（跨宿主通用兜底）。")
    say("           脚本只**尽力**拉起系统浏览器；沙箱 / 远程 / 默认关联失效 / 子进程被回收时")
    say("           可能一个窗口都没有。用户说没看到就立刻发地址，别坚持说已经打开了。")
    say("        ② 请他本人登录：手机号 / 验证码本人操作，AI 不代登录、不代取 Token、不碰账号凭证。")
    say("        ③ 把上面「取 Token 三步」发给他。")
    say("        ④ 立刻把参考图**作为图片**发给他：%s" % TOKEN_GUIDE_IMG)
    say("           —— 发图片本身，不是发路径字符串；别等他说「找不到」才发。")
    say("        ⑤ 拿到 Token 后跑：python scripts/init_env.py --token <那串>")
    say("      ⛔ 全程不提「购买 / 开通 / 升级 / 要不要开会员」；默认他已经买过了。")


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
    ap.add_argument("--check", action="store_true", help="只检查，不写任何配置（0=就绪 / 2=缺 Token）")
    ap.add_argument("--token", default="", help="直接写入 Token")
    ap.add_argument("--account", type=int, default=None, help="多账号：用第几个")
    ap.add_argument("--with-browser", action="store_true", help="额外检查网页兜底通道")
    ap.add_argument("--no-browser", action="store_true", help="缺 Token 时不自动打开浏览器")
    ap.add_argument("--open-login", action="store_true", help="只打开 Vidu 登录页，不做别的")
    ap.add_argument("--no-pip", action="store_true")
    a = ap.parse_args()

    if a.open_login:
        say("  打开 Vidu 登录页：%s" % LOGIN_URL)
        open_login_page(force=True)
        return 0

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
        say("      本机没有找到 Vidu Token。")
        say("")
        open_login_page(a.no_browser)
        say("")
        print_token_guide()
        say("")
        if a.check:
            say("      （--check 模式，不写入任何 Token / 配置）")
            say("")
            print_agent_orders()
            say("")
            say("⇒ 返回 2：只缺 Token，后面一步都不做，等他登录后把 Token 贴回来。")
            return 2
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
