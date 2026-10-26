#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# (c) manju-vidu-workflow · MJVID:b02c7be960 · 溯源标记，请保留
"""voice_lock_check.py —— 人物音色卡门禁（零计费 · 零依赖）

为什么有这个脚本
    ★ 2026-10-26 实测：Vidu **闲时（nopeak）无法参考音色**。
    ⇒ 角色声线只能靠文字锁：每个角色一份《人物音色卡》，逐组抄一行「锚点串」。
    卡写歪了，成片就是「全员一个嗓子 / 一集换一个人」，后期救不回来。本脚本只管卡。
    ⚠ 但「无法参考音色」≠「没有配音」：闲时平台照样会用原生配音逐句念台词。
      卡管的是"像不像同一个人"，⛔ 不是"有没有声音"；别据此删台词或砍对白。

查什么
    A 完整：九维是否写全（基准音域 / 基频区间 / 虚实占比 / 语速 / 停顿模式 /
            重音习惯 / 语调曲线 / 微观质感 / 齿音强度）
    B 合法：基频是**数字区间**且在人体范围内；语速区间合法；虚实比例能读懂
    C 锚点：每张卡有「锚点串」（≤40 字）和「禁用」一行
    D 禁词：卡里不许出现会**重造声线**的词（磁性嗓音 / 烟嗓 / 播音腔…）
    E 互斥：任意两角色基频区间不重叠（重叠 ≤10 Hz 时语速必须分开）；锚点串不许雷同
    F 命名：文件名 = 音色-<资产名>.txt，且与卡内角色名一致

    G 人设卡片（--card）：九维标签齐不齐 · 卡上「基频区间」的数字与音色卡是否一致 ·
      有没有质量尾缀与负面要求

用法
    python scripts/voice_lock_check.py --dir "<项目>/00_剧本与提示词/_资产提示词"
    python scripts/voice_lock_check.py --file 音色-林桂芳.txt        # 只查一张
    python scripts/voice_lock_check.py --card 人设卡-万集.txt --dir …  # 只查人设卡片
    python scripts/voice_lock_check.py --dir … --json out.json

退出码：0 通过｜1 有错误｜2 输入有问题
"""
from __future__ import annotations

import argparse
import io
import itertools
import json
import os
import re
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

DIMS = ["基准音域", "基频区间", "虚实占比", "语速", "停顿模式",
        "重音习惯", "语调曲线", "微观质感", "齿音强度"]

BAD_WORDS = ["磁性嗓音", "少女音", "御姐音", "烟嗓", "气泡音", "贵族腔",
             "播音腔", "声音变老", "低音炮", "奶音"]

HZ_MIN, HZ_MAX = 60, 450          # 人体说话基频合理范围
SPEED_MIN, SPEED_MAX = 1.5, 8.0   # 字/秒
MAX_OVERLAP_HZ = 10               # 允许的基频接触
MAX_ANCHOR = 40                   # 锚点串字数上限
NUM = re.compile(r"\d+(?:\.\d+)?")


def nums(text):
    return [float(x) for x in NUM.findall(text or "")]


def field(txt, name):
    """取「N 维度：内容」那一行的内容。容忍 1/1、1、1.、1: 等写法。"""
    m = re.search(r"^[^\n]*" + re.escape(name) + r"\s*[：:]\s*(.+)$", txt, re.M)
    return m.group(1).strip() if m else ""


def pair(text):
    """从一段文字里取 (lo, hi)。只有一个数就当 (n, n)。"""
    v = nums(text)
    if not v:
        return None
    if len(v) == 1:
        return v[0], v[0]
    lo, hi = min(v[0], v[1]), max(v[0], v[1])
    return lo, hi


def read_card(path):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    fn = os.path.basename(path)
    name = os.path.splitext(fn)[0]
    if name.startswith("音色-"):
        name = name[len("音色-"):]
    m = re.search(r"【人物音色设定】\s*([^｜|\n]+)", txt)
    inner = m.group(1).strip() if m else ""
    return {"file": fn, "name": name, "inner_name": inner, "text": txt}


