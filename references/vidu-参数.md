# Vidu 参数（唯一口径 · 2026-10-24 对齐）

> ★ 本文件是**全包唯一的参数口径**。任何文档、脚本、提示词规范里的数字，与这里不一致，以这里为准。
> 机制细节（为什么、怎么抓到的）→ `vidu-平台机制.md`；这里只给**取值和边界**。

---

## 〇、一句话版本

| 项 | 值 |
|---|---|
| 视频模型 | **Vidu Q4**，`model_version = "3.4"` |
| 一条任务 = | **一个分镜组** |
| 单组时长 | **1–16 秒**，**硬上限 16**；**目标 12–16** |
| 单分镜时长 | **≥ 1.2 秒**；一组 2–6 镜，推荐 3–5 镜 |
| 一组素材 | 图 **≤ 9**、音色 **≤ 3** |
| 一组提示词 | **≤ 2000 字**（写到 1500 以内最稳） |
| 分辨率 | `540p / 720p / 1080p / 2k / 4k`，**默认 1080p** |
| 比例 | `16:9 / 9:16 / 1:1 / 4:3 / 3:4` |
| 调度 | **`nopeak`（闲时，0 积分）** 默认；`normal` 花积分 |
| 下载 | **只认 `download_uri` / `nomark_uri`（无水印）** |

**改上限只改一处：** `scripts/vidu.py` 的 `VIDU_MAX_SECONDS`（当前 16）。
平台若回落到 15，改这个常量 + 本文件第一张表，别的文档不用动。

---

## 一、任务类型

| type | 说明 | Q4 支持 | 时长 |
|---|---|---|---|
| `character2video` | 参考生视频（图 + 主体，**默认**） | ✅ | **1–16** |
| `img2video` | 图生视频（单图） | ✅ | **3–16** |
| `text2video` | 纯文字生视频 | ❌ | — |
| `headtailimg2video` | 首尾帧 | ❌ | — |
| `text2image` | 文生图（资产/符） | ✅ | `duration = 0` |
| `reference2image` | 参考图生图 | ✅ | `duration = 0` + `image_count` |

**Q4 不支持 `transition`。** 传了直接 `Q4 should not include transition`，脚本不开放这个参数。
**Q4 不支持 `claw_pass`。** 只有 `nopeak` / `normal`。

---

## 二、settings 字段（提交体）

```jsonc
"settings": {
  "duration": 12,              // 视频：整数秒 1–16；出图：恒 0
  "model_version": "3.4",      // 视频固定；出图见 §四
  "resolution": "1080p",
  "aspect_ratio": "9:16",
  "sample_count": 1,           // 一次出几条；默认 1
  "schedule_mode": "nopeak",   // nopeak / normal，别猜同义词（off_peak 等一律 400）
  "codec": "h265",
  "movement_amplitude": "auto",
  "use_trial": false           // 视频 false；出图走 true
}
```

`input` 侧：

```jsonc
{"prompts": [
  {"type": "text",  "content": "…提示词…"},
  {"type": "image", "content": "ssupload:?id=<upload_id>"},
  {"type": "audio", "content": "ssupload:?id=<upload_id>", "name": "男主音色.wav"}
], "editor_mode": "normal", "enhance": true}
```

- 图片按顺序对应提示词里的 `pn1`、`pn2`…；音色对应 `vm1`、`vm2`…
- 音频条目的 `metadata` 字段名必须是 **`duration`**（写错 → CORS 预检失败 → 前端只看到 `Failed to fetch`）。

---

## 三、时长怎么定（和分镜组规划同一套数）

| 项 | 值 |
|---|---|
| 合法区间 | **1–16 秒**（整数） |
| 目标区间 | **12–16 秒**，落在这一段一致性成本最低 |
| 低于 6 秒 | 判碎片，能合就合 |
| 单镜下限 | **1.2 秒**（再短立不住主体） |
| 单镜上限 | 没有平台限制；**6 秒以上**要有足够持续观看价值 |
| 台词语速 | 中文含停顿 **3.2–4 字/秒**（按 3.6 估最稳）：12s≈38–48 字，16s≈51–64 字 |

**上限就是 16 秒，不是 15。** 早期按网页轮播可见档位排片，习惯性写成 15 上限，那是旧口径。
Q4 接口对 **1–16** 的整数秒都接受（2026-10-24 实测：14/15/16 全部 `200`、`can_submit: true`；
报价接口对 17 也回 200 —— 它本身不做时长校验，别拿它证明上限）。
**本机历史台账里实际跑通过的是 5–12 秒**，所以 **首次排 16 秒组时，先用单组实跑确认一次**；
确认通过后，全包按 16 排片。

**改上限只改一个常量：** `scripts/vidu.py` 的 `VIDU_MAX_SECONDS`（当前 **16**）。
脚本只此一份，口径永远一致。

**别按固定档位吸附。** 组时长 = 组内各分镜时长之和，可以是任意整数秒；
`12.4 秒` 这种就向上取整到 13，别硬凑 15。

---

## 四、生图（资产 / 符）

