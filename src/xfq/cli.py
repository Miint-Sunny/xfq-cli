# -*- coding: utf-8 -*-
"""xfq：小番茄图片混淆的命令行。默认解混淆，-e 混淆，批量，输出 PNG。"""
from __future__ import annotations

import argparse
import glob
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__
from .core import decode, encode, roughness

Image.MAX_IMAGE_PIXELS = None
IMG_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff'}
GLOB_CHARS = ('*', '?', '[')


# ---------------------------------------------------------------- 跨平台小件
def setup_console() -> None:
    """Windows 上 stdout 重定向到文件 / 管道时默认 GBK，符号会报错；统一 UTF-8。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def _plain() -> bool:
    flag = os.environ.get('XFQ_ASCII')
    if flag is not None:
        return flag not in ('0', '')
    return os.name == 'nt' and not os.environ.get('WT_SESSION')


SYM = {'ok': '√', 'bad': '×', 'warn': '!'} if _plain() else {'ok': '✔', 'bad': '✗', 'warn': '⚠'}


def iter_images(paths, recursive: bool = False):
    """产出 (文件, 相对路径)。目录保留层级；带 * ? [ 的参数自己展开（Windows 的 shell 不替外部程序展开）。"""
    for p in paths:
        p = Path(p)
        if any(ch in str(p) for ch in GLOB_CHARS) and not p.exists():
            matches = sorted(glob.glob(str(p), recursive=True))
            if not matches:
                print(f'没有匹配: {p}', file=sys.stderr)
                continue
            yield from iter_images(matches, recursive)
        elif p.is_dir():
            it = p.rglob('*') if recursive else p.glob('*')
            for f in sorted(it):
                if f.is_file() and f.suffix.lower() in IMG_EXTS and not f.name.startswith('.'):
                    yield f, f.relative_to(p)
        elif p.is_file():
            yield p, Path(p.name)
        else:
            print(f'找不到: {p}', file=sys.stderr)


def confirm(prompt: str) -> bool:
    try:
        return input(prompt).strip().lower() in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def fmt_size(n: float) -> str:
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if n < 1024 or unit == 'GiB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.2f} {unit}'
        n /= 1024
    return f'{n:.2f} GiB'


# ---------------------------------------------------------------- 主流程
def output_path(src: Path, rel: Path, opts) -> Path:
    ext = '.jpg' if opts.jpeg is not None else '.png'
    suffix = opts.suffix if opts.suffix is not None else ('_enc' if opts.encode else '_dec')
    if opts.output:
        return Path(opts.output)
    if opts.outdir:
        return Path(opts.outdir) / rel.with_name(rel.stem + suffix + ext)
    return src.with_name(src.stem + suffix + ext)


def load_pixels(im: Image.Image) -> np.ndarray:
    """有透明就 RGBA，否则 RGB。参考实现在 canvas 上按 RGBA 搬像素，通道数不影响位置。"""
    has_alpha = 'A' in im.mode or (im.mode == 'P' and 'transparency' in im.info)
    return np.asarray(im.convert('RGBA' if has_alpha else 'RGB'))


def process_one(src: Path, rel: Path, opts) -> tuple[bool, str]:
    dst = output_path(src, rel, opts)
    tag = f'{src.name} → {dst if opts.output or opts.outdir else dst.name}'
    if dst.exists() and not opts.overwrite:
        return False, f'{SYM["bad"]} {tag}   输出已存在，跳过（--overwrite 可覆盖）'
    try:
        with Image.open(src) as im:
            im.load()
            arr = load_pixels(im)
        before = roughness(arr)
        out = encode(arr) if opts.encode else decode(arr)
        after = roughness(out)
        note = ''
        if not opts.encode and after >= before:
            # 解完没变平滑：多半根本不是小番茄图（或已经是原图）。
            # 30 张真图校准：解真混淆图比值 0.46–0.79（含过 JPEG90 的），解原图 1.41–2.17，阈值 1.0 两边都有余量
            if not opts.force:
                return False, (f'{SYM["warn"]} {tag}   解完没变平滑（粗糙度 {before:.1f} → {after:.1f}），'
                               f'看着不像小番茄混淆过的图，跳过；--force 硬写')
            note = f'（粗糙度 {before:.1f} → {after:.1f}，不像混淆图，已硬写）'
        if opts.dry_run:
            return True, f'· {tag}   [dry-run] {arr.shape[1]}×{arr.shape[0]} 粗糙度 {before:.1f} → {after:.1f}'
        dst.parent.mkdir(parents=True, exist_ok=True)
        result = Image.fromarray(out)
        tmp = dst.with_name(dst.name + '.tmp~')
        if opts.jpeg is not None:
            result.convert('RGB').save(tmp, format='JPEG', quality=opts.jpeg, subsampling=0)
        else:
            result.save(tmp, format='PNG')
        os.replace(tmp, dst)
        what = '混淆' if opts.encode else '解混淆'
        return True, (f'{SYM["ok"]} {tag}   {what} {arr.shape[1]}×{arr.shape[0]} · 粗糙度 {before:.1f} → {after:.1f}'
                      f' · {fmt_size(dst.stat().st_size)}{note}')
    except Exception as e:
        return False, f'{SYM["bad"]} {tag}   失败: {e}'


def main(argv=None) -> int:
    setup_console()
    ap = argparse.ArgumentParser(
        prog='xfq',
        description='小番茄图片混淆：默认解混淆，-e 混淆。输出 PNG（无损），批量可整个目录拖进来。',
        epilog='示例：xfq a.jpg（→ a_dec.png）  |  xfq -e a.png（→ a_enc.png）  |  xfq -r ./收图 -d ./解好  |  xfq -e *.png --jpeg')
    ap.add_argument('paths', nargs='*', help='图片文件或目录')
    ap.add_argument('-e', '--encode', action='store_true', help='混淆（默认是解混淆）')
    ap.add_argument('-r', '--recursive', action='store_true', help='目录递归')
    g = ap.add_mutually_exclusive_group()
    g.add_argument('-o', '--output', metavar='FILE', help='输出文件（只能配一个输入）')
    g.add_argument('-d', '--outdir', metavar='DIR', help='输出目录，目录输入时保留相对层级')
    ap.add_argument('--suffix', default=None, help='输出文件名后缀（默认解混淆 _dec、混淆 _enc）')
    ap.add_argument('--jpeg', nargs='?', const=95, type=int, metavar='质量', help='输出 JPEG 而不是 PNG（默认质量 95；混淆图发群时更像网页版出来的）')
    ap.add_argument('--force', action='store_true', help='解完看着不像小番茄图也照写')
    ap.add_argument('--overwrite', action='store_true', help='输出已存在时覆盖')
    ap.add_argument('-n', '--dry-run', action='store_true', help='只算不写')
    ap.add_argument('-y', '--yes', action='store_true', help='处理目录 / 通配符时不问 y/N')
    ap.add_argument('-V', '--version', action='version', version=f'xfq {__version__}')
    a = ap.parse_args(argv)

    items = list(iter_images(a.paths, a.recursive))
    if not items:
        print('没有找到图片', file=sys.stderr)
        return 1
    if a.output and len(items) > 1:
        print('-o 只能配一个输入文件；多个文件请用 -d 输出目录', file=sys.stderr)
        return 1
    batch = [p for p in a.paths if Path(p).is_dir() or any(ch in p for ch in GLOB_CHARS)]
    if batch and not a.yes and not a.dry_run:
        ext = Counter(f.suffix.lower().lstrip('.') for f, _ in items)
        kinds = ' · '.join(f'{k} {n}' for k, n in ext.most_common())
        print(f"{', '.join(batch)}：{len(items)} 张（{kinds}）{'混淆' if a.encode else '解混淆'}"
              f" → {'目录 ' + a.outdir if a.outdir else '原图旁边'}")
        if not confirm('继续？[y/N]（-y 可跳过确认）'):
            print('已取消')
            return 1

    ok = fail = 0
    for src, rel in items:
        good, line = process_one(src, rel, a)
        print(line)
        ok += good
        fail += not good
    if len(items) > 1:
        print(f'—— 共 {len(items)} 张：成功 {ok}，失败/跳过 {fail}')
    return 1 if fail else 0


if __name__ == '__main__':
    sys.exit(main())