def check_one(c, bad, warn, note):
    txt, name = c["text"], c["name"]

    # A 九维
    miss = [d for d in DIMS if not field(txt, d)]
    if miss:
        bad("%s 缺维度：%s" % (name, " / ".join(miss)))

    # F 命名
    if not c["file"].startswith("音色-"):
        bad("%s 文件名应为「音色-<资产名>.txt」" % c["file"])
    if c["inner_name"] and name and c["inner_name"] != name:
        bad("%s 卡内角色名「%s」与文件名不一致" % (c["file"], c["inner_name"]))

    # B 基频 / 语速
    hz = pair(field(txt, "基频区间"))
    if not hz:
        bad("%s 基频区间没写数字（形容词锁不住声线）" % name)
    else:
        lo, hi = hz
        if lo < HZ_MIN or hi > HZ_MAX:
            bad("%s 基频 %g—%g Hz 超人体范围（%d—%d）" % (name, lo, hi, HZ_MIN, HZ_MAX))
        if lo == 0 or hi == 0:
            bad("%s 基频写成了 0" % name)
        if "日常" in field(txt, "基频区间") and not nums(field(txt, "基频区间"))[2:]:
            warn("%s 没写「日常落在多少 Hz」（能把区间收窄成一个人）" % name)

    sp = pair(field(txt, "语速"))
    if not sp:
        bad("%s 语速没写数字（字/秒）" % name)
    else:
        a, b = sp
        if a < SPEED_MIN or b > SPEED_MAX:
            bad("%s 语速 %g—%g 字/秒 不合常理（%g—%g）" % (name, a, b, SPEED_MIN, SPEED_MAX))

    # C 锚点串 + 禁用
    anchor = ""
    m = re.search(r"锚点串[：:]\s*(.+)", txt)
    if not m:
        bad("%s 缺「锚点串」（分镜组要逐字抄这一行）" % name)
    else:
        anchor = m.group(1).strip()
        if len(anchor) > MAX_ANCHOR:
            bad("%s 锚点串 %d 字 > %d 字（每组都抄，太长吃字数）"
                % (name, len(anchor), MAX_ANCHOR))
        if len(anchor) < 6:
            bad("%s 锚点串太短（%s），锁不住声线" % (name, anchor))
    if not re.search(r"禁用[：:]", txt):
        warn("%s 没写「禁用」一行（建议写一条绝不出现的声音特征）" % name)

    # D 禁词（★ 「禁用：」那一行本来就是写"不许出现什么"，要排除掉再扫）
    body = "\n".join(l for l in txt.split("\n") if not re.match(r"^\s*禁用\s*[：:]", l))
    for w in BAD_WORDS:
        if w in body:
            bad("%s 出现禁用词「%s」—— 会让模型另造声线" % (name, w))

    note({"name": name, "hz": hz, "speed": sp, "anchor": anchor,
          "quality": field(txt, "微观质感")})
    return None


def overlap(a, b):
    """两个区间的重叠量；不重叠返回负数。"""
    if not a or not b:
        return -999
    return min(a[1], b[1]) - max(a[0], b[0])


def check_pairs(cards, bad, warn):
    for x, y in itertools.combinations(cards, 2):
        ox = overlap(x["hz"], y["hz"])
        if ox > MAX_OVERLAP_HZ:
            os_ = overlap(x["speed"], y["speed"])
            tip = ""
            if os_ > 0:
                tip = "语速也撞了（重叠 %.1f 字/秒）" % os_
            bad("撞嗓：%s（%s）vs %s（%s）基频重叠 %g Hz%s"
                % (x["name"], fmt_hz(x["hz"]), y["name"], fmt_hz(y["hz"]), ox,
                   "，" + tip if tip else ""))
        elif ox > 0:
            os_ = overlap(x["speed"], y["speed"])
            if os_ > 0.2:
                bad("撞嗓风险：%s vs %s 基频重叠 %g Hz，语速又重叠 %.1f 字/秒"
                    % (x["name"], y["name"], ox, os_))
            else:
                warn("%s 与 %s 基频刚好贴着（重叠 %g Hz），语速已分开，可接受"
                     % (x["name"], y["name"], ox))
        if x["anchor"] and x["anchor"] == y["anchor"]:
            bad("锚点串雷同：%s 与 %s 都是「%s」" % (x["name"], y["name"], x["anchor"]))


def fmt_hz(hz):
    return "%g—%g Hz" % hz if hz else "—"


def fmt_sp(sp):
    return "%g—%g 字/秒" % sp if sp else "—"


# ─────────────────────── G 人设卡片 ───────────────────────
def card_name(txt):
    m = re.search(r"名字\s*[：:]\s*([^\n｜|]+)", txt)
    return m.group(1).strip() if m else ""


def voice_card_hz(voice_dir, name):
    p = os.path.join(voice_dir or "", "音色-%s.txt" % name)
    if not (voice_dir and os.path.isfile(p)):
        return None
    return pair(field(open(p, encoding="utf-8", errors="ignore").read(), "基频区间"))


