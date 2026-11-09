# 剪映自动化模块（jianying-editor）

> 本目录是 `vidu-wanji-skill` 的**可选剪辑子模块**：用 Python 直接生成剪映专业版草稿，
> 完成素材导入、字幕、配音、配乐、特效、关键帧与草稿导出。
> 上游为开源项目 **jianying-editor-skill v1.7.0**（MIT），本包按原样集成；
> 上游 README 的作者 / 仓库 / 打赏信息已移除，MIT 许可证原文保留在 `LICENSE`。

---

## 一、能做什么

| 能力 | 说明 |
|---|---|
| 素材导入 | 视频 / 音频 / 图片按时间点放进轨道 |
| 字幕 | 按文案拆句、逐句对齐；支持样式与动画 |
| 配音 | 剪映原生音色 / 微软 TTS；`add_narrated_subtitles` 一键文案转配音字幕 |
| 配乐 | 本地音乐或云端曲库 |
| 特效 / 转场 / 滤镜 | 按中文名检索剪映素材库并应用 |
| 关键帧 | 缩放、位移、透明度 |
| 复合片段 | 嵌套工程 |
| 录屏 + 智能变焦 | 录屏并给点击处加缩放 / 红圈 |
| 草稿检查 / 导出 | `draft_inspector.py` / `auto_exporter.py`（导出仅 Windows） |

## 二、平台边界

| 平台 | 状态 |
|---|---|
| Windows + 剪映专业版 | 推荐；草稿生成、素材导入、字幕、配音、导出 |
| macOS + 剪映专业版 | 支持草稿生成；导出需在剪映内手动完成 |
| CapCut 国际版 / 手机端 | 不支持 |

> 只写草稿，不启动剪映。草稿是 JSON 工程，只存素材路径，不存素材本体。

## 三、安装

```bash
pip install -r jianying-editor/requirements.txt
# 需要 ffmpeg / ffprobe 在 PATH 里
```

**演示素材不在包里。** 上游随包带了 3 MB 的 `assets/video.mp4` 和 README 配图，本包已剔除；
跑 `examples/` 之前先造一份（示例里的路径不用改）：

```bash
python jianying-editor/scripts/make_demo_media.py
```

`api_validator.py` 不依赖素材：缺 `video.mp4` 时它用 ffmpeg 现造 3 秒测试片。

业务剪辑脚本**不要写在本目录**；放到项目根目录，用 `JY_SKILL_ROOT` 指向本目录。

## 四、最小启动代码

```python
import os, sys

skill_root = os.getenv("JY_SKILL_ROOT", os.path.abspath("jianying-editor"))
sys.path.insert(0, os.path.join(skill_root, "scripts"))
from jy_wrapper import JyProject

project = JyProject("AI_测试草稿", overwrite=True)
project.add_media_safe("D:/素材/EP01_1_1.mp4", "0s")
project.add_text_simple("第一句字幕", start_time="0s", duration="3s")
project.save()
```

完整启动模板与多编辑器路径探测：`rules/setup.md`。
最小命令 SOP：`docs/minimal-command-sop.md`。
Agent 路由：`docs/agent-playbook.md`。

## 五、常用命令

```bash
# 草稿列表 / 摘要 / 结构
python jianying-editor/scripts/draft_inspector.py list --limit 20
python jianying-editor/scripts/draft_inspector.py summary --name "AI_测试草稿"
python jianying-editor/scripts/draft_inspector.py show --name "AI_测试草稿" --kind content --json

# 素材 / 特效检索
python jianying-editor/scripts/asset_search.py "复古" -c filters

# 环境自检
python jianying-editor/scripts/api_validator.py

# 导出（Windows）
python jianying-editor/scripts/auto_exporter.py "AI_测试草稿" "out.mp4" --res 1080 --fps 30
```

## 六、规则索引

| 文件 | 管什么 |
|---|---|
| `rules/setup.md` | 必读：初始化 / 路径探测 / `JY_SKILL_ROOT` |
| `rules/core.md` | 保存、导出、草稿管理 |
| `rules/media.md` | 素材导入、AI 视频分析优化（30 分钟 / 360p） |
| `rules/text.md` | 字幕、文本、字幕动画 |
| `rules/keyframes.md` | 关键帧 |
| `rules/effects.md` | 滤镜 / 特效 / 转场 |
| `rules/audio-voice.md` | TTS 配音、BGM |
| `rules/recording.md` | 录屏与智能变焦 |
| `rules/cli.md` | CLI 契约与机器可读输出 |
| `rules/generative.md` | 生成式剪辑思路 |
| `docs/api.md` | API 速查 |
| `examples/` | 可运行示例 |

## 七、交付前必查

- 草稿目录存在，`project.save()` 成功；
- 至少一条 video 轨片段；
- BGM 在 audio 轨（不在 video 轨）；
- 有旁白时有字幕轨且时间对齐；
- 素材路径 URI 化、可解析；素材池 id = 媒体记录 id；
- 发布后再按剪映重写后的结构复核一遍（`speeds` / `common_keyframes`）。

完整三道校验与字幕参数见主包 `../references/50-剪辑与交付.md`。

## 八、许可

- 本模块：MIT，见 `LICENSE`（版权声明按许可证要求保留）。
- 内嵌 `scripts/vendor/pyJianYingDraft/`：Apache License 2.0，见其 `LICENSE`。
- 本包不再展示上游作者、仓库、打赏与社区链接。
