# -*- coding: utf-8 -*-
"""qa_check.py — 流水线自动质检（吸收 anatomy 家族 qa.md 思路：每条检查带方法与修法）。

用法:
    python qa_check.py                    # 时间线检查（渲染前即可跑）
    python qa_check.py --media            # 额外检查成片本身（duration/分辨率/音量，从 MP4 验证，不是只看帧）

检查项（全部可自动化的子集）:
    T1 音频文件齐全        voice/<name>.mp3 每段都有
    T2 锚点递进+空档       上一段音频结束到下一段锚点 ≥ min-gap（默认 0.12s），重叠即 FAIL
    T3 切点=锚点-0.12      每个内部切点与锚点差 ≤ 0.15s
    T4 片长足够            duration ≥ 末段结束 + 0.15s
    T5 字幕不跨切点        每段音频结束 ≤ 下一切点（字幕窗口不被切）
    T6 html cuts 同步      anim html 的 cuts 数组与 config.json 一致
    M1 成片时长            final*.mp4 实测时长与 config.duration 差 ≤ 0.6s
    M2 成片分辨率          与 config width/height 一致
    M3 音轨电平            volumedetect mean 在 -30~-8dB（正常 -18 附近）

退出码：0=全过（允许 WARN），1=有 FAIL。交付时在说明里写明哪些项未跑（如 --media 未跑）。
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def load(here: Path):
    segs = json.loads((here / "segments.json").read_text(encoding="utf-8"))
    meta = json.loads((here / "voice_meta.json").read_text(encoding="utf-8"))
    cfg = json.loads((here / "config.json").read_text(encoding="utf-8"))
    dur = {m["name"]: m["duration_ms"] / 1000 for m in meta}
    amap = {m["name"]: m.get("anchor") for m in meta}
    return segs, meta, cfg, dur, amap


def check_timeline(here: Path, min_gap: float):
    segs, meta, cfg, dur, amap = load(here)
    results = []

    def ok(name, cond, detail, fix=""):
        results.append((name, "PASS" if cond else "FAIL", detail, fix))
        return cond

    def warn(name, cond, detail, fix=""):
        results.append((name, "WARN" if not cond else "PASS", detail, fix))
        return cond

    # T1 音频文件
    missing = [s["name"] for s in segs if not (here / "voice" / f"{s['name']}.mp3").exists()]
    ok("T1 音频文件齐全", not missing,
       "voice/ 每段都有" if not missing else f"缺 {missing}",
       "重跑 gen_voice.py（reuse 机制不会重复计费）")

    # T2 锚点递进 + 空档
    gaps = []
    for i in range(len(segs) - 1):
        end_i = amap[segs[i]["name"]] + dur[segs[i]["name"]]
        gaps.append(amap[segs[i + 1]["name"]] - end_i)
    ok("T2 段间无重叠", all(g >= min_gap for g in gaps),
       f"空档 {[f'{g:.2f}' for g in gaps]}" if gaps else "单段无空档",
       "重跑 retime.py；空档仍 <0.25s 则稿子太长，删段或提 duration")
    if gaps and min(gaps) < 0.25:
        results.append(("T2b 空档余量", "WARN", f"最小空档 {min(gaps):.2f}s < 0.25s，节奏偏赶",
                        "提 config.duration 或精简该段文案"))

    # T3 切点对齐
    cuts = cfg.get("cuts", [])
    bad = []
    for i, c in enumerate(cuts[1:-1], start=1):
        expect = amap[segs[i]["name"]] - 0.12
        if abs(c - expect) > 0.15:
            bad.append(f"cut[{i}]={c} 应为 {expect:.2f}")
    ok("T3 切点=锚点-0.12", not bad, "全部对齐" if not bad else "; ".join(bad),
       "重跑 retime.py 同步 html 与 config")

    # T4 片长
    last_end = amap[segs[-1]["name"]] + dur[segs[-1]["name"]]
    ok("T4 片长足够", cfg["duration"] >= last_end + 0.15,
       f"duration={cfg['duration']} 末段结束={last_end:.2f}",
       "把 config.duration 提到末段结束+1s 以上")

    # T5 字幕不跨切点
    cross = []
    for i, s in enumerate(segs[:-1]):
        end_i = amap[s["name"]] + dur[s["name"]]
        if end_i > cuts[i + 1] + 0.05:
            cross.append(s["name"])
    ok("T5 字幕不跨切点", not cross, "字幕窗口干净" if not cross else f"{cross} 音频压到下一切点",
       "重跑 retime.py；仍跨则该段音频比窗口长，拆段")

    # T6 html cuts 同步
    htmls = list(here.glob("anim*.html"))
    if htmls:
        src = htmls[0].read_text(encoding="utf-8")
        m = re.search(r"const cuts=\[([^\]]*)\];", src)
        html_cuts = [float(x) for x in m.group(1).split(",")] if m else None
        ok("T6 html cuts 同步", html_cuts == [float(c) for c in cuts],
           "一致" if html_cuts == list(map(float, cuts)) else f"html={html_cuts} config={cuts}",
           "重跑 retime.py --html <该html>")
    return results


def ffprobe(args_):
    r = subprocess.run(["ffprobe", "-v", "error"] + args_, capture_output=True, text=True)
    return r.stdout.strip()


def check_media(here: Path):
    results = []
    cfg = json.loads((here / "config.json").read_text(encoding="utf-8"))
    vids = sorted((here / "output").glob("final*.mp4")) if (here / "output").exists() else []
    if not vids:
        results.append(("M0 成片存在", "WARN", "output/ 下无 final*.mp4（渲染后跑 --media）", ""))
        return results
    v = vids[-1]  # final_subbed.mp4 优先（排序上 s > .）
    dur = float(ffprobe(["-show_entries", "format=duration", "-of", "csv=p=0", str(v)]))
    ok = abs(dur - cfg["duration"]) <= 0.6
    results.append(("M1 成片时长", "PASS" if ok else "FAIL",
                    f"{dur:.2f}s vs config {cfg['duration']}s",
                    "时长差大：确认 retime 后 duration 是否改过，重渲" if not ok else ""))
    wh = ffprobe(["-show_entries", "stream=width,height", "-select_streams", "v:0",
                  "-of", "csv=p=0", str(v)])
    ok2 = wh == f"{cfg['width']},{cfg['height']}"
    results.append(("M2 成片分辨率", "PASS" if ok2 else "FAIL", wh,
                    "渲染窗口与 config width/height 不一致，检查 render_frames" if not ok2 else ""))
    r = subprocess.run(["ffmpeg", "-i", str(v), "-af", "volumedetect", "-f", "null", "-"],
                       capture_output=True, text=True)
    mm = re.search(r"mean_volume: ([-\d.]+) dB", r.stderr)
    if mm:
        mean = float(mm.group(1))
        ok3 = -30 <= mean <= -8
        results.append(("M3 音轨电平", "PASS" if ok3 else "WARN", f"mean {mean}dB",
                        "电平异常：检查 mix_final 的 voice_gain/limiter" if not ok3 else ""))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-gap", type=float, default=0.12)
    ap.add_argument("--media", action="store_true", help="连同成片一起检查")
    args = ap.parse_args()
    here = Path(".").resolve()
    if not (here / "segments.json").exists():
        print("找不到 segments.json —— 在 video-build 工作目录内运行")
        sys.exit(2)
    results = check_timeline(here, args.min_gap)
    if args.media:
        results += check_media(here)
    nfail = 0
    for name, status, detail, fix in results:
        mark = {"PASS": "✅", "WARN": "⚠️ ", "FAIL": "❌"}[status]
        print(f"{mark} {name:<14} {detail}")
        if status == "FAIL":
            nfail += 1
            if fix:
                print(f"     ↳ 修法：{fix}")
    print(f"\n{'❌ ' + str(nfail) + ' 项 FAIL' if nfail else '✅ 全部通过'}"
          + ("（未跑 --media，成片项未验证）" if not args.media else ""))
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
