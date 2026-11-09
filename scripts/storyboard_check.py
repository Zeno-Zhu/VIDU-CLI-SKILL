#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分镜组表体检（三种表都认）。

    python scripts/storyboard_check.py "…/EP01_分镜组.tsv"
    python scripts/storyboard_check.py "…/EP01_镜头规划_自己人.tsv" --json out/_体检.json
    python scripts/storyboard_check.py "…/EP01_分镜组.tsv" --strict

认哪三种表：

① **基础九列**（L1）：组号 / 分镜 / 时长 / 景别 / 角度 / 运镜 / 功能 / 内容 / 台词
② **深度八列**（L2）：镜头ID / 剧本单元 / 画面与表演 / 景别 / 机位角度 / 运镜路径 / 视觉落点 / 状态变化
③ **结构三列**（L1 精简）：分镜组ID / 时长 / 原剧本锚点  ← 只能做组级检查，逐镜项自动跳过

判据（唯一口径，见 references/vidu-参数.md）：
  · 组时长 ≤ 16 秒（硬线）；< 6 秒判碎片；6—12 秒提示「能合就合」（一集最多一两组短组）
  · 单镜 ≥ 1.2 秒（硬下限，无例外）
  · 一组优先 4—8 镜，不设死线（<2 判不成立，>8 看内容撑不撑）
  · 空镜+氛围：单组 > 40% 警告；全片 > 25% 警告
  · 单个无水词氛围镜 > 4.5 秒警告
  · 连续 3 镜同景别 / 同机位 / 同运镜 警告（固定机位不算运镜重复）
  · 全片单一景别 > 55% 警告
  · 台词 > 组时长 × 4 字 警告
  · 站位：有站位列时，组内第一镜必须写全，缺了警告

