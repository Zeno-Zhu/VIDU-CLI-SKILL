# outline.json 结构

> 大纲的载体。**模型只管填 JSON**，Markdown 与资产清单由 `render` / `assets` 生成。
> 五件套：改编说明、人物表、场景表、爽点表、分集梗概。第六件（资产清单）永远由脚本算。

---

## 顶层

```json
{
  "source": "这次我是猪",
  "origin": "original",
  "params": {
    "episodes": 12, "targetSeconds": 75, "genre": "荒诞喜剧",
    "adaptMode": "抽核", "coreValue": ["笑", "反差"],
    "mainline": false, "preferences": [], "thresholds": {}
  },
  "adaptation": {},
  "characters": [], "scenes": [], "props": [], "beats": [], "episodes": []
}
```

## params

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `episodes` | 是 | 总集数。分集数量必须与它一致 |
| `targetSeconds` | 是 | 单集目标秒数。默认 75 |
| `genre` | 是 | 题材，决定爽点类型 |
| `adaptMode` | 是 | `忠实` / `抽核` / `借壳`。`origin=original` 时填 `抽核` 即可 |
| `coreValue` | 是 | 核心观看商品数组，应继承自 `world.json` |
| `mainline` | 是 | 本篇是否推进轮回主线 |
| `preferences` | 否 | 用户点名要保的角色、戏 |
| `thresholds` | 否 | 覆盖质量门阈值，见下 |

### thresholds 可覆盖项

| 键 | 默认 | 说明 |
| --- | --- | --- |
| `maxLeads` | 5 | 主角组上限（下限恒为 1） |
| `maxSupport` | 10 | 重要配角上限 |
| `maxFunctional` | 10 | 功能性角色上限 |
| `maxBeatGap` | 3 | 相邻爽点最大间隔（集） |
| `maxProps` | 8 | 叙事道具上限 |
| `maxPrimaryScenes` | 动态 | 缺省 `4 + ⌈集数/10⌉`，夹在 5–15。显式给出才覆盖 |

**短篇（20–30 集）建议收紧角色档**：默认值是按 60 集以上给的。

---

## adaptation 改编说明

```json
{
  "core": "一句话核心",
  "keep": [ { "what": "", "why": "", "evidence": "原文逐字片段" } ],
  "cut":  [ { "what": "", "why": "" } ],
  "merge":[ { "what": "", "why": "" } ],
  "risks":[ { "what": "", "plan": "" } ],
  "cutNote": "这意味着：全剧终点是……",
  "mergeNote": "主角组入选理由：谁有完整转变弧"
}
```

| 规则 | 说明 |
| --- | --- |
| `core` | 必填，一句话 |
| `keep` | 至少一条。`origin=novel` 时建议附 `evidence`（原文逐字片段）——防凭印象改编 |
| `cut` | `adaptMode` 不是「忠实」时不能为空 |
| `cutNote` / `mergeNote` | 给了就不能是空字符串。这两句会出现在大纲最前面的「关键决策」 |

`origin=original` 时，`cut` 的对象是**脑洞的其它可能性**，不是小说情节。`evidence` 可以省略。

---

## characters 人物表

```json
{ "id": "C01", "name": "万集", "role": "男主", "tier": "lead",
  "anchor": "base:wanji", "arc": "从被人宰的猪，到掌控整条产业链",
  "from": ["原创"] }
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | `C01` 格式，全局唯一 |
| `name` | 是 | 本世姓名。功能性角色用称呼标签（「急诊医生」） |
| `role` | 是 | 定位一句话 |
| `tier` | 是 | `lead` / `support` / `functional` |
| `anchor` | 是 | `base:wanji` / `base:suwei` / `system` / `local` |
| `arc` | lead / support 必填 | 人物弧。`functional` 可省 |
| `from` | 是 | 非空数组：原著对应谁 / 合并了谁 / 纯原创写 `["原创"]` |

### tier 三档

| tier | 是谁 | 上限 | 规则 |
| --- | --- | --- | --- |
| `lead` | 主角组（男女主 + 主反派） | 1–5 | `arc` 必填 |
| `support` | 有名字的重要配角 | ≤10 | `arc` 必填 |
| `functional` | 功能性角色 | ≤10 | **占脸不占名**：`name` 用称呼标签，`arc` 可省 |

无名背景人不进表、不追踪、不限量。

### anchor 硬约束（`anchor-unique` 门）

- `base:wanji` **恰好 1 个**
- `base:suwei` **≤1 个**；`coreValue` 含「爱情 / 甜 / 情感 / 恋」时必须存在
- `system` ≤1 个
- `local` 不限

---

## scenes 场景表

```json
{ "id": "S01", "name": "养殖场猪圈", "primary": true, "reusePlan": "" }
```

- `id` 格式 `S01`，全局唯一；`name` 必填；`primary` 必填布尔
- **全剧只出现一次的场景必须带 `reusePlan`**（复用哪个现有环境资产、换什么时段天气改出来）

主场景上限随集数动态：`4 + ⌈集数/10⌉`，夹在 5–15。

---

## props 叙事道具（可选）

```json
{ "id": "P01", "name": "饲料记录本", "function": "决定万集被送走的死期", "beatIds": ["B03"] }
```

- `id` 格式 `P01`；`name` 必填
- **`function` 必填**——这件物件在戏里承载什么。填不出来说明它不是叙事道具，是场景陈设
- `beatIds` 可选，写了必须指向真实存在的 beat id
- 上限 8 件。**只收有特写、跨集出现、承载剧情的**
- 分集用 `episodes[].propIds` 引用；没有一集引用的道具会被 `refs` 门点名

**判据：它坏了、丢了、被换掉，剧情会不会塌？** 会塌才是道具。

---

## beats 爽点表

```json
{ "id": "B01", "type": "身份反差", "weight": "major", "episode": 2,
  "value": "反差", "setup": "所有人当他是待宰的猪",
  "payoff": "他用猪的身份调动了整条运输线", "reveal": "" }
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `id` | 是 | `B01` 格式 |
| `type` | 是 | 自由文本（打脸/揭破/反差/甜/成长…） |
| `weight` | 是 | `major` / `minor` |
| `episode` | 是 | **唯一数据源**。分集不再列 beatIds |
| `value` | 是 | 观看价值类型：爽 / 笑 / 甜 / 痛 / 怒 / 奇观 / 悬念 / 反差 / 成长 |
| `setup` | 是 | 前面怎么铺 |
| `payoff` | 是 | 具体兑现成什么场面 |
| `reveal` | 否 | `世界意志` / `终极秘密`。`params.mainline=false` 时不许出现 |

