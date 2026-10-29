# -*- coding: utf-8 -*-
"""retime.py — 按实测口播时长重排锚点与场景切点，消灭空档。

用法:
    python retime.py                 # 读 segments.json + voice_meta.json，重排后写回
    python retime.py --lead 0.8 --tail 1.5

规则:
    - 首句前留 lead 秒，末句后留 tail 秒
    - 句间空档按 weights 分配（转折处给更大停顿）
    - 切点 = 锚点 - 0.12（画面比声音早一点点，配合交叉淡入不露空屏）
    - 同步改写 anim_*.html 里的 cuts 数组
"""
import argparse
import json
import re
from pathlib import Path

WEIGHTS = [1.0, 1.0, 1.0, 1.4, 1.2]  # 句间空档权重（转折处更大）；段数超出时按 1.0 补


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default="segments.json")
    ap.add_argument("--lead", type=float, default=0.8)
    ap.add_argument("--tail", type=float, default=1.5)
    ap.add_argument("--html", default="anim.template.html")
    args = ap.parse_args()

    here = Path(".").resolve()
    segs = json.loads((here / args.segments).read_text(encoding="utf-8"))
    meta = json.loads((here / "voice_meta.json").read_text(encoding="utf-8"))
    dur = {m["name"]: m["duration_ms"] / 1000 for m in meta}

    total = float(json.loads((here / "config.json").read_text(encoding="utf-8"))["duration"])
    speech = sum(dur[s["name"]] for s in segs)
    gaps_total = total - args.lead - args.tail - speech
    if gaps_total < 0.3 * len(WEIGHTS):
        print(f"⚠️ 空档不足（{gaps_total:.2f}s），压缩 tail")
        args.tail = max(0.5, args.tail + gaps_total - 0.3 * len(WEIGHTS))
        gaps_total = total - args.lead - args.tail - speech
    n_gaps = len(segs) - 1
    weights = [WEIGHTS[i] if i < len(WEIGHTS) else 1.0 for i in range(n_gaps)]
    unit = gaps_total / sum(weights)
    gaps = [w * unit for w in weights]

    t = args.lead
    anchors = []
    for i, s in enumerate(segs):
        anchors.append(round(t, 3))
        t += dur[s["name"]]
        if i < len(gaps):
            t += gaps[i]

    cuts = [0.0] + [round(a - 0.12, 3) for a in anchors[1:]] + [total]

    for s, a in zip(segs, anchors):
        s["anchor"] = a
        s["reuse"] = True
    for i, s in enumerate(segs):
        end_limit = cuts[i + 1] if i + 1 < len(cuts) else total - 0.15
        s["window"] = [round(s["anchor"] - 0.5, 3), round(end_limit, 3)]
    (here / args.segments).write_text(json.dumps(segs, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    # 同步 voice_meta.json 的 anchor（subgen.py 读的是 voice_meta，不同步会导致字幕重叠）
    vmp = here / "voice_meta.json"
    if vmp.exists():
        vmeta = json.loads(vmp.read_text(encoding="utf-8"))
        amap = {s["name"]: s["anchor"] for s in segs}
        for m in vmeta:
            if m.get("name") in amap:
                m["anchor"] = amap[m["name"]]
        vmp.write_text(json.dumps(vmeta, ensure_ascii=False, indent=2), encoding="utf-8")
        print("voice_meta anchors synced")

    # 同步 config.json 的 cuts（v1.0.3：config 也是消费方——mix/bgm 读它，不同步会出现两套切点）
    cp = here / "config.json"
    if cp.exists():
        cfg = json.loads(cp.read_text(encoding="utf-8"))
        cfg["cuts"] = cuts
        cp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("config.json cuts synced")

    # 改写 html 里的 cuts
    hp = here / args.html
    if hp.exists():
        src = hp.read_text(encoding="utf-8")
        new = "const cuts=[" + ",".join(f"{c:g}" for c in cuts) + "];"
        src2 = re.sub(r"const cuts=\[[^\]]*\];", new, src, count=1)
        hp.write_text(src2, encoding="utf-8")
        print("html cuts:", new)

    print(f"speech={speech:.2f}s gaps={[f'{g:.2f}' for g in gaps]} tail={total - (anchors[-1] + dur[segs[-1]['name']]):.2f}s")
    for s, a in zip(segs, anchors):
        print(f"  {s['name']:<10} anchor={a:6.2f} dur={dur[s['name']]:5.2f} end={a + dur[s['name']]:6.2f}")
    print("cuts:", [f"{c:g}" for c in cuts])

    # 空档预算告警（吸收 anatomy qa 思路：不放宽检查，先提示）
    if gaps and min(gaps) < 0.25:
        print(f"⚠️ 最小空档 {min(gaps):.2f}s < 0.25s，节奏偏赶。建议：①精简最长段的文案 ②提 config.duration")
    ratio = speech / total
    if ratio > 0.9:
        print(f"⚠️ 口播占片长 {ratio:.0%}，几乎没有呼吸空间。建议删 1 段或提 duration；"
              f"若实长超出目标 30%+，先精简稿子再重合成（时长推演不可信）")


if __name__ == "__main__":
    main()
