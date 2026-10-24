---
name: infinite-reincarnation-script
version: 1.0.0
description: |
  给「无限轮回宇宙」写短剧剧本：从一句脑洞（或一篇小说）开始，经过世界篇初始化 → 全剧大纲 → 逐集剧本，
  产出符合母宇宙设定、符合 60–90 秒单集容量、格式可直接投喂分镜的正式剧本，并直接生成 Word 文件。
  三层数据（world.json → outline.json → script.json）全部由脚本做确定性校验：大纲 17 道质量门、剧本 12 道质量门，
  不靠模型自觉。核心卖点是「锚点唯一性」（万集恰好 1 个、苏薇最多 1 个）与「时长确定性折算」（4.5 字/秒、2.5 秒/拍）。
  零依赖、零 API key，用当前会话额度。
  Use when asked to 无限轮回、世界篇、轮回宇宙、万集、苏薇、平行世界剧本、无限流短剧，
  或「写短剧剧本」且明确是这一套系列。
metadata:
  license: Apache-2.0
  requires:
    bins:
      - node          # >= 18，只用标准库，无 npm 依赖
---

# 无限轮回宇宙 · 短剧剧本

`{baseDir}` = 本文件所在目录（= 视频总包里的 `script/`）。脚本在 `{baseDir}/scripts/`，零依赖，`node` 直接跑。

> **这是「一句话做视频」的 ① 号入口。**
> 上游：用户手上没本子。下游：② 漫剧线（`../.prompts/01-漫剧分镜提示词.md`）。
> **接缝只有一处**：`script.json` → `../references/剧本到分镜的交接.md`（一集拆几组、台词怎么折算）。
> **产出落在项目目录，不落本 skill 目录。** 项目骨架用 `../scripts/asset_init.py` 建。

---

## 这个 skill 干什么

**输入**：一句脑洞 / 某个题材 / 一篇参考小说 / 已有的世界篇设定
**输出**：`<剧名>-剧本.docx`（正式剧本，标准 △ 格式）+ `outline.json` + `script.json` + 资产清单 + 场景清单

三段式，每段之间有硬门，过不了不进下一段：

```
A 世界篇初始化 → B 全剧大纲 → C 逐集剧本 → D 交付（Word）
   world.json      outline.json   script.json
   ← 母设七问 →    ← 17 道门 →   ← 12 道门 →
```

**不做的事**：分镜、镜号、单镜时长、首帧提示词、角色出图、配音、剧本评级、Word 以外的对外交付件。
剧本只管到「场次 + 节拍 + 台词」，剩下的都是下一层的事——**下一层怎么接，看 `../references/剧本到分镜的交接.md`。**

---

## 开工前必须读的三样

| 场景 | 读什么 |
| --- | --- |
| 任何阶段 | `{baseDir}/bible/00-母宇宙.md`（一页纸知道什么不能改） |
| 阶段 A | `bible/02-固定资产.md`、`bible/03-角色与锚点.md` |
| 阶段 B | `references/r5-大纲工艺.md`、`references/schema/outline.schema.md` |
| 阶段 C | `references/r6-写戏工艺.md`、`references/r4-格式规范.md`、`references/schema/script.schema.md` |
| 拍板 / 定稿 | `references/r1-观看价值.md`、`references/r7-质检清单.md` |

`bible/` 五份是**外发件**，可以整份贴给任何共创者；`references/` 七份是**内功**，按阶段取用，不用一次读完。

> **bible 是快照。** 项目侧设定更新后，用 `--bible <path>` 指向最新文件，别让包内的旧快照变成真相源。

---

## 阶段 A｜世界篇初始化

**触发**：用户给出新的世界篇想法（一句脑洞、一个题材、一个身份、一篇参考作品）。

**动作**：
1. 按 `bible/00` 确认母设边界，按 `bible/02` 确认固定资产。
2. 按设定 §0.3 的「创作者想法优先」理解意图：核心脑洞是什么、想要什么体验、哪些已定、哪些可自由发挥。
3. 按 §0.4 的九个维度（定位 / 核心创意 / 主角本世 / 世界规则 / 人物关系 / 故事发动机 / 开局 / 范围 / 母宇关联）内部规划。
4. 按 §0.6 的**十项**输出到 `world.json`（结构见 `references/schema/world.schema.md`）。

**七问自检**（`bible/04` + 设定 §10.1），答不出「是」就别进阶段 B：