### 硬规则（`beat-gap` / `beat-major` / `core-value` / `mainline-bound`）

- 相邻爽点间隔 ≤ `maxBeatGap`，开头结尾无真空
- 至少一个 `major`，且最早的 `major` 不能落在最后一集
- `coreValue` 每一项在 `value` 里的出现次数 ≥ `max(1, ⌈集数/10⌉)`
- `mainline=false` 时 `reveal` 必须为空

---

## episodes 分集梗概

```json
{ "ep": 1, "synopsis": "叙述体梗概", "hook": "【钩子】",
  "suspense": "【悬念】", "sceneIds": ["S01"], "characterIds": ["C01","C02"],
  "propIds": [], "crowdPlan": "", "warnings": [], "powerNote": "" }
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `ep` | 是 | 从 1 连续编号，总数 = `params.episodes` |
| `synopsis` | 是 | 这一集发生了什么。**叙述体**，出现引号对白会被 `prose` 门拦 |
| `hook` | 是 | 【钩子】让人点下一集的那个问题 |
| `suspense` | 是 | 【悬念】埋着没解的线 |
| `sceneIds` | 是 | 必须指向已登记的场景 |
| `characterIds` | 是 | 必须指向已登记的角色 |
| `propIds` | 否 | 写了 `props` 才有意义 |
| `crowdPlan` | 条件必填 | `characterIds ≥ 3` 时必须写同框拆解方案 |
| `warnings` | 条件必填 | 梗概扫到生成难点关键词时必须列：`雨戏` `肢体接触` `人群` `手部特写` |
| `powerNote` | 否 | 本集用到前世能力时，一句说明为何在当前世界成立（对应 bible R4） |

### crowdPlan 是代理指标

校验按 `characterIds` 人数判。三人实际不同框（分处不同场次）时，把这事实写成方案即可：「三人分处两场，无同框，分场拍」，照样通过。

---

## 校验分档

```bash
node {baseDir}/scripts/ir-outline.mjs validate outline.json --stage skeleton
node {baseDir}/scripts/ir-outline.mjs validate outline.json --stage beats
node {baseDir}/scripts/ir-outline.mjs validate outline.json --stage full

# 渲染
node {baseDir}/scripts/ir-outline.mjs render outline.json --docx 剧名-大纲.docx
node {baseDir}/scripts/ir-outline.mjs render outline.json --md
node {baseDir}/scripts/ir-outline.mjs assets outline.json > 剧名-资产清单.md
```

| stage | 查哪些门 | 何时过 |
| --- | --- | --- |
| `skeleton` | 人物档 + 场景 + 道具 + 锚点唯一性 | 骨架初稿 |
| `beats` | skeleton + 爽点间隔/major + 核心商品 + 主线边界 | **写分集之前必须过** |
| `full` | 全部 17 门 | 交付前 |

爽点间隔和 major 时机错了，分集写完全废。所以 `beats` 是硬门。

---

## 17 道质量门速查

| # | id | 查什么 |
| --- | --- | --- |
| 1 | `characters-lead` | 主角组 1–5 |
| 2 | `characters-support` | 重要配角 ≤10 |
| 3 | `characters-functional` | 功能性角色 ≤10 |
| 4 | `scenes-cap` | 主场景 ≤ 动态上限 |
| 5 | `scene-reuse` | 一次性场景有 reusePlan |
| 6 | `props-cap` | 道具 ≤8 |
| 7 | `beat-gap` | 爽点间隔 ≤3，头尾无真空 |
| 8 | `beat-major` | 有 major，最早 major 不在最后一集 |
| 9 | `hook-ep1` | 第 1 集有钩子 |
| 10 | `episode-three` | 每集三栏齐全 |
| 11 | `crowd-plan` | 三人同框有拆解 |
| 12 | `warnings` | 生成难点进预警 |
| 13 | `refs` | 引用完整，无失业角色/空转场景/零集道具 |
| 14 | `prose` | 叙述体无对白 |
| 15 | `anchor-unique` | 锚点唯一性 |
| 16 | `core-value` | 核心商品认领 |
| 17 | `mainline-bound` | 主线边界 |
