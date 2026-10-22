#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分镜组表体检。

只管四件事：时长合不合规、分镜切得够不够细、空镜和纯情绪有没有拖、景别与机位有没有一路平到底。

用法：
    python scripts/storyboard_check.py out/分镜组表.tsv
    python scripts/storyboard_check.py out/分镜组表.tsv --json out/_体检.json
    python scripts/storyboard_check.py out/分镜组表.tsv --strict

表头（制表符分隔，顺序可变；Markdown 表格也能读）：

    组号  分镜  时长  景别  角度  功能  内容  台词  资产

- 组号 / 分镜 / 时长 必填，其余缺了照样能跑，只是对应检查会跳过
- 时长单位秒，写 4、4.0、4s 都行
- 功能取值：叙事 / 对白 / 反应 / 空镜 / 氛围 / 转场（缺省按台词与资产推断）

退出码：0 通过（可有警告）｜1 有错误｜2 表读不进来
"""

import argparse
import json
import os
import re
import sys

MAX_GROUP = 16.0      # 组时长上限，硬线
TARGET_LOW = 12.0     # 目标下限，低于它提示合并
HARD_LOW = 6.0        # 低于这个基本是碎片，判错
MIN_SHOT = 1.2        # 单分镜下限
MAX_SHOTS = 6         # 单组镜数建议上限
EMPTY_RATIO_GROUP = 0.40   # 单组空镜+氛围时长占比
EMPTY_RATIO_ALL = 0.25     # 全片空镜+氛围时长占比
EMOTION_MAX = 4.5          # 单个无水词的氛围镜上限
SIZE_DOMINANT = 0.55       # 全片单一景别占比上限
CHARS_PER_SEC = 3.2        # 中文台词语速上限（含停顿），用于判断塞不塞得下

HEADER_ALIAS = {
    "组号": ["组号", "组", "分镜组", "group", "组id", "组ID"],
    "分镜": ["分镜", "镜号", "分镜号", "shot", "镜"],
    "时长": ["时长", "秒", "duration", "时长(s)", "时长（s）", "秒数"],
    "景别": ["景别", "大小", "shot_size", "镜别大小"],
    "角度": ["角度", "机位", "机位角度", "视角", "拍摄角度", "方位"],
    "功能": ["功能", "类型", "镜别", "用途"],
    "内容": ["内容", "画面", "画面内容", "描述", "剧情"],
    "台词": ["台词", "对白", "语音", "说话", "口播", "旁白"],
    "资产": ["资产", "素材", "参考", "引用"],
    "组时长": ["组时长", "组总时长"],
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
SIZE_ALIAS = {
    "拉开": "全景", "全身": "全景", "过肩": "中近景", "半身": "中景",
    "脸部": "特写", "细节": "特写", "局部": "特写",
}

CJK = re.compile(r"[\u4e00-\u9fff]")


class Shot(object):
    def __init__(self, group, name, dur, size, angle, func, content, line, assets, row):
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


def to_float(v):
    if v is None:
        return None
    s = str(v).strip()
    s = re.sub(r"[^\d.]", "", s)
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
    if not (assets or "").strip():
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
        mode = "tsv"
        cells = [l.split("\t") for l in lines]
    elif lines[0].strip().startswith("|"):
        mode = "md"
        cells = []
        for l in lines:
            s = l.strip()
            if not s.startswith("|"):
                continue
            parts = [c.strip() for c in s.strip("|").split("|")]
            if all(re.fullmatch(r":?-{2,}:?", c or "") for c in parts):
                continue
            cells.append(parts)
    else:
        mode = "csv"
        cells = [[c.strip() for c in l.split(",")] for l in lines]

    header = [h.strip() for h in cells[0]]
    idx = {}
    for key, names in HEADER_ALIAS.items():
        for i, h in enumerate(header):
            if h in names:
                idx[key] = i
                break
    missing = [k for k in ("组号", "分镜", "时长") if k not in idx]
    if missing:
        raise ValueError("表头缺列：%s\n表头实际是：%s\n期望至少包含：组号 分镜 时长\n"
                         "推荐整表头：组号 分镜 时长 景别 角度 功能 内容 台词 资产"
                         % ("、".join(missing), " | ".join(header)))
    return cells[1:], header, idx, mode


def build_shots(rows, idx):
    shots, notes = [], []
    for n, cells in enumerate(rows, start=2):
        def get(k):
            i = idx.get(k)
            return cells[i].strip() if i is not None and i < len(cells) else ""

        g = get("组号")
        name = get("分镜")
        dur = to_float(get("时长"))
        if not g and not name and dur is None:
            continue
        if not g or not name or dur is None:
            notes.append("第 %d 行缺组号/分镜/时长，已跳过" % n)
            continue
        line = get("台词")
        assets = get("资产")
        func, note = norm_func(get("功能"), line, assets)
        if note:
            notes.append("第 %d 行：%s" % (n, note))
        shots.append(Shot(g, name, dur, norm_size(get("景别")), get("角度"),
                          func, get("内容"), line, assets, n))
    return shots, notes


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
    groups = group_shots(shots)

    total_all = sum(s.dur for s in shots) or 1e-9
    empty_all = sum(s.dur for s in shots if s.func in ("空镜", "氛围"))

    size_dur = {}
    for s in shots:
        if s.size:
            size_dur[s.size] = size_dur.get(s.size, 0.0) + s.dur

    for g, ss in groups:
        total = sum(s.dur for s in ss)
        tag = "组 %s" % g

        if total > MAX_GROUP + 1e-6:
            errs.append("%s：组时长 %.1fs 超过 %.0fs 上限 —— 拆组，别硬压" % (tag, total, MAX_GROUP))
        elif total < HARD_LOW:
            errs.append("%s：组时长 %.1fs 太短 —— 至少 %.0fs，最好 12–16s" % (tag, total, HARD_LOW))
        elif total < TARGET_LOW - 1e-6:
            warns.append("%s：组时长 %.1fs 低于 12s —— 能合就并进相邻组" % (tag, total))

        if len(ss) < 2:
            errs.append("%s：只有 1 个分镜 —— 一组至少要 2 镜，推荐 3–5 镜" % tag)
        elif len(ss) > MAX_SHOTS:
            warns.append("%s：%d 个分镜偏多 —— 单镜会碎到 2s 以下，建议 3–5 镜" % (tag, len(ss)))

        names = [s.name for s in ss]
        dup = set(n for n in names if names.count(n) > 1)
        if dup:
            warns.append("%s：分镜号重复 %s" % (tag, "/".join(sorted(dup))))

        for s in ss:
            if s.dur < MIN_SHOT - 1e-9:
                errs.append("%s/%s：分镜 %.2fs 低于 %.1fs 下限 —— 并进相邻镜或加时长"
                            % (tag, s.name, s.dur, MIN_SHOT))
            if s.func in ("空镜", "氛围") and not s.line.strip() and s.dur > EMOTION_MAX:
                warns.append("%s/%s：%.1fs 的纯情绪/空镜且无台词 —— 压到 %.1fs 内，或加一个动作落点"
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

        kinds = set(s.size for s in ss if s.size)
        if len(kinds) < 2 and len(ss) >= 3:
            warns.append("%s：%d 个分镜只用了一种景别 —— 至少给一个反差镜" % (tag, len(ss)))

        chars = sum(len(CJK.findall(s.line)) for s in ss)
        if chars and chars > total * CHARS_PER_SEC:
            warns.append("%s：台词 %d 字，%.1fs 装不下（上限约 %d 字）—— 拆组或砍字"
                         % (tag, chars, total, int(total * CHARS_PER_SEC)))

    if empty_all / total_all > EMPTY_RATIO_ALL:
        warns.append("全片：空镜+氛围占 %.0f%%（>%.0f%%）—— 空镜多了会像 MV，不像剧"
                     % (empty_all / total_all * 100, EMPTY_RATIO_ALL * 100))

    if size_dur:
        top, topd = max(size_dur.items(), key=lambda kv: kv[1])
        if topd / total_all > SIZE_DOMINANT:
            warns.append("全片：%s 占 %.0f%%（>%.0f%%）—— 单一景别过重，注意拉远或推近"
                         % (top, topd / total_all * 100, SIZE_DOMINANT * 100))

    if len(groups) > 1:
        avg = total_all / len(groups)
        infos.append("平均每组 %.1fs，共 %d 组" % (avg, len(groups)))

    return errs, warns, infos, groups, total_all, empty_all


def main():
    ap = argparse.ArgumentParser(description="分镜组表体检：时长 / 粒度 / 空镜 / 景别角度")
    ap.add_argument("table", help="分镜组表（.tsv / .md / .csv）")
    ap.add_argument("--json", default="", help="把体检结果另存成 JSON")
    ap.add_argument("--strict", action="store_true", help="警告也算不过")
    ap.add_argument("--quiet", action="store_true", help="只打结论，不打每组明细")
    a = ap.parse_args()

    if not os.path.isfile(a.table):
        print("找不到文件：%s" % a.table)
        return 2

    try:
        rows, header, idx, mode = read_cells(a.table)
    except ValueError as e:
        print("[表读不进来] %s" % e)
        return 2

    shots, notes = build_shots(rows, idx)
    if not shots:
        print("没读到有效行。表头是：%s" % " | ".join(header))
        return 2

    errs, warns, infos, groups, total_all, empty_all = check(shots)

    print("分镜组表体检  %s" % a.table)
    print("组 %d ｜ 分镜 %d ｜ 总时长 %.1fs = %.2f 分 ｜ 空镜+氛围 %.0f%%"
          % (len(groups), len(shots), total_all, total_all / 60,
             empty_all / total_all * 100))
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
        print("结论：%d 处错误，先改。" % len(errs))
    elif warns and a.strict:
        print("结论：无错误，但 %d 条警告；--strict 下判不通过。" % len(warns))
    elif warns:
        print("结论：过线。%d 条警告可以改，也可以留。" % len(warns))
    else:
        print("结论：干净。")

    if a.json:
        payload = {
            "table": os.path.abspath(a.table),
            "groups": len(groups),
            "shots": len(shots),
            "total_seconds": round(total_all, 2),
            "empty_ratio": round(empty_all / total_all, 4),
            "errors": errs,
            "warnings": warns,
            "per_group": [
                {"组号": g, "镜数": len(ss),
                 "时长": round(sum(s.dur for s in ss), 2),
                 "空镜占比": round(sum(s.dur for s in ss if s.func in ("空镜", "氛围"))
                               / (sum(s.dur for s in ss) or 1e-9), 3)}
                for g, ss in groups
            ],
        }
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=1)
        print("体检结果已存：%s" % a.json)

    if errs:
        return 1
    if warns and a.strict:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
