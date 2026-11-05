# -*- coding: utf-8 -*-
"""命令行：混淆与解混淆、目录确认、通配符展开、非混淆图的跳过、覆盖已有文件、保留原图元数据（-o）。"""
import os

import numpy as np
import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

import xfq.cli as cli
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
    assert main([str(enc), '-O', str(tmp_path / 'back.png'), '--overwrite']) == 0
    assert (tmp_path / 'back.png').exists()


def test_decode_refuses_unscrambled_unless_forced(tmp_path, capsys):
    src = tmp_path / 'plain.png'
    smooth_png(src)
    assert main([str(src)]) == 0                       # 跳过不计为失败
    assert '可能不是小番茄混淆图' in capsys.readouterr().out and not (tmp_path / 'plain_dec.png').exists()
    assert main([str(src), '-f']) == 0                 # -f 为 --force 的短选项
    assert (tmp_path / 'plain_dec.png').exists()


def test_jpeg_output_and_alpha(tmp_path):
    src = tmp_path / 'rgba.png'
    rng = np.random.default_rng(1)
    arr = rng.integers(0, 256, (32, 48, 4), dtype=np.uint8)
    Image.fromarray(arr).save(src)
    assert main(['-e', str(src)]) == 0
    with Image.open(tmp_path / 'rgba_enc.png') as im:
        assert im.mode == 'RGBA'
    assert main(['-e', str(src), '--jpeg', '90', '-O', str(tmp_path / 'e.jpg')]) == 0
    with Image.open(tmp_path / 'e.jpg') as im:
        assert im.format == 'JPEG' and im.mode == 'RGB'


def test_folder_confirm_and_outdir(tmp_path, monkeypatch, capsys):
    d = tmp_path / 'pics'
    d.mkdir()
    for n in ('a.png', 'b.png'):
        arr = smooth_png(d / n)
        Image.fromarray(encode(arr)).save(d / n)              # 保存为混淆图
    monkeypatch.setattr('builtins.input', lambda _p: 'n')
    assert main([str(d), '-d', str(tmp_path / 'out')]) == 1
    assert '已取消' in capsys.readouterr().out
    monkeypatch.setattr('builtins.input', lambda _p: 'y')
    assert main([str(d), '-d', str(tmp_path / 'out')]) == 0
    assert sorted(p.name for p in (tmp_path / 'out').iterdir()) == ['a_dec.png', 'b_dec.png']
    monkeypatch.setattr('builtins.input', lambda _p: pytest.fail('不应请求确认'))
    assert main([str(d / '*.png'), '-y', '-d', str(tmp_path / 'out2')]) == 0   # 通配符未经 shell 展开，由程序展开
    assert (tmp_path / 'out2' / 'a_dec.png').exists()


# ---------------------------------------------------------------- 覆盖已有输出文件
def _with_old_output(tmp_path):
    src = tmp_path / 'a.png'
    arr = smooth_png(src)
    old = tmp_path / 'a_enc.png'
    old.write_bytes(b'old output')
    return src, arr, old


def test_overwrite_moves_old_output_to_trash(tmp_path, monkeypatch, capsys, no_system_trash):
    monkeypatch.setattr(cli, 'trash_supported', lambda: True)
    src, arr, old = _with_old_output(tmp_path)
    assert main(['-e', str(src), '--overwrite', '-n']) == 0             # 试运行：只报告，不移动
    assert old.read_bytes() == b'old output'
    assert '被覆盖的 a_enc.png 将移到废纸篓' in capsys.readouterr().out
    assert main(['-e', str(src), '--overwrite']) == 0
    assert (no_system_trash / 'a_enc.png').read_bytes() == b'old output'
    assert np.array_equal(np.asarray(Image.open(old)), encode(arr))
    assert '被覆盖的 a_enc.png 已移到废纸篓' in capsys.readouterr().out


def test_overwrite_skipped_when_trash_fails(tmp_path, monkeypatch, capsys):
    def fail(path):
        raise OSError('测试：无法移动')
    monkeypatch.setattr(cli, 'trash_supported', lambda: True)
    monkeypatch.setattr(cli, 'move_to_trash', fail)
    src, _arr, old = _with_old_output(tmp_path)
    assert main(['-e', str(src), '--overwrite']) == 1                   # 无法移到废纸篓：不覆盖，计为失败
    assert old.read_bytes() == b'old output' and '未覆盖' in capsys.readouterr().out
    assert not list(tmp_path.glob('*.tmp~'))                            # 临时文件已清理


def test_overwrite_without_trash_support_replaces_directly(tmp_path, monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, 'trash_supported', lambda: False)
    monkeypatch.setattr(cli, 'move_to_trash', calls.append)
    src, arr, old = _with_old_output(tmp_path)
    assert main(['-e', str(src), '--overwrite']) == 0
    assert not calls and np.array_equal(np.asarray(Image.open(old)), encode(arr))
    assert '已覆盖 a_enc.png' in capsys.readouterr().out


