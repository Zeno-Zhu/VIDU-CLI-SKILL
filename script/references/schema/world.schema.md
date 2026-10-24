# world.json 结构

> 阶段 A 的产物。对应《无限轮回宇宙·短剧共创 设定》0.6 的十项初始化。
> **独立于 outline.json**：世界篇设定跨生命周期，是「另一个 AI 窗口接手时必须先读」的东西。

---

## 顶层

```json
{
  "title": "这次我是猪",
  "origin": "original",
  "lang": "zh",
  "params": { "genre": "荒诞喜剧", "episodes": 12, "targetSeconds": 75, "coreValue": ["笑", "反差"], "mainline": false },
  "positioning": {}, "coreIdea": {}, "protagonist": {}, "worldRules": {},
  "cast": [], "engine": {}, "opening": {}, "scope": {}, "mainlineLink": {},
  "confirmed": [], "suggested": [], "open": []
}
```

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `title` | 是 | 世界篇名 |
| `origin` | 是 | `original`（脑洞原创）或 `novel`（小说改编） |
| `lang` | 否 | 默认 `zh` |
| `params` | 是 | 见下 |

### params

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `genre` | 是 | 题材。**决定爽点类型**，猜错整份废 |
| `episodes` | 是 | 总集数 |
| `targetSeconds` | 是 | 单集目标秒数。默认 75（设定 §4.6 优先 65–80s） |
| `coreValue` | 是 | 核心观看商品数组，如 `["笑","反差"]`、`["甜","成长"]`。**下游 `core-value` 门按它查 beats** |
| `mainline` | 是 | 本篇是否推进轮回主线。`false` 时不许出现 `reveal` |

---

## 十项，逐项对应设定 §0.6

### 一、`positioning` 世界篇定位

```json
{ "name": "", "genre": "", "audience": "", "scale": "", "tone": "" }
```

名称 / 题材（主 + 辅）/ 目标观众与语言文化环境 / 预计集数与时长规模 / 整体气质与主要观看体验。

未确定的制作参数可以留空，不擅自锁死。

### 二、`coreIdea` 核心创意与观看卖点

```json
{ "whyFun": "", "difference": "", "consume": "", "strengthen": "" }
```

`whyFun` 为什么有趣 / `difference` 与同类型有什么不同 / `consume` 观众主要来消费什么 / `strengthen` 最值得做强的那一项。

> 保留创作者原始脑洞。**不要把所有可能性都写进来**，选一条做强。

### 三、`protagonist` 主角本世设定

```json
{
  "nameInEra": "万集", "form": "猪", "identity": "", "assets": "",
  "powerUsed": [], "powerLimits": [], "goal": ""
}
```

`nameInEra` 本世姓名（恒为万集）/ `form` 生命形态与年龄 / `identity` 身份职业家庭社会位置 / `assets` 当前条件与资源 / `powerUsed` 可用的前世知识与能力 / `powerLimits` 受当前世界限制的能力 / `goal` 当前欲望与目标。

**默认已历大量轮回，不强制从零成长。** 需要什么前世经验可以合理设计，不要求补写轮回史。

### 四、`worldRules` 本世界核心设定

```json
{ "era": "", "region": "", "system": "", "limits": [] }
```

时代 / 地域与社会背景 / 力量体系或技术条件 / `limits` 能力限制与制度约束。

只建立当前故事真正需要的内容。现实题材优先继承现实常识，架空题材允许大胆创造，但不得突破母宇宙最高规则。

### 五、`cast` 主要人物与关系

```json
[ { "name": "苏薇", "anchor": "base:suwei", "want": "", "relation": "", "conflict": "", "value": "" } ]
```

| 字段 | 说明 |
| --- | --- |
| `name` | 本世姓名 |
| `anchor` | **四值之一：`base:wanji` / `base:suwei` / `system` / `local`** |
| `want` | 核心性格与主要欲望 |
| `relation` | 与主角的关系 |
| `conflict` | 当前利益与冲突 |
| `value` | 能为故事带来的观看价值 |

**`anchor` 的硬约束：**

- `base:wanji` 有且仅有 1 个
- `base:suwei` ≤ 1 个；`coreValue` 含爱情/甜/情感时必须存在
- `system` ≤ 1 个
- `local` 不限

本篇不需要爱情线时，可以不安排苏薇登场。不为了填满名单强制加人。

### 六、`engine` 核心故事机制 ⛔ 最重要的一项

```json
{ "coreConflict": "", "whyKeepGoing": "", "loopOfValue": "", "aftermath": "" }
```

`coreConflict` 核心矛盾是什么 / `whyKeepGoing` 人物为什么持续行动 / `loopOfValue` 核心玩法怎样反复提供观看价值 / `aftermath` 已有结果怎样产生后续剧情。

**要回答的是：为什么这个世界能持续产生好看的故事？**

只有有趣脑洞却无法继续发展的设定，在这一步就该被发现。

### 七、`opening` 开局与主要高值方向

```json
{ "firstBeatValue": "", "initialSituation": "", "hooks": [] }
```

`firstBeatValue` 第一集最值得展示什么 / `initialSituation` 主角最初面对的问题或机会 / `hooks` 早期可形成的强人物选择、身份反差、关系变化或类型高值场面。

**只定方向和承诺，不写完整第一集。** 不机械规定必须从死亡、重生、冲突、羞辱或反转开始。

### 八、`scope` 故事范围与结局方向

```json
{ "span": "", "ending": "", "longTermOpen": [] }
```

`span` 讲多大范围（一段人生 / 一生 / 多次轮回）/ `ending` 核心结果或终局方向 / `longTermOpen` 适合成为长期故事的部分。

不为了长篇容量强行扩大世界规模。

### 九、`mainlineLink` 母宇宙关联

```json
{ "keepPersonality": true, "anchorUsed": false, "clues": [], "touchesUltimate": false }
```

`keepPersonality` 主角是否保持统一核心人格 / `anchorUsed` 是否涉及固定灵魂锚点 / `clues` 轮回线索 / `touchesUltimate` 是否触碰世界意志或终极秘密。

**不要求每个世界篇都安排轮回主线内容。** `touchesUltimate=false` 时，下游 outline 的 `params.mainline` 应为 `false`，且 beats 不许标 `reveal`。

### 十、确认与开放事项 ⛔ 不许省略

```json
{
  "confirmed": ["创作者明确提供或已锁定的事实"],
  "suggested": ["AI 补充、尚待确认的建议设定"],
  "open": ["当前不需要确定、未来允许自由创作的部分"]
}
```

三者的区别就是 `bible/04` 里的四种事实状态。混用这三栏，等于把候选设定当成了跨世界事实。

---

## 完成条件（设定 §0.8）

1. 创作者的核心想法已被准确理解
2. 有明确的题材和主要观看商品
3. 主角本世身份、主要能力及世界条件能够成立
4. 主要人物和核心矛盾已具备基本运行条件
5. 世界设定能支持预期故事规模
6. 开局已具备值得观看的核心方向
7. 与母宇宙没有无法解释的根本冲突
8. 已确认 / 候选 / 开放得到区分

不要求完整世界历史、全部角色、每一集剧情都已确定。

---

## 之后

`world.json` 通过七问自检后，进入阶段 B：

```bash
node {baseDir}/scripts/ir-outline.mjs seed world.json --eps 12 > outline.json
```
