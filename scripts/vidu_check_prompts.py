#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vidu_check_prompts.py —— 提示词结构门（双模板 · 零计费）

认两套模板，自动分派：
  · `_自己人` 散文制式（无 △，镜头权交给模型）
  · `_标准`   逐镜制式（九字段，镜头逐镜写死）

用法
    python scripts/vidu_check_prompts.py --new "<项目>/自己人提示词/第1集.txt"
    python scripts/vidu_check_prompts.py --project "<项目目录>"          # 自动找两套稿子
    python scripts/vidu_check_prompts.py --new 新稿.txt --old 旧稿.txt   # 台词逐字对账
    python scripts/vidu_check_prompts.py --new 稿.txt --asset-dir "<项目>/01_资产库"

查什么
  A 结构：&&start/&&end 配对 · 组号唯一 · 组号格式 · 模板字段齐全
  B 标题：一级标题 `第N集·《…》` 唯一
  C 时长：整数秒 1—16（目标 12—16，<12 只提醒）；标准模板还需「各镜时长之和 = 组时长」
  D 资产：pn 连续且 ≤9 · vm ≤3 · 资产名存在（给了 --asset-dir / --panel-dir 才查）
  E 音色：有独立音色的发言者 ≤3 · vm 与发言角色一致 · 无台词不许有音色块
  F 台词：新旧逐字多重集完全一致（给了 --old 才查）
  G 格式：每句台词后紧跟 `<>`，且以「保持<角色名>的音色不变，」开头
  H 正文：无 `《》` 剩余占位 · 无未替换变量 · 不空
  I 规范：无内部工作痕迹（主镜头锚点 / 沿用上一组站位）· 无禁用音色词
  J 音色通道（★ 2026-10-26 新增）：闲时（nopeak）不许挂 vm，必须有【音色文字锁定】；
    normal 必须有 vm。锚点串与音色卡逐字一致 · 同一角色跨组一字不差。

★ 为什么有 J：闲时无法参考音色（实测），角色声线只能靠文字锚点串锁定。
  ⚠ 注意区别：闲时**照样会生成配音**（平台原生配音逐句念台词）。
  这一项拦的是「不该挂参考音频」，⛔ 不是「不该有台词」——把台词删掉同样算错。
  给了 --voice-dir 就对着卡文件核，没给就只核「有没有、齐不齐、跨组同不同」。

