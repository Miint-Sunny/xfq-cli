# -*- coding: utf-8 -*-
"""算法：和参考站字节级一致；混淆 → 解混淆恒等；各种奇怪尺寸。"""
import base64
import json
from pathlib import Path

import numpy as np
import pytest

from xfq.core import curve, decode, encode, offset, roughness

# 黄金向量来自 Rinne414/sd-image-sorter（MIT）：用参考站原版 JS 在 node 里跑出的字节级结果。
# 密码为空的那些 = step 1、无补边 = 小番茄。
GOLDEN = json.loads((Path(__file__).parent / 'assets' / 'reference_golden.json').read_text('utf-8'))
CASES = [c for c in GOLDEN['pixel_cases'] if c['password'] == '']


@pytest.mark.parametrize('case', CASES, ids=[f"{c['width']}x{c['height']}" for c in CASES])
def test_matches_reference_site_bytes(case):
    w, h = case['width'], case['height']
    original = np.frombuffer(base64.b64decode(case['original_b64']), dtype=np.uint8).reshape(h, w, 4)
    expected = np.frombuffer(base64.b64decode(case['encrypted_b64']), dtype=np.uint8).reshape(h, w, 4)
    assert np.array_equal(encode(original), expected)
    assert np.array_equal(decode(expected), original)


@pytest.mark.parametrize('w,h', [(1, 1), (1, 9), (9, 1), (2, 2), (2, 3), (3, 2), (5, 7), (7, 5), (16, 16),
                                 (37, 100), (100, 37), (64, 48), (123, 45), (832, 96)])
def test_curve_is_a_permutation_and_roundtrips(w, h):
    c = curve(w, h)
    assert c.size == w * h and np.array_equal(np.sort(c), np.arange(w * h))
    rng = np.random.default_rng(w * 1000 + h)
    for channels in (3, 4):
        arr = rng.integers(0, 256, (h, w, channels), dtype=np.uint8)
        assert np.array_equal(decode(encode(arr)), arr)
    if w * h > 1:
        assert not np.array_equal(encode(arr), arr)


def test_offset_is_js_math_round():
    assert offset(35) == 22 and offset(1) == 1 and offset(10) == 6


def test_roughness_drops_after_decode():
    # 用低频噪声当「自然图」：纯渐变太平滑，Gilbert 曲线保持局部性，混淆后也不怎么粗糙
    rng = np.random.default_rng(0)
    small = rng.integers(0, 256, (6, 8, 3), dtype=np.uint8)
    from PIL import Image
    natural = np.asarray(Image.fromarray(small).resize((96, 64), Image.BILINEAR))
    enc = encode(natural)
    assert roughness(enc) > roughness(natural)
    assert roughness(decode(enc)) == roughness(natural)
