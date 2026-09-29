# -*- coding: utf-8 -*-
"""xfq：小番茄图片混淆的命令行工具。默认解混淆，使用 -e 时混淆；支持批量处理，默认输出 PNG。"""
from __future__ import annotations

import glob
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__
from .argparse_zh import ArgumentParser
from .core import decode, encode, roughness

Image.MAX_IMAGE_PIXELS = None
IMG_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff'}
GLOB_CHARS = ('*', '?', '[')
REPO_URL = 'https://github.com/Miint-Sunny/xfq-cli'


# ---------------------------------------------------------------- 终端输出与文件遍历
def setup_console() -> None:
    """将标准输出与标准错误设为 UTF-8。

    Windows 上重定向到文件或管道时默认编码为 GBK，输出 ✔ 等符号会引发编码错误。
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def _plain() -> bool:
    """判断是否使用 GBK 字符集内的替代符号。环境变量 XFQ_ASCII 设为 1 或 0 可强制开启或关闭。"""
    flag = os.environ.get('XFQ_ASCII')
    if flag is not None:
        return flag not in ('0', '')
    return os.name == 'nt' and not os.environ.get('WT_SESSION')


SYM = {'ok': '√', 'bad': '×'} if _plain() else {'ok': '✔', 'bad': '✗'}


def error(message: str, hint: str | None = None) -> None:
    """向标准错误输出错误信息，可附带一行提示。"""
    sys.stdout.flush()
    print(f'错误：{message}', file=sys.stderr)
    if hint:
        print(f'提示：{hint}', file=sys.stderr)


def warn(message: str) -> None:
    """向标准错误输出警告信息。"""
    sys.stdout.flush()
    print(f'警告：{message}', file=sys.stderr)


def iter_images(paths, recursive: bool = False):
    """遍历输入路径，产出 (图片文件, 相对路径)。

    输入为目录时，相对路径保留目录层级；含 ``* ? [`` 的参数由本函数展开，
    因为 Windows 的 cmd 与 PowerShell 不会为外部程序展开通配符。
    """
    for p in paths:
        p = Path(p)
        if any(ch in str(p) for ch in GLOB_CHARS) and not p.exists():
            matches = sorted(glob.glob(str(p), recursive=True))
            if not matches:
                warn(f'没有与 {p} 匹配的文件')
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
            warn(f'{p} 不存在')


def confirm(prompt: str) -> bool:
    """在终端中请求确认。仅输入 y 或 yes 视为同意；回车、其他输入、Ctrl-C、Ctrl-D 均视为拒绝。"""
    try:
        return input(prompt).strip().lower() in ('y', 'yes')
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def fmt_size(n: float) -> str:
    """格式化文件大小，使用二进制单位（KiB、MiB）。"""
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if n < 1024 or unit == 'GiB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.2f} {unit}'
        n /= 1024
    return f'{n:.2f} GiB'


# ---------------------------------------------------------------- 处理
def output_path(src: Path, rel: Path, opts) -> Path:
    """根据选项确定输出路径。"""
    ext = '.jpg' if opts.jpeg is not None else '.png'
    suffix = opts.suffix if opts.suffix is not None else ('_enc' if opts.encode else '_dec')
    if opts.output:
        return Path(opts.output)
    if opts.outdir:
        return Path(opts.outdir) / rel.with_name(rel.stem + suffix + ext)
    return src.with_name(src.stem + suffix + ext)


def load_pixels(im: Image.Image) -> np.ndarray:
    """读取像素。含透明信息时返回 RGBA，否则返回 RGB；置换按像素进行，与通道数无关。"""
    has_alpha = 'A' in im.mode or (im.mode == 'P' and 'transparency' in im.info)
    return np.asarray(im.convert('RGBA' if has_alpha else 'RGB'))


def process_one(src: Path, rel: Path, opts) -> tuple[str, str]:
    """处理单个文件。

    Returns:
        (status, line)：status 为 ``ok``、``skip`` 或 ``fail``；line 为报告行。
    """
    name = src.name
    dst = output_path(src, rel, opts)
    tag = f'{name} → {dst if opts.output or opts.outdir else dst.name}'
    if dst.exists() and not opts.overwrite:
        return 'skip', f'· {name}  已跳过：输出文件 {dst.name} 已存在（使用 --overwrite 覆盖）'
    try:
        with Image.open(src) as im:
            im.load()
            arr = load_pixels(im)
        before = roughness(arr)
        out = encode(arr) if opts.encode else decode(arr)
        after = roughness(out)
        change = f'粗糙度 {before:.1f} → {after:.1f}'
        note = ''
        # 解混淆后粗糙度未下降，说明输入很可能不是小番茄混淆图，或已经是原图。
        # 以 30 张实际图片校准：混淆图解混淆后的比值为 0.46–0.79（含经 JPEG 90 压缩的图片），
        # 原图的比值为 1.41–2.17。阈值 1.0 与两侧均有足够距离。
        if not opts.encode and after >= before:
            if not opts.force:
                return 'skip', (f'· {name}  已跳过：解混淆后粗糙度未下降（{before:.1f} → {after:.1f}），'
                                f'输入可能不是小番茄混淆图（使用 -f 仍写出）')
            note = '（注意：粗糙度未下降，输入可能不是小番茄混淆图，已按 -f 写出）'
        size = f'{arr.shape[1]}×{arr.shape[0]}'
        if opts.dry_run:
            return 'ok', f'· {tag}  [试运行] {size}；{change}{note}'
        dst.parent.mkdir(parents=True, exist_ok=True)
        result = Image.fromarray(out)
        tmp = dst.with_name(dst.name + '.tmp~')
        if opts.jpeg is not None:
            result.convert('RGB').save(tmp, format='JPEG', quality=opts.jpeg, subsampling=0)
        else:
            result.save(tmp, format='PNG')
        os.replace(tmp, dst)
        what = '已混淆' if opts.encode else '已解混淆'
        return 'ok', f'{SYM["ok"]} {tag}  {what} {size}；{change}；{fmt_size(dst.stat().st_size)}{note}'
    except Exception as e:
        return 'fail', f'{SYM["bad"]} {name}  处理失败：{e}'


def summary(counts: Counter) -> str:
    """返回批量处理的汇总行。"""
    total = sum(counts.values())
    return f'完成：共 {total} 个文件，成功 {counts["ok"]} 个，跳过 {counts["skip"]} 个，失败 {counts["fail"]} 个'


# ---------------------------------------------------------------- 命令行
EPILOG = f'''\
解混淆校验：
  解混淆后计算相邻像素的平均差异（粗糙度）。正确解混淆的图片粗糙度明显下降；
  粗糙度未下降时，输入很可能不是小番茄混淆图，默认跳过该文件，使用 -f 仍写出。

示例：
  xfq a.jpg                  解混淆，输出 a_dec.png
  xfq -e a.png               混淆，输出 a_enc.png
  xfq -r ./in -d ./out       递归处理目录，结果写入 ./out
  xfq -e *.png --jpeg        混淆并输出 JPEG（质量 95）
  xfq a.jpg -n               试运行，只报告粗糙度变化

文档：{REPO_URL}'''


def build_parser() -> ArgumentParser:
    ap = ArgumentParser(
        prog='xfq',
        description='小番茄图片混淆的命令行工具。默认对输入图片解混淆，使用 -e 时进行混淆。\n'
                    '默认输出无损 PNG；输入为目录或通配符时，处理前请求确认。',
        epilog=EPILOG, add_help=False)
    ap.add_argument('paths', nargs='*', metavar='PATH', help='图片文件或目录，支持通配符')

    g = ap.add_argument_group('模式')
    g.add_argument('-e', '--encode', action='store_true', help='混淆图片（默认：解混淆）')
    g.add_argument('-f', '--force', action='store_true', help='解混淆结果未通过粗糙度校验时仍写出文件')

    g = ap.add_argument_group('输出')
    dest = g.add_mutually_exclusive_group()
    dest.add_argument('-o', '--output', metavar='FILE', help='输出文件，仅适用于单个输入文件')
    dest.add_argument('-d', '--outdir', metavar='DIR', help='输出目录；输入为目录时保留相对路径')
    g.add_argument('--suffix', metavar='SUFFIX', help='输出文件名后缀（默认：解混淆为 _dec，混淆为 _enc）')
    g.add_argument('--jpeg', nargs='?', const=95, type=int, metavar='QUALITY',
                   help='输出 JPEG 而非 PNG，QUALITY 取值 1–100（默认：95）')
    g.add_argument('--overwrite', action='store_true', help='覆盖已存在的输出文件（默认：跳过）')

    g = ap.add_argument_group('其他')
    g.add_argument('-h', '--help', action='help', help='显示此帮助信息并退出')
    g.add_argument('-r', '--recursive', action='store_true', help='递归处理子目录')
    g.add_argument('-n', '--dry-run', action='store_true', help='试运行：计算并报告结果，不写入文件')
    g.add_argument('-y', '--yes', action='store_true', help='处理目录或通配符时不请求确认')
    g.add_argument('-V', '--version', action='version', version=f'xfq-cli {__version__}', help='显示版本信息并退出')
    return ap


def main(argv=None) -> int:
    setup_console()
    ap = build_parser()
    a = ap.parse_args(argv)
    if a.jpeg is not None and not 1 <= a.jpeg <= 100:
        ap.error(f'参数 --jpeg：QUALITY 须在 1–100 之间：{a.jpeg}')

    items = list(iter_images(a.paths, a.recursive))
    if not items:
        error('未找到图片文件', '使用 xfq -h 查看用法')
        return 1
    if a.output and len(items) > 1:
        error('-o 只能用于单个输入文件', '处理多个文件时，使用 -d DIR 指定输出目录')
        return 1
    # 目录与通配符属于批量操作，处理前请求确认；逐个指定的文件不确认
    batch = [p for p in a.paths if Path(p).is_dir() or any(ch in p for ch in GLOB_CHARS)]
    if batch and not a.yes and not a.dry_run:
        ext = Counter(f.suffix.lower().lstrip('.') for f, _ in items)
        kinds = '、'.join(f'{k} {n}' for k, n in ext.most_common())
        mode = '混淆' if a.encode else '解混淆'
        dest = f'输出到目录 {a.outdir}' if a.outdir else '输出到源文件所在目录'
        print(f"{'、'.join(batch)}：共 {len(items)} 个文件（{kinds}），{mode}，{dest}")
        if not confirm('是否继续？[y/N] '):
            print('已取消')
            return 1

    counts = Counter()
    for src, rel in items:
        status, line = process_one(src, rel, a)
        print(line)
        counts[status] += 1
    if len(items) > 1:
        print(summary(counts))
    return 1 if counts['fail'] else 0


if __name__ == '__main__':
    sys.exit(main())