| 项 | 值 |
|---|---|
| 模型别名 | `fast` = `3.2_image_2_5_fast`｜**`pro` = `3.2_image_2_5_pro`（默认）**｜`base` = `3.2_image_2` |
| 价格 | **6 积分/张**（三档同价，实测） |
| 默认比例 | `image` 资产 **9:16**（基准图）/ **16:9**（设定板）；`card` 符 **16:9** |
| `duration` | **恒 0** |
| 闲时 | `text2image` 可用 `nopeak`；**`reference2image` 传 `nopeak` 直接 403** |
| 参考图 | r2i 的每张图要**上传两次**（`content` + `src_imgs[0]`），两个不同 upload id |
| 耗时 | 一张约 **2–3 分钟**（含排队） |

**为什么不默认走闲时生图：** 生图与出片**共用同一个「闲时 200 条/天」计数器**，
批量资产会把当天出片额度吃掉。所以 `image` / `card` 默认 `normal`（花积分），
`--dry-run` 先报价。

**下载同样只认无水印。** `success` 但只有 `uri` = 中间态，**继续等**，别退到带水印版。

---

## 五、闲时额度

```
GET /vidu/v1/tasks/quota  →  {"nopeak_quota": {"used": 200, "total": 200}}
```

- **唯一权威来源**就是它。别用积分推、别数任务估。
- 档位：`total = 20` → 专业版；`total = 200` → 旗舰版；其他值照实报「自定义额度」。
- **同时进行中 ≤ 100 条**；日额度先卡死。
- 0 点重置；用完**不会自己恢复** ⇒ 门禁要**停**（退出码 2），不能死等。

| 档位 | 每天闲时 | 一集 6 组，一天能跑 |
|---|---|---|
| 专业版 | 20 条 | 3 集 |
| 旗舰版 | 200 条 | 30 集左右 |

**闲时的能力边界（2026-10-21 实测）：**

| 能力 | 闲时 | 说明 |
|---|---|---|
| 音色参考 `--audio` | ✅ 可用 | 让角色用指定声线说话 |
| AI 配音念台词 | ✅ 可用 | `{台词}` 照样会被念出来 |
| 唇同步 / 音频驱动（`with_audio` + `lip_sync`） | ❌ | 报 `withaudio & lipsync nopeak mode is not allowed` |
| 参考图生图 `r2i` | ❌ | 403 |
| 文生图 `t2i` | ✅ 但**吃出片额度** | 不建议批量用 |

**默认只走闲时。** 要走积分得用户明确说，别替他决定。

---

## 六、结果怎么判断

`ok: true` 不代表成功。**只看 `state`：**

| state | 意思 |
|---|---|
| `created` `queueing` `preparation` `scheduling` `processing` | 还在跑 |
| `success` | 成功，可以下载 |
| `failed` | 失败，看 `err_code` / `err_msg` |
| `canceled` | 取消 |

- **判「这组出没出片」先找成功任务**，不要只看最新一条（重投过的组最新一条可能是 failed）。
- 平台台账**有滞后**（实测可达数小时）⇒ 判失败前先留足入账时间，别急着重投。
- **判「提交真的成功」要认 `task_id`**（提交响应里的 `id`），不要认历史列表。

---

## 七、报错对照

| 报错 | 原因 | 改法 |
|---|---|---|
| `Q4 should not include transition` | 传了 transition | 去掉 |
| `Q4 does not support claw_pass` | 模式用错 | 改 `nopeak` / `normal` |
| `duration X out of range` | 时长超界 | 参考生视频 1–16，图生视频 3–16 |
| `Q4 character2video requires an image...` | 没给素材 | 至少一张图 |
| `withaudio & lipsync nopeak mode is not allowed` | 闲时开了 lip_sync | 关 lip_sync；单纯 `--audio` 不受影响 |
| `reference2image nopeak mode is not allowed` | r2i 用了闲时 | 生图走 `normal` |
| `Invalid resolution` | 分辨率写错 | 用 `1080p` |
| `INSUFFICIENT_CREDITS` | 积分不够 | 充值，或改走闲时 |
| `INVALID_PROMPT_LENGTH` | 提示词超 2000 字 | 压到 1500 内 |
| `CONTENT_MODERATION` / `CreationPolicyViolation` | 内容审核不过 | **合规改写**，别原样重投 |
| `400 AuditSubmitIllegal` | 撞敏感词 | 多半是角色名撞真人，换个名 |

---

## 八、几个习惯

1. **先 `check` 再提交。** 额度和积分一眼看清。
2. **别一口气超额度交。** 超了平台直接失败，不是排队。
3. **提交完别坐着等。** 交完去干别的，隔几分钟 `status` 看一眼。
4. **崩了重跑同一条，别改提示词。** 改了就不是同一个镜头。
5. **`--image` 顺序必须和 `pn1/pn2` 对上，`--audio` 对应 `vm1/vm2`。** 顺序错了就换脸换嗓。
6. **素材路径别带空格。** Windows 下带空格的路由容易出问题。
