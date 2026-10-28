# infocard-video · 信息卡短视频流水线

把一段口播稿变成一条 **1080×1920 竖版成片**：TTS 口播 + 品牌信息卡画面 + BGM + 字幕，全自动七步。

**定位**：与素材库拼贴类工具（配城市航拍空镜的那种）和生成式视频包装器（按秒烧钱的 Veo/Runway 壳）不同，
本流水线的画面是 HTML/CSS 渲染的**信息卡**——结论卡、数字滚动网格、编号步骤、真实截图嵌入。
适合知识/数据/实测类口播；现金成本 ≈ 0（仅 TTS 字符费）。

## 给 Agent 的安装说明（Agent 自己装，不用人动手）

这是一个标准的 **SKILL.md 技能包**：目录里有 `SKILL.md`（元数据 + 七步执行指令），
任何会读文件的 agent 都能自行安装并执行。给 agent 的完整指令如下，可直接整段粘贴给 agent：

> 请把技能 infocard-video 安装到本机技能目录并验证可用：
> 1. 克隆仓库：`git clone https://github.com/lmxcode/infocard-video`（Windows 下若网络受限，加代理配置）
> 2. 把整个 `infocard-video/` 目录放入本机技能目录：
>    - WorkBuddy：`~/.workbuddy/skills/infocard-video/`（Windows 为 `C:\Users\<你>\.workbuddy\skills\infocard-video\`）
>    - 其他读 SKILL.md 约定的 agent：放入其技能/插件目录即可
> 3. 验证安装：`infocard-video/SKILL.md`、`scripts/`（6 个脚本）、`templates/`（3 个模板）三者齐全
> 4. 依赖检查：`ffmpeg -version` 可用；本机有 Edge/Chrome/Chromium；环境变量 `MINIMAX_API_KEY` 已设置（缺哪项告知用户怎么补）
> 5. 回复用户安装完成。之后用户说「做一条短视频 / 把这篇稿子做成视频 / 口播视频 / 信息卡视频」等即触发本技能，按 SKILL.md 的七步流程执行

安装后无需任何 pip install——脚本全部只用 Python 标准库。

## 快速开始

```bash
# 依赖：Python 3.8+（仅标准库）、ffmpeg、本机 Edge/Chrome/Chromium
export MINIMAX_API_KEY=...        # MiniMax 开放平台 API Key，不落盘

# 1. 建工作目录，复制模板
mkdir video-build && cd video-build
cp ../templates/config.example.json config.json     # 改 duration / voice_id
cp ../templates/segments.example.json segments.json # 填你的分段口播稿
cp ../templates/anim.template.html anim.html        # 改 {{BRAND}} 和场景内容

# 2. 七步流水线（详见 SKILL.md / references/pipeline-guide.md）
python ../scripts/gen_voice.py --segments segments.json --config config.json
python ../scripts/retime.py --lead 0.8 --tail 1.6 --html anim.html
python ../scripts/render_frames.py --config config.json --html anim.html   # 慢，放后台
python ../scripts/make_bgm.py --config config.json
python ../scripts/mix_final.py --config config.json --out output/final.mp4
python ../scripts/subgen.py --out subs.ass
ffmpeg -i output/final.mp4 -vf "ass=subs.ass" -c:a copy output/final_subbed.mp4
```

成片：`output/final_subbed.mp4`。

## 亮点

- **声画对齐按实测**：切点从 TTS 实测时长推导（retime），不信推演值——实测推演偏差可达 30%+
- **信息卡画面**：数字滚动、场景入场动画、真实截图，无素材库拼盘感，品牌风格一个 CSS 文件管到底
- **零第三方 Python 依赖**：全部标准库，clone 即用
- **断点续渲**：逐帧渲染可中断恢复，改单场景可局部重渲

## 环境要求

| 依赖 | 用途 | 说明 |
|---|---|---|
| Python 3.8+ | 全部脚本 | 仅标准库，无需 pip install |
| ffmpeg | 混音/烧字幕 | 系统安装 |
| Edge/Chrome/Chromium | 逐帧截图渲染 | 无头模式，自动探测 |
| MiniMax API Key | TTS 口播 | 环境变量 `MINIMAX_API_KEY`，按字符计费，一条 60s 片 < 1 元 |

## 目录结构

```
├── SKILL.md                    # agent 执行入口（技能包元数据 + 七步指令）
├── README.md                   # 本文件
├── scripts/                    # 6 个脚本：gen_voice / retime / render_frames / make_bgm / mix_final / subgen
├── templates/                  # anim.template.html（画面模板）+ config / segments 示例
└── references/pipeline-guide.md  # 参数手册 + 实测坑位 + 排错
```

## License

MIT