退出码：0 通过｜1 有错误｜2 输入有问题
"""
from __future__ import annotations

import argparse
import collections
import io
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MIN_SEC, MAX_SEC, TARGET_LOW = 1, 16, 12
MAX_IMAGES, MAX_AUDIOS, MAX_CHARS = 9, 3, 2000

FORCE = ("【强制声明】无背景音乐；画面无字幕/台词文字/水印/Logo/角标/UI；声音：不要配乐，仅保留同期声；"
         "全程无背景音乐，仅保留真实环境音效与动作同期声。")

CJK = re.compile(r"[\u4e00-\u9fff]")
GROUP_ID = re.compile(r"分镜组ID：\s*([^\s\n]+)")
DUR = re.compile(r"分镜组时长：\s*(\d+(?:\.\d+)?)\s*(?:秒|s)?")
TITLE = re.compile(r"^\s*第\s*\d+\s*集\s*[·:：]\s*《[^》]+》\s*$")
DIALOGUE = re.compile(r"([^\s：:<>\n【】]{1,12})：\s*([^<>\n]+?)\s*<([^<>]+)>")
DIRECTION = re.compile(r"^<(.+)>$")
BAD_WORDS = ["主镜头锚点", "沿用上一组站位", "磁性嗓音", "少女音", "御姐音", "烟嗓", "播音腔",
             "气泡音", "贵族腔", "声音变老", "低音炮", "奶音"]
VOICE_MOD_FIELD = "【音色文字锁定】"
VOICE_STRICT_FIELD = "【音色严格规范】"

SELF_FIELDS = ["【基础信息】", "【统一风格模块】", "【强制声明】", "【资产盘点】", "【提示词正文】"]
STD_FIELDS = ["【基础信息】", "【统一风格模块】", "【强制声明】", "【资产盘点】", "【提示词正文】",
              "【质感与一致性】"]
STD_SHOT_FIELDS = ["时长：", "景别：", "拍摄方式与视角：", "运镜：", "构图：",
                   "角色台词：", "音频提示词："]
STD_SHOT_FIELDS_OPT = ["肢体动作", "对标影视特效参考"]


# ─────────────────────── 读文件 ───────────────────────
def read_blocks(path):
    raw = open(path, encoding="utf-8-sig").read()
    return raw, re.findall(r"&&start\s*\n(.*?)\n\s*&&end", raw, re.S)


def guess_template(block, gid):
    if gid.endswith("_自己人") or gid.endswith("_自己人B"):
        return "自己人"
    if gid.endswith("_标准"):
        return "标准"
    if "【本提示词对应的信息】" in block or "【导演目标】" in block:
        return "自己人"
    if "【镜号" in block:
        return "标准"
    return "自己人"


SPEAKER = r"[^\s：:<>\n【】，。；！？、…“”\"\'（）()]{1,12}"
DIA = re.compile("(" + SPEAKER + r")：\s*([^<>\n]+?)\s*<([^<>]+)>")


def extract_dialogue(body, tpl, shots=None):
    """返回 [(角色, 台词, <>内容)]。标准模板只看「角色台词：」字段，避免把字段名当角色。"""
    out = []
    if tpl == "标准":
        for name, seg in (shots or []):
            m = re.search(r"角色台词：\s*(.+)", seg)
            if not m:
                continue
            v = m.group(1).strip()
            if v in ("无", "—", "-", ""):
                continue
            for mm in DIA.finditer(v):
                out.append((mm.group(1).strip(), mm.group(2).strip(), mm.group(3).strip()))
            if "<" not in v:
                out.append(("", v, ""))
    else:
        for mm in DIA.finditer(body):
            out.append((mm.group(1).strip(), mm.group(2).strip(), mm.group(3).strip()))
    return out


def cjk(s):
    return len(CJK.findall(s or ""))


# ─────────────────────── 音色通道（J） ───────────────────────
ANCHOR_LINE = re.compile(r"^([^\s：:<>【】《》（）]{1,12})：\s*(.+?)\s*$")


def parse_voice_module(block):
    """取【音色文字锁定】里的 {角色: 锚点串}。"""
    m = re.search(re.escape(VOICE_MOD_FIELD) + r"\s*\n(.*?)(?=\n【|\n&&end|\Z)", block, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).split("\n"):
        s = line.strip()
        if not s or s.startswith(("【", "《", "·", "-", "本组无参考音频")):
            continue
        mm = ANCHOR_LINE.match(s)
        if not mm:
            continue
        name, anchor = mm.group(1).strip(), mm.group(2).strip()
        if "，" in name or "。" in name or "/" in name:
            continue
        out[name] = anchor
    return out


def load_voice_cards(path):
    """读 _资产提示词/音色-*.txt → {角色名: 锚点串}。"""
    cards = {}
    if not path or not os.path.isdir(path):
        return cards
    for fn in os.listdir(path):
        if not fn.startswith("音色-") or not fn.lower().endswith(".txt"):
            continue
        name = os.path.splitext(fn)[0][len("音色-"):].strip()
        txt = open(os.path.join(path, fn), encoding="utf-8", errors="ignore").read()
        m = re.search(r"锚点串[：:]\s*(.+)", txt)
        if m:
            cards[name] = m.group(1).strip()
    return cards


def check_voice(block, dia, mode, cards, bad, warn):
    """J：闲时不许 vm；必须有锚点串；锚点串要对得上卡。返回 {角色: 锚点}"""
    vms = re.findall(r"vm(\d+),\s*([^=@，,\n]+?)\s*=@", block)
    has_vm = bool(vms) and "人物音色资产：无" not in block
    speakers = []
    for sp, _t, _d in dia:
        if sp and sp not in speakers:
            speakers.append(sp)
    mod = parse_voice_module(block)

    if mode == "nopeak":
        if has_vm:
            bad("闲时（nopeak）不能挂参考音色：删掉 vm 行，改用【音色文字锁定】"
                "（见 references/音色与配音.md）。⚠ 台词照念，别删台词")
        if speakers and not mod:
            bad("闲时稿必须有【音色文字锁定】：%s 这一组没锁声线" % "/".join(speakers))
        if mod and VOICE_STRICT_FIELD in block:
            bad("【音色严格规范】与【音色文字锁定】不能同时出现（一个走参考音，一个走文字）")
        for sp in speakers:
            if mod and sp not in mod:
                bad("【音色文字锁定】缺发言角色：%s" % sp)
    elif mode == "normal":
        if speakers and not has_vm:
            bad("normal 通道有台词却没登记 vm 行（有参考音色就写 `人物音色资产：vm1,<名>=@`）")
        if mod:
            warn("normal 通道同时出现【音色文字锁定】，确认不是混模板")

    for sp, anchor in mod.items():
        if len(anchor) > 40:
            warn("%s 锚点串 %d 字 > 40，建议压短（每组都要抄一遍）" % (sp, len(anchor)))
        if cards:
            if sp not in cards:
                bad("%s 没有音色卡（--voice-dir 下应有 音色-%s.txt）" % (sp, sp))
            elif anchor != cards[sp]:
                bad("%s 锚点串与音色卡不一致：\n        稿子：%s\n        卡  ：%s"
                    % (sp, anchor, cards[sp]))

    # ★ 2026-10-26：防止把「闲时不能参考音色」误读成「没声音」而删掉台词
    if mod and not speakers:
        warn("本组写了【音色文字锁定】却一句台词都没有 —— 是不是把台词删了？"
             "闲时照样有原生配音，台词不该删；真要纯画面组，把音色模块整块去掉")
    return mod


# ─────────────────────── 校验 ───────────────────────
def check_self(block, bad, warn):
    for k in SELF_FIELDS:
        if k not in block:
            bad("缺模块 %s" % k)
    body = block.split("【提示词正文】", 1)[1] if "【提示词正文】" in block else ""
    if not body.strip():
        bad("【提示词正文】为空")
    # 散文制式：不应出现逐镜标记
    if re.search(r"^【镜号", body, re.M):
        bad("自己人版出现【镜号】—— 自己人是散文制式，逐镜标记属于标准模板")
    if "△" in body:
        warn("自己人版正文出现 △（散文制式不需要 △，确认没混模板）")
    return body


def check_std(block, bad, warn):
    for k in STD_FIELDS:
        if k not in block:
            bad("缺模块 %s" % k)
    body = block.split("【提示词正文】", 1)[1] if "【提示词正文】" in block else ""
    if not body.strip():
        bad("【提示词正文】为空")
        return body, []
    shots = re.findall(r"【镜号([^】]+)】\s*\n(.*?)(?=\n【镜号|\n【质感与一致性】|\Z)", body, re.S)
    if not shots:
        bad("标准版没有一个【镜号X】")
        return body, []
    total = 0.0
    for name, seg in shots:
        for f in STD_SHOT_FIELDS:
            if f not in seg:
                bad("镜号%s 缺字段 %s" % (name, f.rstrip("：")))
        for f in STD_SHOT_FIELDS_OPT:
            if f not in seg:
                warn("镜号%s 缺「%s」（建议补，没有也能出片）" % (name, f))
        m = re.search(r"时长：\s*(\d+(?:\.\d+)?)", seg)
        if not m:
            bad("镜号%s 没写时长" % name)
        else:
            d = float(m.group(1))
            total += d
            if d < 1.2 - 1e-9:
                bad("镜号%s 时长 %.1fs < 1.2s 硬下限" % (name, d))
    return body, shots, total


def check_group(block, asset_names, panel_names, old_counter, bad, warn, note,
                voice_mode="auto", voice_cards=None):
    gid_m = GROUP_ID.search(block)
    if not gid_m:
        bad("缺 分镜组ID")
        gid = "?"
    else:
        gid = gid_m.group(1).strip()

    if not re.match(r"^\d+_\d+_(自己人|标准|自己人B|B)$", gid):
        bad("组号格式不合规（应形如 1_1_自己人 / 1_1_标准 / 1_1_B）：%s" % gid)

    tpl = guess_template(block, gid)
    note(gid, tpl)

    if FORCE not in block:
        bad("【强制声明】未原文输出")
    if "大词层：" not in block:
        bad("【统一风格模块】缺 大词层")
    if "小词层：" not in block:
        bad("【统一风格模块】缺 小词层")

    # 时长
    dm = DUR.search(block)
    if not dm:
        bad("分镜组时长格式异常（应写「分镜组时长：14秒」）")
        dur = None
    else:
        raw = float(dm.group(1))
        if abs(raw - round(raw)) > 1e-9:
            warn("组时长写了小数 %.2f，提交前会取整" % raw)
        dur = int(round(raw))
        if dur > MAX_SEC or dur < MIN_SEC:
            bad("组时长 %ds 超界（%d—%d 秒）" % (dur, MIN_SEC, MAX_SEC))
        elif dur < TARGET_LOW:
            warn("组时长 %ds 低于目标 12s —— 能合就合" % dur)

    # 模板专属
    if tpl == "自己人":
        body = check_self(block, bad, warn)
    else:
        body = check_std(block, bad, warn)[0]
        # 各镜时长之和 vs 组时长（check_std 已算过一遍，这里重算避免重复告警）
        shots = re.findall(r"【镜号([^】]+)】\s*\n(.*?)(?=\n【镜号|\n【质感与一致性】|\Z)", body, re.S)
        total = 0.0
        for _n, seg in shots:
            m = re.search(r"时长：\s*(\d+(?:\.\d+)?)", seg)
            if m:
                total += float(m.group(1))
        if dur and shots and abs(total - dur) > 1e-6:
            bad("各镜时长之和 %.1fs ≠ 组时长 %ds" % (total, dur))

    # 台词 + <> 绑定
    shots = (re.findall(r"【镜号([^】]+)】\s*\n(.*?)(?=\n【镜号|\n【质感与一致性】|\Z)", body, re.S)
             if tpl == "标准" else None)
    dia = extract_dialogue(body, tpl, shots)
    for sp, tx, d in dia:
        if not sp:
            bad("台词「%s」缺 <> 绑定（标准模板每一句都要跟在「角色台词：」后面并带 <>）" % tx[:12])
        elif not d.startswith("保持%s的音色不变，" % sp):
            bad("台词「%s」的 <> 未以「保持%s的音色不变，」开头" % (tx[:12], sp))
    # 正文里出现「角色：台词」但没有 <> 的，单独抓
    for line in body.split("\n"):
        s = line.strip()
        if not s or s.startswith(("【", "△", "场景：", "时间：", "节奏提示词：", "#")):
            continue
        if re.match(r"^[^\s：:<>{]{1,12}：", s) and "<" not in s and "保持" not in s:
            # 白名单：字段行
            if not re.match(r"^(时长|景别|拍摄方式与视角|运镜|构图|角色台词|音频提示词|"
                            r"肢体动作|对标影视特效参考|故事背景|关键情绪和冲突|环境时空基准|"
                            r"空间站位说明|光影调度|同期声说明|大词层|小词层|画幅)[:：]", s):
                warn("疑似台词行没有 <> 绑定：%s" % s[:30])

    speakers = []
    for sp, _tx, _d in dia:
        if sp and sp not in speakers:
            speakers.append(sp)

    # 资产
    pns = [int(x) for x in re.findall(r"pn(\d+),", block)]
    if pns:
        if sorted(set(pns)) != list(range(1, len(set(pns)) + 1)):
            bad("pn 编号不连续：%s" % sorted(set(pns)))
        if max(pns) > MAX_IMAGES:
            bad("图片 %d 张 > %d 上限" % (max(pns), MAX_IMAGES))
    names = [n.strip() for n in re.findall(r"pn\d+,\s*([^=@，,\n]+)\s*=@", block)]
    known = set(asset_names or []) | set(panel_names or [])
    if known:
        for n in names:
            if n not in known:
                bad("资产不存在于磁盘：%s" % n)
    vms = [int(x) for x in re.findall(r"vm(\d+),", block)]
    if vms:
        if sorted(set(vms)) != list(range(1, len(set(vms)) + 1)):
            bad("vm 编号不连续：%s" % sorted(set(vms)))
        if len(vms) > MAX_AUDIOS:
            bad("音色 %d 条 > %d 上限" % (len(vms), MAX_AUDIOS))
    if len(speakers) > MAX_AUDIOS:
        bad("有台词的角色 %d 名 > %d（平台只给 3 条音色）：%s"
            % (len(speakers), MAX_AUDIOS, speakers))
    if not dia and "人物音色资产" in block and "人物音色资产：无" not in block:
        bad("无台词却登记了人物音色资产")
    if not dia and "【音色严格规范】" in block:
        bad("无台词却输出了【音色严格规范】")
    if not dia and VOICE_MOD_FIELD in block:
        bad("无台词却输出了【音色文字锁定】")

    # J 音色通道
    if voice_mode == "auto":
        eff_mode = ("normal" if (re.search(r"vm\d+,", block) and "人物音色资产：无" not in block)
                    else "nopeak")
    else:
        eff_mode = voice_mode
    anchors = check_voice(block, dia, eff_mode, voice_cards, bad, warn)

    # 正文体量
    if dur and len(body) > MAX_CHARS:
        bad("正文 %d 字 > %d 上限" % (len(body), MAX_CHARS))
    if "《" in body or "》" in body:
        bad("正文残留《》占位")
    for w in BAD_WORDS:
        if w in block:
            bad("出现禁用词/内部痕迹：%s" % w)

    # 台词逐字对账
    if old_counter is not None:
        pass  # 由外层统一比对

    return {"gid": gid, "tpl": tpl, "dur": dur, "lines": len(dia),
            "chars": sum(cjk(t) for _s, t, _d in dia), "pn": len(set(pns)),
            "vm": len(vms), "speakers": speakers, "mode": eff_mode,
            "anchors": anchors,
            "dialogue": [t for _s, t, _d in dia]}


def main():
    ap = argparse.ArgumentParser(description="Vidu 提示词结构门（自己人 / 标准 双模板）")
    ap.add_argument("--new", default="", help="要校验的稿子")
    ap.add_argument("--old", default="", help="改写前的旧稿（台词逐字对账基准）")
    ap.add_argument("--project", default="", help="项目根目录：自动找两套稿子")
    ap.add_argument("--asset-dir", default="", help="资产图目录（给了才查资产是否存在）")
    ap.add_argument("--panel-dir", default="", help="常用符目录（给了才查符是否存在）")
    ap.add_argument("--strict", action="store_true", help="警告也算不过")
    ap.add_argument("--voice-mode", choices=["auto", "nopeak", "normal"], default="auto",
                    help="音色通道：auto=有 vm 行算 normal，没有算 nopeak（默认）")
    ap.add_argument("--voice-dir", default="",
                    help="音色卡目录（…/00_剧本与提示词/_资产提示词）：给了就核锚点串与卡逐字一致")
    ap.add_argument("--json", default="", help="结果另存 JSON")
    a = ap.parse_args()

    if not a.voice_dir and a.project:
        cand = os.path.join(a.project, "00_剧本与提示词", "_资产提示词")
        if os.path.isdir(cand):
            a.voice_dir = cand

    files = []
    if a.new:
        files.append(a.new)
    if a.project:
        for rel in ("00_剧本与提示词/自己人提示词/第1集.txt",
                    "00_剧本与提示词/标准提示词/第1集.txt",
                    "00_剧本与提示词/视频提示词/第1集.txt"):
            p = os.path.join(a.project, rel)
            if os.path.isfile(p) and p not in files:
                files.append(p)
    if not files:
        print("[ERROR] 没给稿子。用 --new <文件>，或 --project <项目目录>")
        return 2
    for p in files:
        if not os.path.isfile(p):
            print("[ERROR] 文件不存在：%s" % p)
            return 2

    asset_names, panel_names = None, None
    if a.asset_dir and os.path.isdir(a.asset_dir):
        asset_names = set(os.path.splitext(f)[0] for f in os.listdir(a.asset_dir)
                          if os.path.isfile(os.path.join(a.asset_dir, f)))
    if a.panel_dir and os.path.isdir(a.panel_dir):
        panel_names = set()
        for n in os.listdir(a.panel_dir):
            d = os.path.join(a.panel_dir, n)
            if os.path.isdir(d) and os.path.isfile(os.path.join(d, "panel.png")):
                panel_names.add(n)
            elif n.lower().endswith(".png"):
                panel_names.add(os.path.splitext(n)[0])

    voice_cards = load_voice_cards(a.voice_dir)
    if a.voice_dir and not voice_cards:
        print("⚠ --voice-dir 里没读到 音色-*.txt（%s）" % a.voice_dir)

    err, warn_all = [], []
    rows, all_new = [], []
    old_counter = None
    if a.old:
        if not os.path.isfile(a.old):
            print("[ERROR] 旧稿不存在：%s" % a.old)
            return 2
        _r, ob = read_blocks(a.old)
        old_counter = collections.Counter(
            m.group(2).strip() for b in ob for m in re.finditer(r"([^\s：:<>\n]{1,12})：\s*([^<>\n]+?)\s*<", b))

    for path in files:
        raw, blocks = read_blocks(path)
        print("=" * 68)
        print("稿子：%s" % path)
        if not blocks:
            print("  ✗ 一个 &&start…&&end 块都没读到")
            err.append("%s：没有代码块" % path)
            continue
        if raw.count("&&start") != raw.count("&&end"):
            err.append("&&start / &&end 数量不配对：%d / %d"
                       % (raw.count("&&start"), raw.count("&&end")))
        titles = [l for l in raw.split("\n") if TITLE.match(l)]
        if len(titles) != 1:
            err.append("一级标题应恰好 1 个（形如「第1集·《标题》」），实际 %d 个" % len(titles))

        gids = []
        for b in blocks:
            gid = (GROUP_ID.search(b).group(1) if GROUP_ID.search(b) else "?")
            gids.append(gid)
        dup = [k for k, v in collections.Counter(gids).items() if v > 1]
        if dup:
            err.append("组号重复：%s" % "、".join(dup))

        for b in blocks:
            local_err, local_warn = [], []
            info = check_group(
                b, asset_names, panel_names, old_counter,
                lambda m: local_err.append("[%s] %s" % (
                    (GROUP_ID.search(b).group(1) if GROUP_ID.search(b) else "?"), m)),
                lambda m: local_warn.append("[%s] %s" % (
                    (GROUP_ID.search(b).group(1) if GROUP_ID.search(b) else "?"), m)),
                lambda *_: None,
                voice_mode=a.voice_mode, voice_cards=voice_cards)
            err.extend(local_err)
            warn_all.extend(local_warn)
            rows.append(info)
            all_new.extend(info["dialogue"])

        print("  组 %d ｜ 模板 %s" % (len(blocks),
                                   "/".join(sorted(set(r["tpl"] for r in rows[-len(blocks):])))))

    # ── J2 同一角色跨组锚点串必须一字不差
    seen = {}
    for r in rows:
        for sp, anchor in (r.get("anchors") or {}).items():
            seen.setdefault(sp, collections.OrderedDict()).setdefault(anchor, []).append(r["gid"])
    for sp, variants in seen.items():
        if len(variants) > 1:
            detail = "；".join("%s ×%d" % (k, len(v)) for k, v in variants.items())
            err.append("音色锚点跨组不一致（%s）：%s" % (sp, detail))

    # 台词逐字多重集
    if old_counter is not None:
        cn = collections.Counter(all_new)
        if old_counter != cn:
            for k in old_counter:
                if old_counter[k] != cn[k]:
                    err.append("台词不匹配（旧%dx / 新%dx）：%s" % (old_counter[k], cn[k], k))
            for k in cn:
                if k not in old_counter:
                    err.append("新出现台词：%s" % k)
        print("旧台词 %d 条 ｜ 新台词 %d 条" % (sum(old_counter.values()), sum(cn.values())))

    print("")
    print("%-14s %-6s %-5s %-5s %-4s %-4s %-7s %s"
          % ("组号", "模板", "时长", "台词", "字", "图", "通道", "发言"))
    for r in rows:
        print("%-14s %-6s %-5s %-5d %-4d %-4d %-7s %s"
              % (r["gid"], r["tpl"], r["dur"] if r["dur"] is not None else "-",
                 r["lines"], r["chars"], r["pn"],
                 r.get("mode", "-"), "/".join(r["speakers"]) or "—"))

    print("")
    if err:
        print("❌ 错误 %d 条：" % len(err))
        for e in err:
            print("   - %s" % e)
    else:
        print("✅ 结构门全部通过")
    if warn_all:
        print("⚠️ 提醒 %d 条：" % len(warn_all))
        for w in warn_all:
            print("   - %s" % w)

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"files": files, "groups": rows, "errors": err,
                       "warnings": warn_all}, f, ensure_ascii=False, indent=1)
        print("结果已存：%s" % a.json)

    if err:
        return 1
    if warn_all and a.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