1. 违反母宇宙根本规则了吗？
2. 无理由改变主角核心人格了吗？
3. 前世能力的使用受当前世界约束了吗？
4. 把局部神明/系统误设成母宇宙最高意志了吗？
5. 锚点处理错了吗（造了第二个正式伴侣）？
6. 提前揭了未确认的终极秘密吗？
7. 万集 / 苏薇 / 系统精灵被重新设计了吗？

**⛔ 停下**：输出后不自动进大纲。等用户确认或修改。

`origin=novel`（小说改编）可跳过 A，直接从原文提取；但**必须**做锚点映射——哪个角色是万集、哪个是苏薇。

---

## 阶段 B｜全剧大纲

### B1 骨架

```bash
node {baseDir}/scripts/ir-outline.mjs seed world.json > outline.json
```

seed 会把万集预置为 `C01`（`anchor: base:wanji`），并把 `world.cast` 里的角色铺进 `characters`。场景、爽点、分集梗概都要你填。

五步，**顺序不能换**（详见 `r5`）：砍线 → 合人 → 收场景 → 排爽点 → 收道具。

```bash
node {baseDir}/scripts/ir-outline.mjs validate outline.json --stage beats
```

**⛔ 拍板三件事**，用户不点头不进 B2：

1. 砍了哪条线（原话是「这意味着：全剧终点是……」）
2. 合了哪些人
3. 大爆点落在第几集

### B2 细版骨架

吸收意见，再过一次 `--stage beats`。用户没意见就直接进 B3。

### B3 分集梗概

每批 **≤ 10 集**。每集三栏：`synopsis`（叙述体）/ `hook` / `suspense`。缺一栏就是没写完。

```bash
node {baseDir}/scripts/ir-outline.mjs validate outline.json --stage full
```

17 门全过才进阶段 C。

---

## 阶段 C｜逐集剧本

```bash
node {baseDir}/scripts/ir-script.mjs seed outline.json --eps 1-3 > script.json
```

seed 从大纲**确定性搬运**：目标秒数、钩子、悬念、待认领爽点。这些事实不要让模型重新想。`scenes` 留空——那才是写戏的活。

**每批 ≤ 3 集。** 剧本是全流程改得最凶的一层，小批量出、快拍板。

写之前读 `r6-写戏工艺.md`，四条最重的：

1. **时长预算先于一切。** 75 秒 ≈ 22 拍（13 句台词 + 9 拍动作）。写超先砍动作，写欠补冲突不补寒暄。
2. **动作要「常见」。** 这条戏最终是视频模型演的，它只演见过千万次的动作。挑担、递东西、站起来放心写；伸篙一挡、睫毛颤、以寸计的位移会崩。
3. **钩子是第一拍，且在运动中给。** 抱着皮箱在雾里跑 ✓；旧皮箱抱在怀里、指节掐白 ✗（静帧留给第二落点）。
4. **每场至少一个动作节拍。** 纯对白的场是广播剧。

```bash
node {baseDir}/scripts/ir-script.mjs validate script.json --outline outline.json
```

**有违规逐条修，改完重跑，直到通过。** 不要绕门。

---

## 阶段 D｜交付

```bash
# 剧本 Word（主交付）
node {baseDir}/scripts/ir-script.mjs render script.json --docx 剧名-剧本.docx --outline outline.json

# 大纲 Word
node {baseDir}/scripts/ir-outline.mjs render outline.json --docx 剧名-大纲.docx

# 资产清单（给角色/场景/道具环节）
node {baseDir}/scripts/ir-outline.mjs assets outline.json > 剧名-资产清单.md

# 场景清单（给分镜环节，不含镜号与提示词）
node {baseDir}/scripts/ir-script.mjs render script.json --shots --outline outline.json > 剧名-shots.json

# 需要纯文本时
node {baseDir}/scripts/ir-script.mjs render script.json --md --outline outline.json > 剧名-剧本.md
```

**最终交给用户的是 `.docx`。** Markdown 只在用户明确要纯文本、或要贴进其它工具时给。

剧本 Word 的排版：集标题黑体 16pt 居中、场景头加粗、△ 与对白首行缩进两字、1.5 倍行距、A4 页面。**打开即可用，不需要再排版。**

---

## 命令速查