退出码：0 通过（可有警告）｜1 有错误｜2 表读不进来
"""

import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import channel_profile as CP  # noqa: E402

MAX_GROUP = 16.0
TARGET_LOW = 12.0
HARD_LOW = 4.0
MIN_SHOT = 1.2
SHOT_GUIDE_LOW = 4      # 建议线，不是死线
SHOT_GUIDE_HIGH = 10    # 建议线，不是死线
EMPTY_RATIO_GROUP = 0.40
EMPTY_RATIO_ALL = 0.25
EMOTION_MAX = 4.5
SIZE_DOMINANT = 0.55
CHARS_PER_SEC = 4.0

ASSET_NAMES = set()
REQUIRE_ASSETS = False
ASSET_COL = False
FIXED_DUR = None

HEADER_ALIAS = {
    "组号": ["组号", "组", "分镜组", "分镜组id", "group", "组id"],
    "分镜": ["分镜", "镜号", "分镜号", "镜头id", "shot", "镜", "shotid"],
    "时长": ["时长", "秒", "duration", "时长(s)", "时长（s）", "秒数"],
    "景别": ["景别", "大小", "shot_size", "镜别大小"],
    "角度": ["角度", "机位", "机位角度", "视角", "拍摄角度", "方位", "机位/角度"],
    "运镜": ["运镜", "镜头运动", "摄影机运动", "摄像机运动", "运镜路径"],
    "功能": ["功能", "类型", "镜别", "用途"],
    "内容": ["内容", "画面", "画面内容", "描述", "剧情", "画面与表演"],
    "台词": ["台词", "对白", "语音", "说话", "口播", "旁白"],
    "资产": ["出场资产", "资产", "素材", "参考", "引用"],
    "站位": ["站位", "走位", "调度", "人物位置", "blocking"],
    "落点": ["视觉落点", "落点"],
    "锚点": ["原剧本锚点", "锚点", "剧本锚点"],
    "状态": ["状态变化", "状态"],
}

FUNC_MAP = {
    "叙事": "叙事", "动作": "叙事", "情节": "叙事", "事件": "叙事",
    "对白": "对白", "台词": "对白", "对话": "对白",
    "反应": "反应", "表情": "反应", "微表情": "反应",
    "空镜": "空镜", "环境": "空镜", "环境镜": "空镜", "景物": "空镜", "大全景空镜": "空镜",
    "氛围": "氛围", "情绪": "氛围", "纯情绪": "氛围", "抒情": "氛围", "表演": "氛围",
    "转场": "转场", "过渡": "转场",
}

SIZE_ORDER = ["大远景", "远景", "全景", "中全景", "中景", "中近景", "近景", "特写", "大特写"]
SIZE_ALIAS = {"拉开": "全景", "全身": "全景", "过肩": "中近景", "半身": "中景",
              "脸部": "特写", "细节": "特写", "局部": "特写", "双人中景": "中景"}

CJK = re.compile(r"[\u4e00-\u9fff]")
SHOT_ID = re.compile(r"^(\d+)_(\d+)_(\d+)$")

MOVE_RULES = [
    ("微推", ["微推", "轻推", "缓推", "slow push"]),
    ("固定", ["机位固定", "固定", "静止", "不动", "static", "locked", "fixed"]),
    ("手持", ["手持", "handheld"]),
    ("环绕", ["环绕", "绕拍", "orbit"]),
    ("升降", ["升降", "升起", "下降", "crane", "俯仰", "tilt"]),
    ("推", ["推", "push", "zoom in"]),
    ("拉", ["拉", "pull", "zoom out"]),
    ("跟", ["跟", "follow", "tracking"]),
    ("移", ["平移", "横移", "移", "track", "dolly"]),
    ("摇", ["摇", "pan"]),
]


def norm_move(raw):
    s = (raw or "").strip().replace(" ", "").lower()
    if not s:
        return ""
    for canon, keys in MOVE_RULES:
        for k in keys:
            if k in s:
                return canon
    return (raw or "").strip()


class Shot(object):
    def __init__(self, group, name, dur, size, angle, func, content, line, assets, row,
                 move=None, block=""):
        self.group = group
        self.name = name
        self.dur = dur
        self.size = size
        self.angle = angle
        self.func = func
        self.content = content
        self.line = line
        self.assets = assets
        self.row = row
        self.move = move
        self.block = block


def to_float(v):
    if v is None:
        return None
    s = re.sub(r"[^\d.]", "", str(v).strip())
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def norm_func(raw, line, assets):
    if raw:
        k = str(raw).strip().replace(" ", "")
        if k in FUNC_MAP:
            return FUNC_MAP[k], None
        for key, val in FUNC_MAP.items():
            if key in k:
                return val, None
        return "叙事", "未知功能「%s」，按叙事处理" % raw
    if line and line.strip() and line.strip() not in ("-", "—", "无"):
        return "对白", None
    if assets is not None and not assets.strip():
        return "空镜", None
    return "叙事", None


def norm_size(raw):
    s = (raw or "").strip().replace(" ", "")
    if not s:
        return ""
    for k in SIZE_ORDER:
        if k in s:
            return k
    for k, v in SIZE_ALIAS.items():
        if k in s:
            return v
    return s


def read_cells(path):
    raw = open(path, encoding="utf-8-sig").read().splitlines()
    lines = [l for l in raw if l.strip()]
    if not lines:
        raise ValueError("文件是空的")

    if "\t" in lines[0]:
        mode, cells = "tsv", [l.split("\t") for l in lines]
    elif lines[0].strip().startswith("|"):
        mode, cells = "md", []
        for l in lines:
            s = l.strip()
            if not s.startswith("|"):
                continue
            parts = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c or "") for c in parts):
                continue
            cells.append(parts)
    else:
        mode, cells = "csv", [[c.strip() for c in l.split(",")] for l in lines]

    header = [h.strip() for h in cells[0]]
    low = [h.lower().replace(" ", "") for h in header]
    idx = {}
    for key, names in HEADER_ALIAS.items():
        for i, h in enumerate(low):
            if h in [n.lower().replace(" ", "") for n in names]:
                idx[key] = i
                break

    group_only = ("分镜" not in idx) and ("组号" in idx) and ("时长" in idx)
    has_dur = "时长" in idx

    if group_only:
        return cells[1:], header, idx, mode, True, True

    if "分镜" not in idx:
        raise ValueError(
            "表头缺列：分镜\n表头实际是：%s\n"
            "期望三种之一：\n"
            "  ① 组号 分镜 时长 景别 角度 运镜 功能 内容 台词\n"
            "  ② 镜头ID 剧本单元 画面与表演 景别 机位角度 运镜路径 视觉落点 状态变化\n"
            "  ③ 分镜组ID 时长 原剧本锚点"
            % " | ".join(header))
    if "组号" not in idx and not SHOT_ID.match((cells[1][idx["分镜"]] if len(cells) > 1 else "").strip()):
        raise ValueError("表头既没有「组号」，分镜号也不是 1_1_3 这种格式，无法归组：%s"
                         % " | ".join(header))
    if not has_dur:
        print("· 这张表没有「时长」列（典型：5.3 八列镜头规划）⇒ 时长类检查跳过；"
              "要查时长请配 --groups 指向 5.1 三列表", file=sys.stderr)
    return cells[1:], header, idx, mode, False, has_dur


def build_shots(rows, idx):
    shots, notes = [], []
    has_move = "运镜" in idx
    has_group = "组号" in idx
    for n, cells in enumerate(rows, start=2):
        def get(k):
            i = idx.get(k)
            return cells[i].strip() if i is not None and i < len(cells) else ""

        name = get("分镜")
        g = get("组号")
        if not g and SHOT_ID.match(name):
            m = SHOT_ID.match(name)
            g = "%s_%s" % (m.group(1), m.group(2))
        dur = to_float(get("时长")) if "时长" in idx else None
        if not g and not name:
            continue
        if not g or not name:
            notes.append("第 %d 行缺组号或分镜号，已跳过" % n)
            continue
        if "时长" in idx and dur is None:
            notes.append("第 %d 行缺时长，已跳过" % n)
            continue
        line = get("台词")
        assets = get("资产") if "资产" in idx else None
        func, note = norm_func(get("功能"), line, assets)
        if note:
            notes.append("第 %d 行：%s" % (n, note))
        shots.append(Shot(g, name, dur, norm_size(get("景别")), get("角度"),
                          func, get("内容"), line, assets, n,
                          norm_move(get("运镜")) if has_move else None,
                          get("站位") if "站位" in idx else None))
    return shots, notes


def check_groups_only(rows, idx):
    """三列表：只查组时长与组号。"""
    errs, warns, infos = [], [], []
    groups = []
    for n, cells in enumerate(rows, start=2):
        def get(k):
            i = idx.get(k)
            return cells[i].strip() if i is not None and i < len(cells) else ""

        g = get("组号")
        dur = to_float(get("时长"))
        if not g and dur is None:
            continue
        if not g or dur is None:
            errs.append("第 %d 行缺组号或时长" % n)
            continue
        groups.append((g, dur, get("锚点")))

    ids = [g for g, _, _ in groups]
    dup = sorted(set(x for x in ids if ids.count(x) > 1))
    if dup:
        errs.append("组号重复：%s" % "/".join(dup))

    total = sum(d for _, d, _ in groups) or 1e-9
    for g, d, anchor in groups:
        if FIXED_DUR and abs(d - float(FIXED_DUR)) > 1e-6:
            errs.append("组 %s：%.1fs ≠ 固定 %.0fs（本渠道固定档）" % (g, d, float(FIXED_DUR)))
        if d > MAX_GROUP + 1e-6:
            errs.append("组 %s：%.1fs 超过 %.0fs 上限 —— 拆组，别硬压" % (g, d, MAX_GROUP))
        elif d < HARD_LOW:
            errs.append("组 %s：%.1fs 太短 —— 低于 %.0fs 判碎片" % (g, d, HARD_LOW))
        elif d < TARGET_LOW - 1e-6:
            warns.append("组 %s：%.1fs 低于优先档 %.0fs —— 一集最多一两组短组" % (g, d, TARGET_LOW))
        if not anchor:
            warns.append("组 %s：没写原剧本锚点 —— 后面改词无法回溯" % g)
    if groups:
        infos.append("平均每组 %.1fs，共 %d 组，合计 %.1fs" % (total / len(groups), len(groups), total))
        infos.append("★ 三列表没有逐镜信息：单镜时长 / 景别 / 运镜 / 空镜占比这几项没查；"
                     "要出片前建议补 L2 镜头规划")
    return errs, warns, infos, groups


def group_shots(shots):
    order, bucket = [], {}
    for s in shots:
        if s.group not in bucket:
            bucket[s.group] = []
            order.append(s.group)
        bucket[s.group].append(s)
    return [(g, bucket[g]) for g in order]


def check(shots):
    errs, warns, infos = [], [], []
    if REQUIRE_ASSETS and not ASSET_COL:
        errs.append("表头没有「出场资产」列 —— P5 必须写出场资产，否则 P6 无法绑定")
    groups = group_shots(shots)
    has_move = any(s.move is not None for s in shots)
    has_block = any(s.block is not None for s in shots)
    has_dur = all(s.dur is not None for s in shots)

    total_all = sum(s.dur or 0 for s in shots) or 1e-9
    empty_all = sum((s.dur or 0) for s in shots if s.func in ("空镜", "氛围"))

    size_dur = {}
    for s in shots:
        if s.size and s.dur:
            size_dur[s.size] = size_dur.get(s.size, 0.0) + s.dur

    for g, ss in groups:
        total = sum(s.dur or 0 for s in ss)
        tag = "组 %s" % g

        if ASSET_COL:
            used = []
            for s in ss:
                for tok in re.split(r"[,，、;；\s]+", (s.assets or "").strip()):
                    if tok and tok not in used:
                        used.append(tok)
            if not used:
                errs.append("%s：出场资产列为空 —— 每组必填（角色 / 场景 / 道具）" % tag)
            for tok in used:
                base = re.split(r"[：:]", tok)[0]
                if ASSET_NAMES and base not in ASSET_NAMES:
                    errs.append("%s：出场资产「%s」不在资产清单里" % (tag, base))
        elif REQUIRE_ASSETS:
            pass

        if has_dur:
            if FIXED_DUR and abs(total - float(FIXED_DUR)) > 1e-6:
                errs.append("%s：%.1fs ≠ 固定 %.0fs（本渠道固定档）" % (tag, total, float(FIXED_DUR)))
            if total > MAX_GROUP + 1e-6:
                errs.append("%s：组时长 %.1fs 超过 %.0fs 上限 —— 拆组，别硬压" % (tag, total, MAX_GROUP))
            elif total < HARD_LOW:
                errs.append("%s：组时长 %.1fs 太短 —— 低于 %.0fs 判碎片" % (tag, total, HARD_LOW))
            elif total < TARGET_LOW - 1e-6:
                warns.append("%s：组时长 %.1fs 低于优先档 %.0fs —— 一集最多一两组短组" % (tag, total, TARGET_LOW))
        else:
            total = 1e-9

        if len(ss) < 2:
            errs.append("%s：只有 1 个分镜 —— 一组至少 2 镜" % tag)
        elif len(ss) < SHOT_GUIDE_LOW:
            warns.append("%s：只有 %d 个分镜，偏少（建议 4 镜以上）—— 若是短组或一镜到底可以留，"
                         "否则看看能不能补反应镜" % (tag, len(ss)))
        elif len(ss) > SHOT_GUIDE_HIGH:
            avg = (total / len(ss)) if total > 1 else 0
            warns.append("%s：%d 个分镜，超过建议上限 %d（平均 %.1fs 一镜）—— "
                         "确认每镜都有独立信息，不是为碎而碎" % (tag, len(ss), SHOT_GUIDE_HIGH, avg))

        names = [s.name for s in ss]
        dup = set(n for n in names if names.count(n) > 1)
        if dup:
            warns.append("%s：分镜号重复 %s" % (tag, "/".join(sorted(dup))))

        if has_dur:
            for s in ss:
                if s.dur < MIN_SHOT - 1e-9:
                    errs.append("%s/%s：分镜 %.2fs 低于 %.1fs 下限 —— 并进相邻镜或加时长"
                                % (tag, s.name, s.dur, MIN_SHOT))
                if s.func in ("空镜", "氛围") and not s.line.strip() and s.dur > EMOTION_MAX:
                    warns.append("%s/%s：%.1fs 的纯情绪/空镜且无台词 —— 压到 %.1fs 内，或加动作落点"
                                 % (tag, s.name, s.dur, EMOTION_MAX))

            empty = sum(s.dur for s in ss if s.func in ("空镜", "氛围"))
            if empty / total > EMPTY_RATIO_GROUP:
                warns.append("%s：空镜+氛围占 %.0f%%（>%.0f%%）—— 换一个反应镜或动作镜进来"
                             % (tag, empty / total * 100, EMPTY_RATIO_GROUP * 100))

        run_func, run_size, run_angle = 1, 1, 1
        for i in range(1, len(ss)):
            run_func = run_func + 1 if ss[i].func == ss[i - 1].func else 1
            run_size = run_size + 1 if ss[i].size and ss[i].size == ss[i - 1].size else 1
            run_angle = run_angle + 1 if ss[i].angle and ss[i].angle == ss[i - 1].angle else 1
            if run_func >= 3 and ss[i].func in ("空镜", "氛围"):
                warns.append("%s/%s：连续 3 镜都是%s —— 这一段会显得没戏" % (tag, ss[i].name, ss[i].func))
                run_func = 1
            if run_size >= 3:
                warns.append("%s/%s：连续 3 镜同一个景别（%s）—— 中间跳一档" % (tag, ss[i].name, ss[i].size))
                run_size = 1
            if run_angle >= 3:
                warns.append("%s/%s：连续 3 镜机位没变（%s）—— 换个轴侧或反打" % (tag, ss[i].name, ss[i].angle))
                run_angle = 1

        if has_move:
            miss = [s.name for s in ss if not (s.move or "").strip()]
            if miss:
                warns.append("%s：%s 没写运镜 —— 固定也要写「机位固定」" % (tag, "/".join(miss)))
            run_move = 1
            for i in range(1, len(ss)):
                same = ss[i].move and ss[i].move == ss[i - 1].move
                run_move = run_move + 1 if same and ss[i].move != "固定" else 1
                if run_move >= 3:
                    warns.append("%s/%s：连续 3 镜同一个运镜（%s）—— 中间换一个，或改固定"
                                 % (tag, ss[i].name, ss[i].move))
                    run_move = 1

        if has_block:
            # 站位预演：组内第一镜必须写全（谁在哪、朝哪、机位在哪侧），后面可只写变化
            if not (ss[0].block or "").strip():
                warns.append("%s/%s：组内第一镜没写站位 —— 先做站位预演（谁在哪、朝哪、机位在轴线哪侧）"
                             % (tag, ss[0].name))
            miss = [s.name for s in ss[1:] if not (s.block or "").strip()]
            if miss and len(miss) == len(ss) - 1:
                warns.append("%s：整组只有第一镜有站位 —— 后面每镜至少写「变了什么」" % tag)

        kinds = set(s.size for s in ss if s.size)
        if len(kinds) < 2 and len(ss) >= 3:
            warns.append("%s：%d 个分镜只用了一种景别 —— 至少给一个反差镜" % (tag, len(ss)))

        if has_dur:
            chars = sum(len(CJK.findall(s.line)) for s in ss)
            if chars and chars > total * CHARS_PER_SEC:
                warns.append("%s：台词 %d 字，%.1fs 装不下（上限约 %d 字）—— 拆组或砍字"
                             % (tag, chars, total, int(total * CHARS_PER_SEC)))

    if has_dur:
        if empty_all / total_all > EMPTY_RATIO_ALL:
            warns.append("全片：空镜+氛围占 %.0f%%（>%.0f%%）—— 空镜多了会像 MV，不像剧"
                         % (empty_all / total_all * 100, EMPTY_RATIO_ALL * 100))
        if size_dur:
            top, topd = max(size_dur.items(), key=lambda kv: kv[1])
            if topd / total_all > SIZE_DOMINANT:
                warns.append("全片：%s 占 %.0f%%（>%.0f%%）—— 单一景别过重，注意拉远或推近"
                             % (top, topd / total_all * 100, SIZE_DOMINANT * 100))

    if len(groups) > 1 and has_dur:
        infos.append("平均每组 %.1fs，共 %d 组" % (total_all / len(groups), len(groups)))
    if not has_dur:
        infos.append("★ 本次没有逐镜时长：单镜下限 / 组时长 / 空镜占比 / 台词密度均未查")

    return errs, warns, infos, groups, total_all, empty_all


def main():
    global MAX_GROUP, TARGET_LOW, HARD_LOW, SHOT_GUIDE_HIGH, ASSET_NAMES, REQUIRE_ASSETS, ASSET_COL, FIXED_DUR
    ap = argparse.ArgumentParser(description="分镜组表体检：时长 / 粒度 / 空镜 / 景别角度 / 运镜 / 出场资产")
    ap.add_argument("table", help="分镜组表（.tsv / .md / .csv）")
    ap.add_argument("--json", default="", help="把体检结果另存成 JSON")
    ap.add_argument("--strict", action="store_true", help="警告也算不过（退出码 1）")
    ap.add_argument("--quiet", action="store_true", help="只打结论，不打每组明细")
    ap.add_argument("--config", default="", help="项目配置.json；不给就向上找")
    ap.add_argument("--max-group", type=float, default=None, help="覆盖单组上限（秒）")
    ap.add_argument("--min-group", type=float, default=None, help="覆盖组最小（秒）")
    ap.add_argument("--prefer-min", type=float, default=None, help="覆盖优先档下限（秒）")
    ap.add_argument("--shot-max", type=int, default=None, help="覆盖镜数建议上限（只告警）")
    ap.add_argument("--assets", default="", help="资产清单.json：给了就核出场资产名")
    ap.add_argument("--require-assets", action="store_true", help="没有出场资产列即判错")
    a = ap.parse_args()

    cfg_path = a.config or CP.find_config(a.table)
    if cfg_path and os.path.isfile(cfg_path):
        p = CP.load_config(cfg_path)
        MAX_GROUP = float(p["group_max_s"])
        HARD_LOW = float(p["group_min_s"])
        TARGET_LOW = float((p.get("group_prefer_s") or [HARD_LOW])[0])
        SHOT_GUIDE_HIGH = int(p.get("shots_soft_max", SHOT_GUIDE_HIGH))
        FIXED_DUR = p.get("fixed_duration_s")
    if a.max_group is not None:
        MAX_GROUP = a.max_group
    if a.min_group is not None:
        HARD_LOW = a.min_group
    if a.prefer_min is not None:
        TARGET_LOW = a.prefer_min
    if a.shot_max is not None:
        SHOT_GUIDE_HIGH = a.shot_max
    if a.assets:
        if not os.path.isfile(a.assets):
            print("[BLOCK] 找不到资产清单：%s" % a.assets)
            return 2
        inv = json.load(open(a.assets, encoding="utf-8"))
        ASSET_NAMES = {x.get("name") for x in inv.get("assets", []) if x.get("name")}
        ASSET_NAMES |= {x.get("id") for x in inv.get("assets", []) if x.get("id")}
    REQUIRE_ASSETS = a.require_assets

    if not os.path.isfile(a.table):
        print("找不到文件：%s" % a.table)
        return 2
    try:
        rows, header, idx, mode, group_only, has_dur = read_cells(a.table)
    except ValueError as e:
        print("[表读不进来] %s" % e)
        return 2

    ASSET_COL = "资产" in idx
    print("分镜组表体检  %s" % a.table)

    if group_only:
        errs, warns, infos, groups = check_groups_only(rows, idx)
        if REQUIRE_ASSETS:
            errs.insert(0, "三列结构表没有「出场资产」列 —— P5 必须写，否则 P6 无法绑定")
        print("组 %d（三列结构表）" % len(groups))
        if not a.quiet:
            print("")
            print("%-12s %-8s %s" % ("组号", "时长", "锚点"))
            for g, d, anchor in groups:
                flag = "  ← 超长" if d > MAX_GROUP else ""
                print("%-12s %-8.1f %s%s" % (g, d, (anchor or "—")[:40], flag))
        total_all = empty_all = 0
        shots = []
    else:
        shots, notes = build_shots(rows, idx)
        if not shots:
            print("没读到有效行。表头是：%s" % " | ".join(header))
            return 2
        errs, warns, infos, groups, total_all, empty_all = check(shots)
        if all(x.dur is not None for x in shots):
            print("组 %d ｜ 分镜 %d ｜ 总时长 %.1fs = %.2f 分 ｜ 空镜+氛围 %.0f%%"
                  % (len(groups), len(shots), total_all, total_all / 60,
                     empty_all / total_all * 100))
        else:
            print("组 %d ｜ 分镜 %d ｜（本表无逐镜时长）" % (len(groups), len(shots)))
        if mode == "md":
            print("（读的是 Markdown 表格）")
        for n in notes[:5]:
            print("  注：%s" % n)
        if not a.quiet:
            print("")
            print("%-8s %-4s %-8s %-8s %s" % ("组号", "镜数", "时长", "空镜%", "景别"))
            for g, ss in groups:
                total = sum(s.dur for s in ss) or 1e-9
                empty = sum(s.dur for s in ss if s.func in ("空镜", "氛围"))
                kinds = "/".join(sorted(set(s.size for s in ss if s.size)))
                flag = "  ← 超长" if total > MAX_GROUP else ""
                print("%-8s %-4d %-8.1f %-8s %s%s"
                      % (g, len(ss), total, "%.0f%%" % (empty / total * 100),
                         kinds or "—", flag))

    if errs:
        print("")
        print("✗ 错误 %d 条（必须改完才能提交）" % len(errs))
        for e in errs:
            print("   - %s" % e)
    if warns:
        print("")
        print("! 警告 %d 条（能不改，但改了更像片子）" % len(warns))
        for w in warns:
            print("   - %s" % w)
    if infos:
        print("")
        for i in infos:
            print("· %s" % i)

    print("")
    if errs:
        print("结论：%d 处结构错误（BLOCK），先改。" % len(errs))
    elif warns and a.strict:
        print("结论：无结构错误，但 %d 条警告；--strict 下判不通过。" % len(warns))
    elif warns:
        print("结论：PASS。%d 条警告可以改，也可以留。" % len(warns))
    else:
        print("结论：PASS，干净。")

    if a.json:
        payload = {
            "table": os.path.abspath(a.table),
            "mode": "group_only" if group_only else "shot_level",
            "groups": (len(groups) if group_only else len(groups)),
            "shots": len(shots),
            "total_seconds": round(total_all, 2),
            "empty_ratio": (round(empty_all / total_all, 4) if total_all else 0),
            "errors": errs,
            "warnings": warns,
            "per_group": [
                {"组号": g, "镜数": len(ss),
                 "时长": round(sum(s.dur for s in ss), 2),
                 "空镜占比": round(sum(s.dur for s in ss if s.func in ("空镜", "氛围"))
                               / (sum(s.dur for s in ss) or 1e-9), 3)}
                for g, ss in groups
            ] if not group_only else [
                {"组号": g, "时长": d, "锚点": anchor} for g, d, anchor in groups
            ],
        }
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print("体检结果已存：%s" % a.json)

    if errs:
        return 2
    if warns and a.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
