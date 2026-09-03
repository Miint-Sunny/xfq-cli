# -*- coding: utf-8 -*-
"""命令行：解 / 混 / 目录确认 / 通配符 / 不像混淆图时跳过。"""
import numpy as np
import pytest
from PIL import Image

from xfq.cli import main
from xfq.core import encode


def smooth_png(path, w=96, h=64):
    y, x = np.mgrid[0:h, 0:w]
    arr = np.stack([x * 2 % 256, y * 3 % 256, (x + y) % 256], axis=-1).astype(np.uint8)
    Image.fromarray(arr).save(path)
    return arr


def test_encode_then_decode_files(tmp_path):
    src = tmp_path / 'a.png'
    arr = smooth_png(src)
    assert main(['-e', str(src)]) == 0
    enc = tmp_path / 'a_enc.png'
    assert np.array_equal(np.asarray(Image.open(enc)), encode(arr))
    assert main([str(enc)]) == 0
    assert np.array_equal(np.asarray(Image.open(tmp_path / 'a_enc_dec.png')), arr)
    assert main([str(enc), '-o', str(tmp_path / 'back.png'), '--overwrite']) == 0
    assert (tmp_path / 'back.png').exists()


def test_decode_refuses_unscrambled_unless_forced(tmp_path, capsys):
    src = tmp_path / 'plain.png'
    smooth_png(src)
    assert main([str(src)]) == 1
    assert '不像小番茄' in capsys.readouterr().out and not (tmp_path / 'plain_dec.png').exists()
    assert main([str(src), '--force']) == 0
    assert (tmp_path / 'plain_dec.png').exists()


def test_jpeg_output_and_alpha(tmp_path):
    src = tmp_path / 'rgba.png'
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 256, (32, 48, 4), dtype=np.uint8)
    Image.fromarray(arr).save(src)
    assert main(['-e', str(src)]) == 0
    with Image.open(tmp_path / 'rgba_enc.png') as im:
        assert im.mode == 'RGBA'
    assert main(['-e', str(src), '--jpeg', '90', '-o', str(tmp_path / 'e.jpg')]) == 0
    with Image.open(tmp_path / 'e.jpg') as im:
        assert im.format == 'JPEG' and im.mode == 'RGB'


def test_folder_confirm_and_outdir(tmp_path, monkeypatch, capsys):
    d = tmp_path / 'pics'
    d.mkdir()
    for n in ('a.png', 'b.png'):
        arr = smooth_png(d / n)
        Image.fromarray(encode(arr)).save(d / n)              # 存混淆好的
    monkeypatch.setattr('builtins.input', lambda _p: 'n')
    assert main([str(d), '-d', str(tmp_path / 'out')]) == 1
    assert '已取消' in capsys.readouterr().out
    monkeypatch.setattr('builtins.input', lambda _p: 'y')
    assert main([str(d), '-d', str(tmp_path / 'out')]) == 0
    assert sorted(p.name for p in (tmp_path / 'out').iterdir()) == ['a_dec.png', 'b_dec.png']
    monkeypatch.setattr('builtins.input', lambda _p: pytest.fail('不该问'))
    assert main([str(d / '*.png'), '-y', '-d', str(tmp_path / 'out2')]) == 0   # 通配符原样传进来
    assert (tmp_path / 'out2' / 'a_dec.png').exists()
