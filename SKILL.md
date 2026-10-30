---
name: infocard-video
display_name: 信息卡短视频流水线
display_name_en: Infocard Short-Video Pipeline
description: 信息卡短视频全自动流水线 Skill。当用户要「做一条短视频 / 把这篇稿子做成视频 / 口播视频 / 配音视频 / 竖版视频 / 抖音视频 / 视频成片 / 自动字幕 / 自动配音 / TTS 口播 / 克隆音色做视频 / 加 BGM / 数据讲解视频 / 账单视频 / 教程视频 / 科普解说视频 / 数字滚动动画 / 图文转视频」时使用——即使用户没说「信息卡」三个字，只要是文字稿→带配音字幕的成片需求就该用本技能。输入一段口播稿或主题 → 全自动八步产出 1080×1920 竖版成片（16:9 等其他比例改 config width/height 即可）：分段脚本 → 逐段 TTS 口播（MiniMax，支持克隆音色）→ 按实测时长重排切点 → 无头浏览器逐帧渲染信息卡画面（HTML/CSS 品牌风，数据动画+真实截图，不用素材库不烧生成模型）→ 和弦垫底 BGM（切点自动落音效）→ 混音 → ASS 字幕烧录 → 自动质检（时间线/成片/音量 9 项）。仅依赖 Python 标准库 + ffmpeg + 本机 Edge/Chrome；现金成本 ≈ 0（仅 TTS 按字符计费，自动记账）。
description_en: Fully automated 1080x1920 portrait short-video pipeline. Input a voiceover script or topic, produce a finished video in seven steps: segmented script, per-segment MiniMax TTS (voice cloning supported), retime cuts from measured audio durations, headless-browser frame-by-frame rendering of HTML/CSS infocard scenes (brand-styled data animations and real screenshots, no stock footage, no generative video models), chord-pad BGM, audio mixing, and ASS subtitle burn-in. Requires only Python stdlib, ffmpeg, and a local Edge/Chrome.
category: 视频
version: 1.1.0
author: 梦幻青山的AI说
agent_created: true
---

# 信息卡短视频流水线

把一段口播稿变成一条 1080×1920 竖版成片（口播 + 信息卡画面 + BGM + 字幕）。
全流程只用 Python 标准库 + ffmpeg + 本机 Edge/Chrome/Chromium，画面是 HTML/CSS 渲染的
**品牌信息卡**（数据动画、真实截图嵌入），不依赖素材库，不调用生成式视频模型。

> 面向用户的完整说明（七步流程 / 参数调优 / 已知坑位 / 排错）见 `@references/pipeline-guide.md`。
> 可直接复制的模板：`templates/anim.template.html`（画面）、`templates/config.example.json`（配置）、
> `templates/segments.example.json`（分段脚本）。

## 前置检查（开工前 30 秒）

1. `ffmpeg -version` 可用
2. 本机有 Edge / Chrome / Chromium（逐帧渲染用）
3. 环境变量 `MINIMAX_API_KEY`（可选 `MINIMAX_GROUP_ID`）——不落盘、不进仓库

三者缺一，先告知用户怎么补，不要硬跑。

## 七步流程（每步一条命令，顺序执行）

在**工作目录**（新建，如 `video-build/`）内执行。开工时把
`templates/` 三件复制进来：`anim.template.html` 改名为 `anim.html` 并填入内容，
`config.example.json` 改名为 `config.json` 并改 duration/fps，`segments.example.json`
改名为 `segments.json` 并填入分段口播稿。

| 步 | 命令 | 说明 |
|---|---|---|
| 1 写分段稿 | （agent 生成 `segments.json`） | 每段一句到两句，`anchor` 占位即可，后面 retime 会重排；停顿用 `<#0.5#>`，多音字用 `pron` |
| 2 逐段口播 | `python scripts/gen_voice.py --segments segments.json --config config.json` | 产出 `voice/*.mp3` + `voice_meta.json`。**以 voice_meta 实测时长为准**，不要用推演值 |
| 3 重排切点 | `python scripts/retime.py --lead 0.8 --tail 1.6 --html anim.html` | 按实测时长重排锚点/切点，自动写回 segments.json、voice_meta.json 和 anim.html 的 cuts |
| 3.5 校准 duration | 把 config.json 的 `duration` 改成 ≥ 末段结束+tail，四舍五入整数 | retime 会提示 tail 是否被压缩 |
| 4 逐帧渲染 | `python scripts/render_frames.py --config config.json --html anim.html` | 产出 `frames/f0000.png…`；跳过已存在帧，可断点续渲。15fps×60s≈900 帧，约 30 分钟，**放后台跑** |
| 5 BGM | `python scripts/make_bgm.py --config config.json` | 产出 `bgm.wav`（和弦垫底，自动随 config 长度） |
| 6 混音 | `python scripts/mix_final.py --config config.json --out output/final.mp4` | 口播按锚点 adelay 对齐 + BGM 压底 + limiter。**不含字幕** |
| 7 字幕烧录 | `python scripts/subgen.py --out subs.ass` 然后 `ffmpeg -i output/final.mp4 -vf "ass=subs.ass" -c:a copy output/final_subbed.mp4` | 字幕是**独立步骤**，别漏；`DISPLAY` 字典可做 TTS 写法→字幕写法的替换 |
| 8 自动质检 | `python scripts/qa_check.py --media` | 时间线 6 项 + 成片 3 项（时长/分辨率/音量，从 MP4 本身验证）；退出码非 0 按「修法」处理后重跑 |

