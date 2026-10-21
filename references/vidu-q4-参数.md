# Vidu Q4 参数速查

报错的时候先翻这里。

---

## 三条命令

### 提交

```bash
vidu-cli task submit \
  --type character2video \
  --prompt "提示词" \
  --image 图1.png --image 图2.png \
  --duration 15 \
  --model-version 3.4 \
  --resolution 1080p \
  --aspect-ratio 9:16 \
  --schedule-mode nopeak
```

`--image` 可以重复，最多 9 张，顺序对应提示词里的 `[@图1]` `[@图2]`。

### 查状态

```bash
vidu-cli task get <task_id>
```

### 下载

```bash
vidu-cli task get <task_id> --output ./out
```

下载成功会返回 `downloaded_files`，里面是本地路径。

---

## 任务类型

| 类型 | 说明 | Q4 支持 |
|---|---|---|
| `character2video` | 参考生视频（图 + 主体） | ✅ 1–16 秒 |
| `img2video` | 图生视频（一张图） | ✅ 3–16 秒 |
| `text2video` | 纯文字生视频 | ❌ 不支持 |
| `headtailimg2video` | 首尾帧 | ❌ 不支持 |

---

## 参数

| 参数 | 值 | 备注 |
|---|---|---|
| `--model-version` | `3.4` | Q4 |
| `--duration` | 整数秒 | 参考生视频 1–16，图生视频 3–16 |
| `--resolution` | `540p` `720p` `1080p` `2k` `4k` | 默认给 1080p |
| `--aspect-ratio` | `16:9` `9:16` `1:1` `4:3` `3:4` | 竖屏给 9:16 |
| `--schedule-mode` | `nopeak` `normal` | 闲时用 nopeak |
| `--transition` | **不要传** | Q4 传了直接报错 |

---

## 闲时模式

```bash
--schedule-mode nopeak
```

- 每天 200 条，0 积分
- 单条最长 16 秒
- 同时最多 **100 条**在跑
- 不带音频（带音频会 403）
- **Q4 不写这个参数默认走 normal，扣积分**

查额度：

```bash
vidu-cli task quota        # 闲时还能跑多少
vidu-cli quota credit      # 积分余额
```

---

## 结果怎么判断

`ok: true` 不代表成功。**只看 `state`**：

| state | 意思 |
|---|---|
| `created` `queueing` `preparation` `scheduling` `processing` | 还在跑，继续等 |
| `success` | 成功，可以下载 |
| `failed` | 失败，看 `err_code` / `err_msg` |
| `canceled` | 取消 |

---

## 报错对照

| 报错 | 原因 | 改法 |
|---|---|---|
| `Q4 should not include transition` | 传了 transition | 去掉这个参数 |
| `Q4 does not support claw_pass` | 用了通行证模式 | 改 `nopeak` 或 `normal` |
| `duration X out of range` | 时长超界 | 参考生视频 1–16，图生视频 3–16 |
| `Q4 character2video requires an image, material or audio reference` | 没给素材 | 至少一张图 |
| `withaudio & lipsync nopeak mode is not allowed` | 闲时带音频 | 去音频，或改 `normal` |
| `Invalid resolution` | 分辨率写错 | 用 1080p |
| `Invalid aspect_ratio` | 比例写错 | 从五个值里选 |
| `INSUFFICIENT_CREDITS` | 积分不够 | 充值，或改走闲时 |
| `CONTENT_MODERATION` | 内容审核没过 | 换说法，别写真实人名 |
| `INVALID_PROMPT_LENGTH` | 提示词太长 | 压到 2000 字内 |

---

## 小技巧

**先查钱再提交**

```bash
vidu-cli task cost --type character2video --model-version 3.4 \
  --duration 15 --resolution 1080p
```

返回 `cost_credits`，提交前心里有数。

**批量提交别写循环**，让 AI 来做：

> 把这 40 条按顺序提交，同时最多 100 个在跑，超了排队。每条提交完记下 task_id。

**下载的文件名用镜头号**，别用 task_id。回头剪片子的时候你会感谢自己。
