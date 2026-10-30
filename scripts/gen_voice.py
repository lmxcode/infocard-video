# -*- coding: utf-8 -*-
"""gen_voice.py — 按「锚点 + 时间窗」逐段合成口播（MiniMax TTS）。

用法:
    python gen_voice.py --segments segments.json --config config.json

环境变量（不落盘、不进仓库）:
    MINIMAX_API_KEY   必填，MiniMax 开放平台 API Key
    MINIMAX_GROUP_ID  如你的账号需要则填写

segments.json 格式（见 example/segments.json）:
    [
      {"name": "S1_hook", "anchor": 0.6, "text": "……", "window": [0, 5.2]},
      {"name": "S2", "text": "……", "pron": ["长/(chang2)"]},   # 可选，本段专用注音
      ……
    ]
    anchor = 口播起播秒数（与 anim.html 的动画对齐）
    window = 该段必须落进去的 [起, 止] 区间（止留 0.15s 余量判定）

读音/节奏控制（MiniMax t2a_v2 官方参数，优先用参数，别再靠改文案绕）:
    1. pronunciation_dict.tone —— 多音字/缩写注音，声调 1-4、轻声 5
       ["长/(chang2)", "API/(A)(P)(I)"]
       config.tts.pronunciation_dict.tone 放全局规则，segments 里 pron 放单段规则
    2. 文本内停顿标记 <#0.5#> —— 秒，0.01-99.99，须夹在两个可发音文本之间，不可连用
       例：「平均只涨三点六，<#0.4#>记忆容量还有限」
    3. language_boost —— 明确 "Chinese"，避免 API 这类缩写被当英文单词拼读
    4. text_normalization=True —— 数字/单位/百分号规范化（128K、62.8%、10M）
    5. speed 0.5-2.0（现用 1.15）、pitch -12~12、vol (0,10]
    6. emotion 对 speech-2.8-* 不生效（仅 2.5-preview/02/01 支持），别设了等结果

输出:
    voice/S1_hook.mp3 …
    voice_meta.json  → 供 mix_final.py 使用
"""
import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path


