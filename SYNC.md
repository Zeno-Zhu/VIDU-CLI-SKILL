# 与 A 包的同步状态

本包（`vidu-skill`，公开精简版）当前 **2.6.0**。

## 已同步（2026-11-09）

### 3.0 资产绑定链路（2.6.0）

| 环节 | 文件 | 状态 |
|---|---|---|
| P0 初始化 | `scripts/project_init.py`、`scripts/channel_profile.py`、`references/20-渠道参数.md` | ✅ 与 A 包同一份 |
| 资产清单 | `scripts/assets_check.py`、`references/21-资产清单.md` | ✅ |
| 设定板 A/B | `scripts/board_build.py`、`scripts/board_check.py`、`templates/`、`references/角色设定板模板.md` | ✅ |
| P6 绑定 | `scripts/bind_assets.py`、`references/22-资产绑定.md` | ✅ |
| P7.5 注入 | `scripts/prompt_assemble.py` | ✅ |
| P8 作业单 | `scripts/jobs_build.py` | ✅ |
| 四方对账 | `scripts/bind_check.py` | ✅ |
| 分镜组 | `scripts/storyboard_check.py`、`references/30-分镜组.md` | ✅ |
| 质检 / 常量 / 流程 / 红线 | `references/40-质检.md`、`90-常量.md`、`00-流程总表.md`、`10-红线.md`、`15-确定性.md` | ✅ |
| 剪辑模块 | `jianying-editor/`、`references/50`、`references/51` | ✅ 与 A 包逐文件一致 |

### 删除的旧文件（已被上面取代）

- `分镜组规划.md` → `30-分镜组.md`
- `分镜组审核.md` → `40-质检.md`
- `vidu-参数.md`、`vidu-q4-参数.md` → `20-渠道参数.md`

## 仍然不同的地方（有意保留）

| 项 | A 包 | B 包 |
|---|---|---|
| 提示词模板 | `prompts/01-自己人模板.md` + `02-标准模板.md` 双模板 | 只做**标准制式**，引导在 `SKILL.md` + `references/prompts/01-漫剧分镜提示词.md` |
| 叙事风格 | 参考手册式，按 P0—P10 阶段卡组织 | 教学式，按「先问什么、再做什么」组织 |
| 阶段卡 | `references/phase-00…10` | 无（并入 SKILL 的流程段） |
| 剧本模块 | `script/`（同一份） | `script/`（同一份） |
| 商业线 | 有 | 有 |

## 处理原则

A 包（`vidu-wanji-skill` 3.2.0）是数据契约与脚本的主源：**脚本、schema、templates 一律以 A 包为准，改了要同步到本包**。
B 包只在**表达层**（SKILL / README 的讲法、提示词引导）保持自己的风格。

⛔ 不要在 B 包单独改脚本逻辑——下次同步会被覆盖；要改先改 A 包，再拷过来。

## 同步清单（下次照这个走）

1. `scripts/`：`project_init` `channel_profile` `assets_check` `board_build` `board_check` `bind_assets` `bind_check` `jobs_build` `prompt_assemble` `storyboard_check` `vidu_check_prompts` `asset_init`
2. `templates/`：三个文件整套覆盖
3. `references/`：`00` `10` `15` `20` `21` `22` `30` `40` `90` `角色设定板模板` `资产设定板` `提示词自检表` `音色与配音` `剧本到分镜的交接`
4. 跑一遍端到端：`project_init → assets_check → board_build/check → storyboard_check → bind_assets → prompt_assemble → vidu_check_prompts → jobs_build → bind_check`
5. 更新 `VERSION` 与 `SKILL.md` frontmatter 版本号
