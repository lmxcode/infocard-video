# 信息卡短视频流水线（pipeline guide）

面向使用者与 agent 的完整说明。SKILL.md 是执行入口，本文件是参数与坑位手册。

## 一、这套流水线是什么 / 不是什么

**是**：输入分段口播稿 → 全自动产出竖版成片的代码管线。画面是 HTML/CSS 渲染的品牌信息卡
（结论卡、数字网格、编号步骤、真实截图），配 TTS 口播 + 和弦垫底 BGM + ASS 字幕。

**不是**：素材库拼贴工具（不会给内容配城市航拍空镜），也不是生成式视频钱包包装器
（不调用 Veo/Runway 一类按秒计费模型）。现金成本 ≈ TTS 字符费，一条 60s 片通常 < 1 元。

适用：知识/数据/实测类口播内容——有数字可展示、有结论可做成卡片的内容效果最好。
不适用：需要实拍、剧情、口型对齐的内容。

## 二、七步流程总览

```
segments.json ──gen_voice──▶ voice/*.mp3 + voice_meta.json（实测时长！）
                                    │
                              retime（重排锚点/切点，写回 segments/voice_meta/anim.html）
                                    │
config.json + anim.html ──render_frames──▶ frames/f0000.png …（逐帧，慢，放后台）
config.json ──make_bgm──▶ bgm.wav
frames + voice + bgm ──mix_final──▶ output/final.mp4
voice_meta ──subgen──▶ subs.ass ──ffmpeg ass 烧录──▶ output/final_subbed.mp4 ✅
```

## 三、关键参数

### config.json · tts
| 字段 | 说明 |
|---|---|
| `model` | `speech-2.8-hd`（质量优先）/ `speech-2.8-turbo`（便宜快） |
| `voice_id` | MiniMax 系统音色（如 `female-shaonv`）或你的克隆音色 ID |
| `speed` | 0.5-2.0；数字多的口播建议 1.15（再快数字含糊） |
| `pronunciation_dict.tone` | 多音字/缩写注音，如 `"API/(A)(P)(I)"`、`"长/(chang2)"` |
| `language_boost: "Chinese"` | 防止缩写被当英文逐字母拼读 |
| `text_normalization: true` | 128K/62.8%/10M 自动规范化 |

停顿标记 `<#0.5#>`（秒）夹在两段可发音文本之间；emotion 对 speech-2.8 系列不生效，别设。

### config.json · mix
| 字段 | 默认 | 说明 |
|---|---|---|
| `bgm_volume` | 0.22 | BGM 峰值，垫底不抢人声 |
| `voice_gain_db` | 3.5 | 口播增益 |
| `limiter` | 0.95 | 总线限幅 |

### 画面（anim.html）
- `.scene` 数量必须 = cuts 长度 - 1（一个场景一个时间段）
- `.a` 的 `data-d` 是相对场景切入的延迟秒；0.5s 内完成的入场最舒服
- 数字滚动用 `cnt(a,b,t0,t1)`，t0/t1 用 `cuts[i]+偏移` 表达，retime 重排后自动跟随
- 嵌真实截图：`.shot > img`，宽 100% 自适应；截图放 1080 宽以内清晰度足够
- 字幕底部 200px 已避让平台文案区（`subgen.py` 常量可调）

## 四、已知坑位（全部实测踩过）

1. **TTS 时长推演偏差 30%+**。数字类文案实测 64.4s、推演只有 48.7s。永远先 gen_voice
   拿 voice_meta 实测值，再 retime，最后才定 config.duration。
2. **字幕烧录是独立步骤**。mix_final 只混音画；忘了 ass 烧录，成片就是无字幕裸片。
3. **voice_meta 与 segments 锚点不同步 → 字幕重叠**。v1.0.0 起 retime 自动同步，
   旧版手跑过 retime 的话记得手动对齐再 subgen。
4. **切点比锚点早 0.12s**（retime 内置），配合场景 0.35s 交叉淡出，声画无空档。别自己改成 0。
5. **渲染慢**：15fps 是刻意的——逐帧无头截图很贵，900 帧 ≈ 30 分钟。要 30fps 先估算时间。
6. **帧可断点续渲**：render_frames 跳过已存在帧。改了某场景画面后，删掉该时间段帧再跑即可局部重渲。
7. **改单段文案**：segments.json 里删掉该段 `reuse` 标记 → 重跑 gen_voice（只会合成该段）→ retime → 删受影响帧续渲。

## 五、排错

| 症状 | 原因/处理 |
|---|---|
| gen_voice 报 401/余额 | `MINIMAX_API_KEY` 未导出或欠费；key 不落盘，每次运行前 export |
| render 找不到浏览器 | config.json `browser` 填可执行文件绝对路径 |
| 成片有音无画/花屏 | 检查 frames 帧数 = duration×fps，缺帧续渲 |
| 字幕与口播错位 | voice_meta 的 anchor 是否为 retime 后的值（见坑 3） |
| BGM 盖过人声 | 降 `bgm_volume` 到 0.15-0.18 |