def synth_one(text: str, out_path: Path, cfg_tts: dict, extra_pron=None) -> dict:
    api_key = os.getenv("MINIMAX_API_KEY")
    if not api_key:
        raise SystemExit("未设置 MINIMAX_API_KEY 环境变量（密钥不要写进任何文件/仓库）")

    voice_setting = {
        "voice_id": cfg_tts.get("voice_id") or os.getenv("MINIMAX_VOICE_ID") or "male-qn-qingse",
        "speed": cfg_tts.get("speed", 1.15),
        "vol": cfg_tts.get("volume") or float(os.getenv("MINIMAX_VOLUME", "3.0")),
    }
    if cfg_tts.get("pitch") is not None:
        voice_setting["pitch"] = int(cfg_tts["pitch"])  # [-12,12]

    body = {
        "model": cfg_tts.get("model") or os.getenv("MINIMAX_TTS_MODEL") or "speech-2.8-hd",
        "text": text,
        "stream": False,
        "voice_setting": voice_setting,
        "audio_setting": {
            "sample_rate": 32000, "bitrate": 128000, "format": "mp3", "channel": 1,
        },
        "subtitle_enable": False,
        # 中文文本规范化：数字/单位/百分号读数更准（128K、62.8%、10M）
        "text_normalization": cfg_tts.get("text_normalization", True),
        "english_normalization": True,
        # 明确指定中文，避免缩写被当英文单词拼读（缩写会被逐字母拼读）
        "language_boost": cfg_tts.get("language_boost") or os.getenv("MINIMAX_LANGUAGE_BOOST") or "Chinese",
    }

    # 发音词典：config 全局 + 分段覆盖。格式 ["长/(chang2)", "API/(A)(P)(I)"]
    pron = list((cfg_tts.get("pronunciation_dict") or {}).get("tone") or [])
    if extra_pron:
        pron.extend(extra_pron)
    if pron:
        body["pronunciation_dict"] = {"tone": pron}

    payload = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        "https://api.minimaxi.com/v1/t2a_v2",
        data=payload,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    base = data.get("base_resp", {})
    if base.get("status_code") != 0:
        raise SystemExit(f"MiniMax API error {base.get('status_code')}: {base.get('status_msg')}")
    mp3 = bytes.fromhex(data["data"]["audio"])
    out_path.write_bytes(mp3)
    dur_ms = data.get("extra_info", {}).get("audio_length", 0)
    return {"duration_ms": dur_ms}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default="segments.json")
    ap.add_argument("--config", default="config.json")
    args = ap.parse_args()

    here = Path(args.config).resolve().parent
    cfg = json.loads((here / Path(args.config).name).read_text(encoding="utf-8"))
    segs = json.loads(Path(args.segments).read_text(encoding="utf-8"))

    vdir = here / "voice"
    vdir.mkdir(exist_ok=True)

    meta = []
    all_fit = True
    synthed = []  # 本次实际重新合成的段（计费用）；reuse 的不重复计费

    # 复用指纹：text+voice_id+model+speed+pron 任一变化都必须重合成。
    # 2026-10-30 实测坑：早期版本只看「mp3 存在 + reuse 标记」，换音色后被当缓存
    # 命中静默跳过，成片还是旧音色。指纹存 voice_fp.json，与 mp3 同生命周期。
    import hashlib
    fp_path = here / "voice_fp.json"
    fps = json.loads(fp_path.read_text(encoding="utf-8")) if fp_path.exists() else {}

    def voice_fp(seg, cfg_tts: dict) -> str:
        raw = json.dumps([seg.get("text"), cfg_tts.get("voice_id"), cfg_tts.get("model"),
                          cfg_tts.get("speed", 1.15), seg.get("pron")], ensure_ascii=False)
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def billed_chars(t: str) -> int:
        # MiniMax 口径：1 汉字=2 字符，ASCII/标点=1 字符
        return sum(2 if ord(c) > 127 else 1 for c in t)

    for seg in segs:
        name = seg["name"]
        anchor, text = float(seg["anchor"]), seg["text"]
        win = seg.get("window")
        mp3 = vdir / f"{name}.mp3"

        fp = voice_fp(seg, cfg.get("tts", {}))
        if mp3.exists() and seg.get("reuse", False) and fps.get(name) == fp:
            # 已存在且指纹一致才读旧文件时长（ffprobe）
            import subprocess
            r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(mp3)], capture_output=True, text=True)
            dur_ms = int(float(r.stdout.strip()) * 1000)
            print(f"{name} reuse {dur_ms}ms", flush=True)
        else:
            r = synth_one(text, mp3, cfg.get("tts", {}), extra_pron=seg.get("pron"))
            dur_ms = r["duration_ms"]
            fps[name] = fp
            synthed.append((name, billed_chars(text)))
            print(f"{name} synth {dur_ms}ms", flush=True)

        end = anchor + dur_ms / 1000
        fit = True
        if win:
            fit = end <= win[1] - 0.15
            if not fit:
                all_fit = False
                print(f"⚠️  {name} 超窗: end={end:.2f} > {win[1]}（文本 {len(text)} 字，精简文案或挪锚点）",
                      file=sys.stderr, flush=True)
        meta.append({"name": name, "anchor": anchor, "text": text,
                     "mp3": str(mp3.resolve()), "duration_ms": dur_ms})

    out = here / "voice_meta.json"
    out.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    fp_path.write_text(json.dumps(fps, ensure_ascii=False, indent=1), encoding="utf-8")

    # 计费记账：逐次累加到 tts_billing.json（单价见 MiniMax 定价页：hd 3.5 元/万字符，turbo 2 元/万字符）
    if synthed:
        bill_path = here / "tts_billing.json"
        bills = json.loads(bill_path.read_text(encoding="utf-8")) if bill_path.exists() else {
            "model": cfg.get("tts", {}).get("model", "?"), "price_per_10k": 3.5, "records": []}
        chars = sum(c for _, c in synthed)
        bills["records"].append({"at": time.strftime("%Y-%m-%d %H:%M:%S"),
                                 "segments": [n for n, _ in synthed],
                                 "billed_chars": chars,
                                 "cost_cny": round(chars / 10000 * bills.get("price_per_10k", 3.5), 4)})
        bills["total_cny"] = round(sum(r.get("cost_cny", 0) for r in bills["records"]), 4)
        bill_path.write_text(json.dumps(bills, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"billing: +{chars} chars, +{bills['records'][-1]['cost_cny']} CNY, total {bills['total_cny']} CNY")
    print(f"meta saved: {out}", "ALL_FIT" if all_fit else "HAS_OVER")
    # 超窗的处理顺序：先精简文案重新合成 → 实在差 0.2s 内可微挪锚点（锚点只是放置位置）
    if not all_fit:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