| 命令 | 干什么 |
| --- | --- |
| `ir-outline.mjs seed world.json` | 世界篇 → 大纲骨架 |
| `ir-outline.mjs validate outline.json --stage skeleton\|beats\|full` | 17 道门 |
| `ir-outline.mjs checkup outline.json` | 只打印 ✓/✗ 诊断 |
| `ir-outline.mjs render outline.json --docx X.docx` / `--md` | 渲染大纲 |
| `ir-outline.mjs assets outline.json` | 资产清单（脚本算，别手写） |
| `ir-script.mjs seed outline.json --eps 1-3` | 大纲 → 剧本骨架 |
| `ir-script.mjs validate script.json --outline o.json` | 12 道门 |
| `ir-script.mjs checkup script.json --outline o.json` | 诊断 |
| `ir-script.mjs render script.json --docx X.docx` | **主交付** |
| `ir-script.mjs render script.json --md` | 纯文本 |
| `ir-script.mjs render script.json --shots` | 场景清单 |
| `ir-script.mjs stats script.json` | 逐集时长账 |

---

## 质量门速查

**大纲 17 门**：角色档 3 门（主角组 1–5 / 配角 ≤10 / 功能性 ≤10）+ 场景 2 门（主场景上限动态 / 一次性场景有复用方案）+ 道具 1 门 + 爽点 2 门（间隔 ≤3 无真空 / 至少一个 major 且不压最后一集）+ 分集 4 门（第 1 集有钩子 / 三栏齐全 / 三人同框有方案 / 生成难点进预警）+ 引用与叙述体 2 门 + **母设 3 门**：

| 母设门 | 拦什么 |
| --- | --- |
| `anchor-unique` | 第二个万集、第二个苏薇、卖甜却没有苏薇 |
| `core-value` | 大纲说卖「笑」，全篇没有一场笑戏 |
| `mainline-bound` | `mainline=false` 却偷偷揭世界意志 |

**剧本 12 门**：时长 ±15% / 单句 ≤35 字 / 说话人合法 / 钩子悬念落纸 / 钩子前 4 拍 / 每场有动作 / 动作无引号 / 爽点认领 / 角色对账 / 场景对账 / 场景头四要素 / 括号无心理描写（软门）。

没给 `--outline` 时，三道对账门会**明说跳过**，不静默放过。

---

## 铁律（写之前看一遍）

1. **不擅自扩展任务。** 要共创就别直接写全剧；要细纲就别写全部对白；要剧本就别附世界观报告；要定向改就别重写整个故事。
2. **不机械套模板。** 固定三幕、固定反转次数、每集必须打脸、每部必须升级——全部不强制。按当前世界篇真实需要决定。
3. **不预设商业表现。** 可以提高观看意愿，不能断言必然爆款。
4. **正式交付里不混创作过程。** 剧本正文不出现作者分析、优化解释、自评报告。
5. **保护用户的方向。** 与母设冲突时，指出具体冲突 + 给出不破坏核心创意的最小调整。
6. **不提前分镜。** 景别、镜号、机位、焦距——一个字都不进剧本。

---

## 常见错误

| 症状 | 原因 | 治法 |
| --- | --- | --- |
| 每集都超时 | 按三分钟的写法写了 75 秒的剧 | 75 秒只有 22 拍，砍动作拍 |
| 每集都欠时 | 全是短对话 | 补一场冲突，别补寒暄 |
| `hook-open` 一直不过 | `hookBeat` 指到第 5 拍以后 | 把钩子具象挪到前 4 拍 |
| 大纲过不了 `refs` | 角色/场景建了没用 | 要么用，要么删，别留着占位 |
| `core-value` 过不了 | 爽点表没标 `value` | 每条 beat 都写观看价值类型 |
| Word 打不开 | 用了 `--md` 却改后缀 | 必须用 `--docx` 生成 |
| 分集写崩 | 一次写了 20 集 | 每批 ≤10 集（大纲）/ ≤3 集（剧本） |

---

## 自测

```bash
node {baseDir}/scripts/selftest.mjs
```

80 项断言，不调模型、不花额度。**每道门都有一个「故意写违规 → 确认被拦」的用例**——证明它真的会拦。改完脚本先跑这个。

## 自带样例

`{baseDir}/examples/示例世界篇/`：6 集 × 75 秒的完整链路（world.json → outline.json → script.json → 剧本.docx）。
全部质量门通过，当质量基准，也是自测夹具。

另有一张 `EP01_分镜组示例.tsv`——第 1 集切成分镜组的样子（6 组 / 21 镜 / 88 秒，体检零错误零警告）。
**接下一层时对着这张看**，比读十段换算规则快。切法见 `../references/剧本到分镜的交接.md`。
