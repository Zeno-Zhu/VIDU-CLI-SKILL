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

分辨率固定 1080p，脚本里写死了，够用。

**不要传 transition。** Q4 没这个参数，传了直接报错。脚本也没开放它。

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