成片 = `output/final_subbed.mp4`。qa_check 全过后再人工抽 3-5 帧看关键场景（`ffmpeg -ss 秒数 -i 成片 -frames:v 1 qc.png`）
兜底视觉问题（排版/字号）。**交付说明里写明哪些检查项没跑**（如未跑 --media 就说明成片项未验证）。

## agent 执行要点（实测踩出来的）

- **音色与模型来源（铁律）**：账号音色和 TTS 模型从环境变量 `MINIMAX_VOICE_ID` / `MINIMAX_TTS_MODEL` 读取（config 里 tts.voice_id / tts.model 留 **null** 即可，脚本自动回退到 env）。**永远不要把某个具体音色名写进 config 或模板**——2026-10-30 C1 实测坑：config.example 写死 female-shaonv，短路了 env 回退，成片音色错了整整一条，重做全流程。只有用户明确要多音色才在 config 显式写
- **时长必须实测**：TTS 实测时长可比推演长 30%+。先 gen_voice 再 retime，永远不要先手排切点
- **过渡效果已内置（v1.0.6）**：模板入场/淡出自带自适应运动模糊（位移越大越糊，到位即清），不需要手工加；过渡帧发糊是正常的，稳定帧必然清晰——qa 抽帧时过渡帧（切点后 0.5s 内）不算糊
- **多比例（v1.0.6）**：横版 16:9 改模板 :root 的 `--vw:1920px;--vh:1080px` + config 的 `width/height`，布局改两栏、字号降一档（64→52 级）；渲染/QA 脚本不用改
- **动画叙事引擎（v1.1.0，硬要求）**：
  - 入场动作：.a 加 `data-motion="up|left|right|pop|zoom"`——钩子大字/大数字用 pop（弹性过冲），重磅结论用 zoom，列表用 right，不要全片只用 up
  - 转场：.scene 加 `data-trans="fade|slide|whip|zoom"`——证据幕用 zoom（推近=放大看），节奏强切用 whip（甩镜），同向转场不连用两次
  - Ken Burns：.shot 截图自动缓慢推近，证据截图不再静态贴片；不用则 data-kb="0"
  - 证据强调：SVG 红框 dl('id',t0,t1) 随口播画线——**口播念到哪行，框画到哪行**，时机对齐 voice_meta 实测时间戳
  - 条形生长 grow() / CTA 脉冲 pulse()
- **分镜先行（v1.1.0 硬要求）**：写 anim.html 前先出分镜表（每幕：口播要点/画面/动画重点/强调时机），动画时机对齐口播实测时间戳；首 1.5s 必须有 pop/zoom 级动效（完播率生死线）；一幕文字块≤2
- **时长超了怎么办**：实长超目标 30%+ 时先精简稿子重合成，不要硬压停顿；retime 会打印空档预算告警（最小空档 <0.25s = 节奏偏赶），照告警处理
- **分段稿口播友好**：数字读慢是正常的；长句拆段，别一段塞三句
- **画面 = 内容，不是装饰**：信息卡直接放结论/数据/截图，每场景一个主张；`.a data-d` 依次入场
- **字幕底部避让**：抖音/视频号文案区在底部，模板已避让 200px，别改小
- **渲染放后台**：900+ 帧要半小时（约每秒成片 30 秒渲染，15fps），后台跑期间可并行做 BGM/字幕；帧已存在会跳过，断点续渲
- **多比例**：config width/height 是参数——16:9 横版用 1920×1080（场景排版需同步调整），9:16 之外的比例先改 config 再渲染
- **改单段文案/换音色**：只重跑 gen_voice 对应段 + retime + 受影响帧删除后续渲，不必全量重来。gen_voice 靠 voice_fp.json 指纹（text+voice_id+model+speed+pron）判复用，改了配置重跑会自动重合成；若指纹文件丢了误判复用，删 voice/*.mp3 强制重合成

## 安全与凭据

- `MINIMAX_API_KEY` 只从环境变量读取，脚本不写盘、不打印
- 渲染只用本机浏览器无头截图，无网络请求
- 生成的全部中间产物（voice/frames/）留在工作目录，可随时删除重生成
