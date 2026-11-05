# -*- coding: utf-8 -*-
"""LSB 隐写的检测与清除。

NovelAI 等工具会把生成参数写进像素的最低位（stealth pnginfo）。比特流按列优先排列：
[magic，15 字节][数据长度，32 位大端，单位为比特][数据][FEC 长度，32 位][FEC]。
magic 为 stealth_pnginfo、stealth_pngcomp（alpha 通道，后者经 gzip 压缩），
或 stealth_rgbinfo、stealth_rgbcomp（RGB 三通道）。格式定义见
https://github.com/NovelAI/novelai-image-metadata ，检测与清除逻辑与 nai-meta 相同。

xfq 只在混淆时清除隐写数据，使用 --original 时保留。隐写数据写在原图顺序的像素上，混淆后即被打乱，
因此在混淆前检测输入图片。解混淆如实还原原图，不检测也不清除隐写。
"""
from __future__ import annotations

import gzip
from dataclasses import dataclass

import numpy as np

MAGICS = {
    'stealth_pnginfo': ('alpha', False),
    'stealth_pngcomp': ('alpha', True),
    'stealth_rgbinfo': ('rgb', False),
    'stealth_rgbcomp': ('rgb', True),
}
SIG_BITS = 15 * 8           # 四种 magic 长度相同
LEN_BITS = 32
HEADER_BITS = SIG_BITS + LEN_BITS


@dataclass
class Stealth:
    channel: str            # 'alpha' 或 'rgb'
    compressed: bool
    used_bits: int          # 头部、数据与 FEC 段共占用的最低位数量，清除时使用
    nbytes: int             # 数据解压后的字节数

    def describe(self) -> str:
        """返回简短描述，如 ``alpha+gzip 4726 B``。"""
        return f"{self.channel}{'+gzip' if self.compressed else ''} {self.nbytes} B"


def _lsb_stream(arr: np.ndarray, channel: str) -> np.ndarray:
    """提取最低位比特流，按列优先顺序（先遍历一列的所有行，再到下一列）。"""
    if channel == 'alpha':
        return (arr[:, :, 3] & 1).T.reshape(-1)
    return (arr[:, :, :3] & 1).transpose(1, 0, 2).reshape(-1)    # 每个像素依次提供 R、G、B 三个比特


def find(arr: np.ndarray) -> Stealth | None:
    """检测像素数组中的 LSB 隐写。

    Args:
        arr: H×W×3（RGB）或 H×W×4（RGBA）的 uint8 数组。RGBA 依次检查 alpha 通道与 RGB 通道。

    Returns:
        检测结果；未检测到时返回 None。
    """
    if arr.ndim != 3 or arr.shape[2] not in (3, 4):
        return None
    for channel in (('alpha', 'rgb') if arr.shape[2] == 4 else ('rgb',)):
        st = _decode(arr, channel)
        if st:
            return st
    return None


def _decode(arr: np.ndarray, channel: str) -> Stealth | None:
    bits = _lsb_stream(arr, channel)
    if bits.size < HEADER_BITS:
        return None
    magic = np.packbits(bits[:SIG_BITS]).tobytes().decode('ascii', 'replace')
    if magic not in MAGICS or MAGICS[magic][0] != channel:
        return None
    compressed = MAGICS[magic][1]
    n_bits = int.from_bytes(np.packbits(bits[SIG_BITS:HEADER_BITS]).tobytes(), 'big')
    # 长度须为正数、按字节对齐且不超出图像容量，否则视为噪声误匹配
    if n_bits <= 0 or n_bits % 8 or HEADER_BITS + n_bits > bits.size:
        return None
    payload = np.packbits(bits[HEADER_BITS:HEADER_BITS + n_bits]).tobytes()
    if compressed:
        try:
            payload = gzip.decompress(payload)
        except Exception:                        # magic 匹配但数据已损坏
            return None
    used = HEADER_BITS + n_bits
    # 官方格式（alpha 通道）在数据之后有可选的 FEC 段：32 位长度（比特），0xffffffff 表示无，一并计入清除范围
    if channel == 'alpha' and used + LEN_BITS <= bits.size:
        fec_len = int.from_bytes(np.packbits(bits[used:used + LEN_BITS]).tobytes(), 'big')
        if fec_len == 0xFFFFFFFF:
            used += LEN_BITS
        elif fec_len > 0 and fec_len % 8 == 0 and used + LEN_BITS + fec_len <= bits.size:
            used += LEN_BITS + fec_len
    return Stealth(channel, compressed, used, len(payload))


def wipe(arr: np.ndarray, st: Stealth) -> None:
    """就地清除隐写数据占用的最低位，不修改占用区域以外的像素。

    alpha 通道中 ≥ 254 的像素设为 255（隐写写在不透明的 alpha 上，254 均由写入产生），其余清除最低位。
    """
    h = arr.shape[0]
    idx = np.arange(st.used_bits)
    if st.channel == 'alpha':
        rows, cols = idx % h, idx // h
        a = arr[rows, cols, 3]
        arr[rows, cols, 3] = np.where(a >= 254, 255, a & 0xFE)
    else:
        pix = idx // 3
        arr[pix % h, pix // h, idx % 3] &= 0xFE


def normalize_opaque_alpha(arr: np.ndarray) -> int:
    """alpha 均 ≥ 254 且含 254 时，全部设为 255。

    用于清除未识别格式写入 alpha 最低位的数据；alpha 254 与 255 在显示上没有区别。

    Returns:
        由 254 改为 255 的像素数。
    """
    if arr.ndim != 3 or arr.shape[2] != 4:
        return 0
    a = arr[:, :, 3]
    if a.min() < 254:
        return 0
    count = int(np.count_nonzero(a == 254))
    if count:
        a[...] = 255
    return count