def test_output_directory_is_never_overwritten(tmp_path, no_system_trash):
    src = tmp_path / 'a.png'
    smooth_png(src)
    d = tmp_path / 'out.png'
    d.mkdir()
    (d / 'keep.txt').write_text('keep', 'utf-8')
    assert main(['-e', str(src), '-O', str(d), '--overwrite']) == 1     # 输出路径是目录：报错，目录不动
    assert (d / 'keep.txt').exists() and not list(no_system_trash.iterdir())


@pytest.mark.skipif(os.environ.get('XFQ_TEST_REAL_TRASH') != '1',
                    reason='会向系统废纸篓移入一个测试文件；设置 XFQ_TEST_REAL_TRASH=1 后运行')
def test_real_system_trash(tmp_path):
    from xfq.trash import move_to_trash, supported
    if not supported():
        pytest.skip('当前系统不支持移到废纸篓')
    f = tmp_path / 'xfq-trash-test.png'
    smooth_png(f)
    move_to_trash(f)
    assert not f.exists()


# ---------------------------------------------------------------- 原图元数据（-o, --original）
ICC = b'test-icc-profile'


def png_with_metadata(path):
    """生成带文本块、EXIF、ICC、DPI 的 PNG，模拟 NovelAI 出图。"""
    arr = smooth_png(path)
    info = PngInfo()
    info.add_text('Software', 'NovelAI')
    info.add_text('Comment', '{"prompt": "1girl, 杂鱼~♥"}')            # 含非 Latin-1 字符，写为 iTXt
    exif = Image.Exif()
    exif[0x0131] = 'NovelAI Diffusion V5 0ADF9AB7'
    Image.fromarray(arr).save(path, pnginfo=info, exif=exif.tobytes(), icc_profile=ICC, dpi=(300, 300))
    return arr


def metadata_of(path):
    with Image.open(path) as im:
        im.load()
        return {'texts': dict(getattr(im, 'text', {}) or {}), 'exif': im.getexif().get(0x0131),
                'icc': im.info.get('icc_profile'), 'dpi': im.info.get('dpi')}


def test_output_has_no_metadata_by_default(tmp_path):
    src = tmp_path / 'a.png'
    png_with_metadata(src)
    assert main(['-e', str(src)]) == 0
    m = metadata_of(tmp_path / 'a_enc.png')
    assert not m['texts'] and m['exif'] is None and m['icc'] is None and m['dpi'] is None


def test_original_keeps_metadata_png(tmp_path, capsys):
    src = tmp_path / 'a.png'
    arr = png_with_metadata(src)
    assert main(['-e', str(src), '-o']) == 0
    enc = tmp_path / 'a_enc.png'
    m = metadata_of(enc)
    assert m['texts'] == {'Software': 'NovelAI', 'Comment': '{"prompt": "1girl, 杂鱼~♥"}'}
    assert m['exif'] == 'NovelAI Diffusion V5 0ADF9AB7' and m['icc'] == ICC
    assert [round(x) for x in m['dpi']] == [300, 300]
    assert '已保留元数据：文本块 ×2、EXIF、ICC 色彩配置文件、DPI' in capsys.readouterr().out
    assert main([str(enc), '--original']) == 0                          # 解混淆时同样保留，元数据完整往返
    dec = tmp_path / 'a_enc_dec.png'
    assert metadata_of(dec)['texts'] == m['texts'] and np.array_equal(np.asarray(Image.open(dec)), arr)


def test_original_to_jpeg_drops_png_text_chunks(tmp_path, capsys):
    src = tmp_path / 'a.png'
    png_with_metadata(src)
    assert main(['-e', str(src), '-o', '--jpeg']) == 0
    m = metadata_of(tmp_path / 'a_enc.jpg')
    assert m['exif'] == 'NovelAI Diffusion V5 0ADF9AB7' and m['icc'] == ICC
    out = capsys.readouterr().out
    assert '已保留元数据：EXIF、ICC 色彩配置文件、DPI' in out and 'JPEG 不支持 PNG 文本块，未保留文本块 ×2' in out


def test_original_from_jpeg(tmp_path, capsys):
    src = tmp_path / 'a.jpg'
    arr = smooth_png(tmp_path / 'tmp.png')
    exif = Image.Exif()
    exif[0x010E] = 'jpeg description'
    Image.fromarray(encode(arr)).save(src, quality=95, exif=exif.tobytes(), icc_profile=ICC, comment=b'jpeg comment')
    assert main([str(src), '-o', '-f']) == 0                            # 解混淆为 PNG，JPEG 注释改存为 Comment 文本块
    m = metadata_of(tmp_path / 'a_dec.png')
    assert m['icc'] == ICC and m['texts'].get('Comment') == 'jpeg comment'
    with Image.open(tmp_path / 'a_dec.png') as im:
        assert im.getexif().get(0x010E) == 'jpeg description'


def test_short_o_is_original_and_capital_o_is_output(tmp_path, capsys):
    src = tmp_path / 'a.png'
    png_with_metadata(src)
    assert main(['-e', str(src), '-o', '-O', str(tmp_path / 'x.png')]) == 0
    assert metadata_of(tmp_path / 'x.png')['texts']                     # -O 指定输出文件，-o 保留元数据
    assert main(['-e', str(src), '-n', '-o']) == 0                      # 试运行：报告将保留的元数据
    assert '将保留元数据：文本块 ×2' in capsys.readouterr().out