def check_card(path, voice_dir, bad, warn, note):
    txt = open(path, encoding="utf-8", errors="ignore").read()
    name = card_name(txt) or os.path.basename(path)
    miss = [d for d in DIMS if not re.search(re.escape(d) + r"\s*[：:]", txt)]
    if miss:
        bad("人设卡缺声音维度：%s" % " / ".join(miss))
    if not card_name(txt):
        bad("人设卡没写「名字：」—— 对不上音色卡就没法核")
    if "ultra sharp" not in txt:
        warn("人设卡没贴质量尾缀（clean, smooth, ultra sharp…）")
    if not re.search(r"(【负面】|负面\s*[：:])", txt):
        warn("人设卡没写负面要求")

    hz = pair(field(txt, "基频区间"))
    ref = voice_card_hz(voice_dir, name)
    if not hz:
        bad("人设卡「基频区间」没写数字")
    elif ref:
        if set(hz) != set(ref):
            bad("%s 卡上基频 %s ≠ 音色卡 %s —— 图上和文本必须是同一副嗓子"
                % (name, fmt_hz(hz), fmt_hz(ref)))
        else:
            note(name, hz)
    elif voice_dir:
        bad("%s 找不到 音色-%s.txt，没法核基频" % (name, name))
    else:
        warn("%s 只做了结构检查（没给 --dir，基频没跟音色卡核过）" % name)
    return None


def main():
    ap = argparse.ArgumentParser(description="人物音色卡门禁（闲时通道唯一手段）")
    ap.add_argument("--dir", default="", help="音色卡目录（_资产提示词）")
    ap.add_argument("--file", action="append", default=[], help="单张卡，可重复")
    ap.add_argument("--card", action="append", default=[], help="人设卡片提示词，可重复")
    ap.add_argument("--json", default="", help="结果另存 JSON")
    ap.add_argument("--strict", action="store_true", help="警告也算不过")
    a = ap.parse_args()

    paths = list(a.file)
    if a.dir:
        if not os.path.isdir(a.dir):
            print("[ERROR] 目录不存在：%s" % a.dir)
            return 2
        paths += [os.path.join(a.dir, f) for f in sorted(os.listdir(a.dir))
                  if f.startswith("音色-") and f.lower().endswith(".txt")]
    paths = [p for p in dict.fromkeys(paths) if os.path.isfile(p)]
    cards = [p for p in dict.fromkeys(a.card) if os.path.isfile(p)]
    if len(cards) != len(a.card):
        print("[ERROR] 人设卡片不存在：%s" % "、".join(set(a.card) - set(cards)))
        return 2
    if not paths and not cards:
        print("[ERROR] 没找到音色卡（--dir <…/_资产提示词> 或 --file 音色-<名>.txt）")
        print("        一张卡都没有 ⇒ 这部剧没人锁过声线，闲时出片会一集换一个人。")
        return 2

    err, warn_all, rows, card_rows = [], [], [], []
    for p in paths:
        c = read_card(p)
        check_one(c, lambda m: err.append(m), lambda m: warn_all.append(m),
                  lambda d: rows.append(d))

    if rows:
        print("=" * 72)
        print(" 人物音色卡门禁 · %d 张" % len(rows))
        print("=" * 72)
        print("%-12s %-16s %-16s %s" % ("角色", "基频", "语速", "锚点串"))
        for r in rows:
            print("%-12s %-16s %-16s %s" % (r["name"], fmt_hz(r["hz"]), fmt_sp(r["speed"]),
                                            r["anchor"] or "—"))

        check_pairs(rows, lambda m: err.append(m), lambda m: warn_all.append(m))
        if len(rows) >= 2:
            pairs = [(overlap(x["hz"], y["hz"]), x["name"], y["name"])
                     for x, y in itertools.combinations(rows, 2)]
            pairs = [p for p in pairs if p[0] > -900]
            if pairs:
                worst = min(pairs, key=lambda t: t[0])
                if worst[0] > 0:
                    print("\n最近的一对：%s vs %s，基频重叠 %g Hz" % (worst[1], worst[2], worst[0]))
                else:
                    print("\n最近的一对：%s vs %s，区间差 %g Hz" % (worst[1], worst[2], -worst[0]))

    if cards:
        print("")
        print("=" * 72)
        print(" 人设卡片门禁 · %d 张" % len(cards))
        print("=" * 72)
        for p in cards:
            check_card(p, a.dir, lambda m: err.append(m), lambda m: warn_all.append(m),
                       lambda n, hz: card_rows.append({"name": n, "hz": hz}))
        if card_rows:
            print("%-12s %-16s %s" % ("角色", "卡上基频", "来源"))
            for r in card_rows:
                print("%-12s %-16s %s" % (r["name"], fmt_hz(r["hz"]), "已与音色卡核对"))

    print("")
    if err:
        print("❌ 错误 %d 条：" % len(err))
        for e in err:
            print("   - %s" % e)
    else:
        print("✅ 全部通过（音色卡%s）" % ("／人设卡片" if cards else ""))
    if warn_all:
        print("⚠️ 提醒 %d 条：" % len(warn_all))
        for w in warn_all:
            print("   - %s" % w)

    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump({"cards": [{"name": r["name"], "hz": r["hz"], "speed": r["speed"],
                                  "anchor": r["anchor"]} for r in rows],
                       "errors": err, "warnings": warn_all}, f, ensure_ascii=False, indent=1)
        print("结果已存：%s" % a.json)

    if err:
        return 1
    if warn_all and a.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
