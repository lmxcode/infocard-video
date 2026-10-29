# -*- coding: utf-8 -*-
"""qa_check 最小单测（v1.0.3）：unittest 标准库，免 pytest。
运行：python tests/test_qa_check.py"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import qa_check  # noqa: E402


def fixture(overlaps=False, cut_misaligned=False, missing_voice=False):
    """构造一个 2 段的最小工作目录。overlaps=True 时制造段间重叠。"""
    d = tempfile.mkdtemp()
    here = Path(d)
    gap2 = -0.3 if overlaps else 0.5  # 第二段锚点相对第一段结束的偏移
    segs = [
        {"name": "s1", "text": "第一段测试。", "reuse": False},
        {"name": "s2", "text": "第二段测试。", "reuse": False},
    ]
    meta = [
        {"name": "s1", "duration_ms": 2000, "anchor": 0.8, "text": "第一段测试。"},
        {"name": "s2", "duration_ms": 1500, "anchor": round(0.8 + 2.0 + gap2, 3), "text": "第二段测试。"},
    ]
    a2 = meta[1]["anchor"]
    cuts = [0, round(a2 - 0.12, 3), 6.0]
    if cut_misaligned:
        cuts[1] = round(cuts[1] + 0.9, 3)
    cfg = {"duration": 6.0, "width": 1080, "height": 1920, "cuts": cuts}
    (here / "segments.json").write_text(json.dumps(segs, ensure_ascii=False), encoding="utf-8")
    (here / "voice_meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    (here / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    (here / "anim.html").write_text(f"const cuts=[{cuts[0]},{cuts[1]},{cuts[2]}];", encoding="utf-8")
    voice = here / "voice"
    voice.mkdir(exist_ok=True)
    if not missing_voice:
        (voice / "s1.mp3").write_bytes(b"x")
        (voice / "s2.mp3").write_bytes(b"x")
    return here


def get(results, name):
    return next(r for r in results if r[0].startswith(name))


class QaCheckTests(unittest.TestCase):
    def test_all_pass(self):
        res = qa_check.check_timeline(fixture(), 0.12)
        fails = [r for r in res if r[1] == "FAIL"]
        self.assertEqual(fails, [])
        self.assertEqual(get(res, "T1")[1], "PASS")
        self.assertEqual(get(res, "T2 ")[1] if any(r[0].startswith("T2 ") for r in res) else get(res, "T2")[1], "PASS")
        self.assertEqual(get(res, "T3")[1], "PASS")
        self.assertEqual(get(res, "T4")[1], "PASS")
        self.assertEqual(get(res, "T5")[1], "PASS")
        self.assertEqual(get(res, "T6")[1], "PASS")

    def test_overlap_fails(self):
        res = qa_check.check_timeline(fixture(overlaps=True), 0.12)
        self.assertEqual(get(res, "T2")[1], "FAIL")

    def test_cut_misaligned_fails(self):
        res = qa_check.check_timeline(fixture(cut_misaligned=True), 0.12)
        self.assertEqual(get(res, "T3")[1], "FAIL")
        # 音频未跨切点（切点提前不压音频），T5 应保持 PASS
        self.assertEqual(get(res, "T5")[1], "PASS")

    def test_missing_voice_fails(self):
        res = qa_check.check_timeline(fixture(missing_voice=True), 0.12)
        self.assertEqual(get(res, "T1")[1], "FAIL")

    def test_gap_warning(self):
        res = qa_check.check_timeline(fixture(), 0.12)
        # 0.5s 空档 > 0.25，不应有 T2b WARN
        t2b = [r for r in res if r[0] == "T2b 空档余量"]
        self.assertEqual(t2b, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
