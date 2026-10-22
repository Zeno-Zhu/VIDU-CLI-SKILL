# Vidu Q4 参数速查

报错的时候先翻这里。命令都是 `python scripts/vidu.py` 开头。

---

## 命令

```bash
# 查额度和积分
python scripts/vidu.py check

# 提交一条
python scripts/vidu.py submit --prompt-file G01.txt \
    --image 人物/男主.png --image 场景/饭馆.png \
    --duration 10 --ratio 9:16

# 批量（作业表见 SKILL.md 第六节）
python scripts/vidu.py batch --jobs jobs.tsv

# 查进度
python scripts/vidu.py status

# 下载
python scripts/vidu.py pull --out ./out

# 生图
python scripts/vidu.py image --prompt "人物设定图：..." --name 男主 --ratio 9:16

# 做符（16:9 能力面板）
python scripts/vidu.py card --name 太极拳 --prompt-file out/符/符-太极拳/prompt.txt
```

`--image` 可以重复，最多 9 张，**顺序对应【资产盘点】的 pn1 / pn2**。

---

## 任务类型

| 类型 | 说明 | Q4 支持 | 时长 |
|---|---|---|---|
| `character2video` | 参考生视频（图 + 主体） | 是 | 1–16 秒 |
| `img2video` | 图生视频（一张图） | 是 | 3–16 秒 |
| `text2video` | 纯文字生视频 | **不支持** | — |
| `headtailimg2video` | 首尾帧 | **不支持** | — |

脚本的 `--type` 只开放了前两个。

---

## 参数

| 脚本参数 | 值 | 备注 |
|---|---|---|
| `--duration` | 整数秒 | 参考生视频 1–16，图生视频 3–16 |
| `--ratio` | `16:9` `9:16` `1:1` `4:3` `3:4` | 竖屏给 9:16 |
| `--mode` | `nopeak` / `normal` | 默认 nopeak（闲时） |
| `--model` | 一般不用填 | 视频默认 3.4，生图默认 3.2_image_2_5_pro |

分辨率固定 1080p，脚本里写死了，够用。生图和做符（`image` / `card`）可以用 `--resolution 2k` 试，报 `Invalid resolution` 就退回默认。

**不要传 transition。** Q4 没这个参数，传了直接报错。脚本也没开放它。

---

## 生图与符

| 项 | `image`（资产图） | `card`（符） |
|---|---|---|
| 默认比例 | 9:16 | 16:9 |
| 落到哪 | `out/<名字>.png` | `out/符/符-<名字>/panel.png` |
| 调度 | `normal`，扣积分 | 同左 |
| 参考图 | `--ref`，可重复 | 同左 |
| 分辨率 | 默认，可试 `2k` | 同左 |
| 提示词 | `--prompt` / `--prompt-file` | 同左 |
| 入库 | — | `--meta` 给 JSON，`--tag` 打标签；`--no-lib` 不入 |
| 等待上限 | `--wait`，默认 300 秒 | 同左 |

**符库**

```bash
python scripts/vidu.py lib                   # 列表
python scripts/vidu.py lib --q 太极 --tag 动作 # 搜
python scripts/vidu.py lib --show 符-太极拳    # 详情
python scripts/vidu.py lib --add out/符/符-运镜 # 补录旧符
python scripts/vidu.py lib --rm 符-运镜        # 只移索引，不删图
```

索引在 `out/符/_库.json`，纯 JSON，手改也认（别改 `id`）。

库默认跟着脚本走：skill 装在哪，库就在哪。有两份 skill（工作区 + 安装目录）想共用一个库，设环境变量 `VIDU_CARD_ROOT` 指到同一个 `out/符`。

**生图不走闲时额度。** 闲时只给视频，图和符都扣积分，开工前 `check` 看余额。

符的提示词压到 1500 字以内。超 2000 字会被拒，或者模型只记住前半段——脚本会提醒你字数。

`card` 会把实际用的提示词另存一份到 `out/符/符-<名字>/prompt.txt`，改字重跑时改它，别重写整段。

等超时不算失败，拿 task_id 去 vidu.cn 上看就行。

---

## 闲时模式

```
--mode nopeak
```

- 每天 200 条，0 积分
- 单条最长 16 秒
- 同时最多 **100 条**在跑
- 不带音频（带音频直接 403）
- **默认就是 nopeak**；想花积分才显式写 `--mode normal`

---

## 结果怎么判断

`ok: true` 不代表成功。**只看 `state`**：

| state | 意思 |
|---|---|
| `created` `queueing` `preparation` `scheduling` `processing` | 还在跑 |
| `success` | 成功，可以下载 |
| `failed` | 失败，看 `err_code` / `err_msg` |
| `canceled` | 取消 |

---

## 报错对照

| 报错 | 原因 | 改法 |
|---|---|---|
| `Q4 should not include transition` | 传了 transition | 别传 |
| `Q4 does not support claw_pass` | 模式用错 | 改 `nopeak` 或 `normal` |
| `duration X out of range` | 时长超界 | 参考生视频 1–16，图生视频 3–16 |
| `Q4 character2video requires an image...` | 没给素材 | 至少一张图 |
| `withaudio & lipsync nopeak mode is not allowed` | 闲时带了音频 | 去音频，或 `--mode normal` |
| `Invalid resolution` | 分辨率写错 | 用 1080p |
| `INSUFFICIENT_CREDITS` | 积分不够 | 充值，或改走闲时 |
| `CONTENT_MODERATION` | 审核没过 | 换说法，别写真实人名 |
| `INVALID_PROMPT_LENGTH` | 提示词太长 | 压到 2000 字内 |
| `400 AuditSubmitIllegal` | 撞了敏感词 | 多半是角色名撞真人，换个名 |

---

## 几个习惯

**先查额度再提交。** `check` 一眼就知道今天还能跑多少条。

**别一口气交超过 100 条。** 超了脚本会提醒你，硬交后面的会失败。

**下载用组号命名。** 脚本默认就是 `G01.mp4`，不用你改。

**崩了重跑同一条，别改提示词。** 改了就不是同一个镜头，后面接不上。

**素材路径别用中文空格。** Windows 下带空格的路由容易出问题，文件夹名尽量短。
