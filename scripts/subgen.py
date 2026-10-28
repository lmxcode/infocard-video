# -*- coding: utf-8 -*-
"""subgen.py — 由 voice_meta.json 生成 ASS 字幕（分句 + 按字数分配时长）。

用法:
    python subgen.py [--out subs.ass]

设计:
    - 竖屏 1080x1920，字号 56，底部 MarginV=300（避开平台文案区与署名片）
    - 深字 + 浅色描边（outline 与纸底同色），任何画面上都可读
    - 长句按标点切块，每块按字数比例分时长，最短 0.8s
"""
import argparse
import json
import re
from pathlib import Path

HEAD = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Sub,Microsoft YaHei,58,&H0022262A,&H0022262A,&H00F2F7FA,&H28F2F7FA,1,0,0,0,100,100,1,0,1,7,0,2,80,80,300,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

SPLIT = re.compile(r"(?<=[，。？！；、：,])")

# 口播用了 TTS 友好写法，字幕上换回正式写法
DISPLAY = {}  # 按需：TTS 友好写法 → 字幕正式写法，如 {"A I": "AI"}


def display(text: str) -> str:
    # 剥离 TTS 停顿标记，字幕上不能出现
    text = re.sub(r"<#\d+(?:\.\d{1,2})?#>", "", text)
    for k, v in DISPLAY.items():
        text = text.replace(k, v)
    return text


def ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int(sec % 3600 // 60)
    s = sec % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def chunks(text: str, max_len: int = 15):
    parts = [p for p in SPLIT.split(text) if p.strip()]
    out, buf = [], ""
    for p in parts:
        if len(buf) + len(p) <= max_len:
            buf += p
        else:
            if buf:
                out.append(buf)
            buf = p
    if buf:
        out.append(buf)
    # 单块过长再硬切
    res = []
    for c in out:
        while len(c) > max_len + 4:
            res.append(c[:max_len])
            c = c[max_len:]
        res.append(c)
    return [c.strip("，。、；：,") for c in res if c.strip("，。、；：,")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="subs.ass")
    ap.add_argument("--min-dur", type=float, default=0.8)
    args = ap.parse_args()

    here = Path(".").resolve()
    meta = json.loads((here / "voice_meta.json").read_text(encoding="utf-8"))

    lines = []
    for m in meta:
        start, dur = m["anchor"], m["duration_ms"] / 1000
        cs = chunks(display(m["text"]))
        total_chars = sum(len(c) for c in cs) or 1
        t = start
        for c in cs:
            d = max(args.min_dur, dur * len(c) / total_chars)
            lines.append((t, min(t + d, start + dur), c))
            t += d

    body = "".join(
        f"Dialogue: 0,{ts(s)},{ts(e)},Sub,,0,0,0,,{txt}\n" for s, e, txt in lines
    )
    out = here / args.out
    out.write_text(HEAD + body, encoding="utf-8")
    print(f"OK {out} · {len(lines)} 条")
    for s, e, txt in lines[:6]:
        print(f"  {s:5.2f}-{e:5.2f} {txt}")


if __name__ == "__main__":
    main()
