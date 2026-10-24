# script.json 结构

> 一份剧本文件覆盖一个集数区间（通常一批 ≤ 3 集）。
> **JSON 里是细拍（用来计秒、用来过门），Markdown 里是合并后的 △（用来读、用来拍）。** 合并由 `render` 负责。

---

## 顶层

```json
{
  "title": "这次我是猪",
  "source": "这次我是猪",
  "lang": "zh",
  "params": {
    "charsPerSecond": 4.5, "actionSeconds": 2.5, "tolerance": 0.15,
    "maxLineChars": 35, "targetSeconds": 75, "hookWindow": 4
  },
  "episodes": []
}
```

`params` 可整体省略，省略就用上面这组默认值。

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `charsPerSecond` | 4.5 | 中文配音语速，字/秒。按实际配音可调 |
| `actionSeconds` | 2.5 | 一个动作节拍折算秒数 |
| `tolerance` | 0.15 | 时长容差 ±15% |
| `maxLineChars` | 35 | 单句台词字数上限（非空白字符） |
| `targetSeconds` | 75 | 缺省目标秒数。分集可各自覆盖 |
| `hookWindow` | 4 | 钩子具象必须落在全集前几拍内 |

---

## episode

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `ep` | 是 | 集号，正整数，同一文件内不重复 |
| `title` | 是 | 集名。渲染成 `第X集·集名` |
| `targetSeconds` | 是 | 目标秒数。`seed` 会从大纲算好 |
| `hook` | 是 | 开场钩子的说明——头几拍靠什么把人摁住 |
| `cliff` | 是 | 结尾悬念的说明——最后一拍留什么让人点下一集 |
| `hookBeat` | 是 | `[场, 拍]`，钩子具象落在哪一拍 |
| `beatsClaimed` | 是 | 认领的大纲爽点 `type` 数组。没有就 `[]`，**字段本身必须在** |
| `scenes` | 是 | 场次数组 |

`hook` / `cliff` 是**说明不是台词**——描述开场和结尾要达成的效果，具体的戏写在场次里。

`hookBeat` 是**说明给人读，认领给机器查**。钩子说皮箱、开场拍了八拍雾，就是缺了认领这一环。

---

## scene 场次

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `sceneId` | 是 | `S01` 格式，对账 outline 的场景 |
| `title` | 是 | 地点名。渲染成场景头的地点 |
| `time` | 是 | `日` / `夜` / `晨` / `昏` |
| `inOut` | 是 | `内` / `外` |
| `characters` | 是 | 本场出场角色 id（`C01` 格式），对账 outline |
| `props` | 否 | 本场用到的道具 id（`P01` 格式） |
| `flow` | 是 | 节拍流，动作与台词交替，按发生顺序 |

### 场景头怎么来

```
{ "sceneId": "S01", "title": "养殖场猪圈", "time": "日", "inOut": "内" }
        ↓ render
1-1：[日] 养殖场猪圈 内
```

`1-1` 里的第一个数字是集号，第二个是场景在本集中的序号（不是 `S01` 的 01）。

---

## beat 节拍 —— 二选一

### 动作节拍

```json
{ "action": "万集把饲料盆往自己这边扒拉，两头大猪同时撞过来。" }
```

### 台词节拍

```json
{ "speaker": "C01", "line": "我不是来抢食的。", "delivery": "越说越没底气" }
```

| 字段 | 说明 |
| --- | --- |
| `action` | 叙述体画面描述，**一拍一件事**。不许出现引号（`「」『』""`）——台词混进动作就没法计秒 |
| `speaker` | 本场 `characters` 里的角色 id |
| `line` | 台词本体，口语，单句 ≤35 字 |
| `delivery` | 表演提示：语气、动作伴随、潜台词。可省略，建议都写 |
| `mode` | 可选：`vo`（心声/旁白）→ 渲染 `（VO）`；`off`（人未入画但被听见）→ 渲染 `（画外）` |

**一个节拍不能既有 `action` 又有 `line`；两者都没有也不行。**

### 渲染对照

| JSON | Markdown |
| --- | --- |
| `{"action":"…"}` | `△…` |
| 连续多个 action | 合并成一条 `△…`，遇到台词断开 |
| `{"speaker":"C01","line":"…"}` | `万集：…` |
| `{"speaker":"C01","delivery":"…","line":"…"}` | `万集（…）：…` |
| `{"speaker":"C01","mode":"vo","line":"…"}` | `万集（VO）：…` |
| `{"speaker":"C01","mode":"off","line":"…"}` | `万集（画外）：…` |

---

## 时长折算（确定性）

```
台词秒数 = 非空白字符数 ÷ charsPerSecond
动作秒数 = 动作节拍数 × actionSeconds
每集预估 = 全部场次之和
```

必须落在 `targetSeconds × (1 ± tolerance)` 内。

### 容量参考（4.5 字/秒、2.5 秒/拍）

| 目标 | 动作拍 | 台词句 | 台词均长 | 合计节拍 |
| --- | --- | --- | --- | --- |
| 60s | 8 | 10 | 18 字 | 18 |
| **75s** | **9** | **13** | **18 字** | **22** |
| 90s | 10 | 16 | 18 字 | 26 |

> 75 秒只有 22 拍。**别按三分钟的写法来**——那是 50 拍的量。

---

## ID 纪律

- 角色用 `C` 编号（不是名字），场景用 `S` 编号，道具用 `P` 编号
- 渲染时给了 `--outline` 会自动把 `C01` 显示成「万集」
- **数据里存编号，界面上看名字**

---

## 12 道质量门

| # | id | 查什么 |
| --- | --- | --- |
| 1 | `duration` | 每集时长在目标 ±15% 内 |
| 2 | `line-length` | 单句台词 ≤35 字 |
| 3 | `speaker` | 说话人在本场人物里 |
| 4 | `hook-cliff` | 每集钩子与悬念都落在纸面 |
| 5 | `hook-open` | 钩子具象在全集前 4 拍内（`hookBeat` 认领） |
| 6 | `has-action` | 每场至少一个动作节拍 |
| 7 | `action-prose` | 动作叙述体，台词只进 `line` |
| 8 | `beats-claimed` | 大纲爽点逐集认领 |
| 9 | `refs-characters` | 角色引用对账大纲 |
| 10 | `refs-scenes` | 场景／道具对账大纲 |
| 11 | `format-ready` | 场景头四要素齐全（title/time/inOut/sceneId） |
| 12 | `delivery-psych` | 括号里没有心理描写（软门，只警告） |

没给 `--outline` 时，第 8/9/10 门会跳过并明说，不静默放过。

---

## 输出文件

```bash
# 主交付：Word
node {baseDir}/scripts/ir-script.mjs render script.json --docx 剧名-剧本.docx --outline outline.json

# 纯文本（用户明确要 md 时才给）
node {baseDir}/scripts/ir-script.mjs render script.json --md --outline outline.json > 剧名-剧本.md

# 场景清单（给下游，不含镜号与提示词）
node {baseDir}/scripts/ir-script.mjs render script.json --shots --outline outline.json > 剧名-shots.json
```

**最终交付是 `.docx`。** 生成器在 `scripts/docx.mjs`，零依赖（自己拼 ZIP + OOXML）。

Word 排版：文档标题 20pt 居中、集标题黑体 16pt 居中、场景头 12pt 加粗、△ 与对白首行缩进两字、1.5 倍行距、A4（11906×16838 twips，页边距 1440）。

`shots.json` 是给下游的场景清单（景数 / 人数 / 时长），**不含任何镜号与提示词**。
