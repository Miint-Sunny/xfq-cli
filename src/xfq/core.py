# -*- coding: utf-8 -*-
"""小番茄图片混淆算法。

该算法是像素置换，不是加密：

1. 为 W×H 的图像生成一条广义希尔伯特曲线（Gilbert 曲线），按曲线顺序将全部像素排成一维序列；
2. 将序列整体循环移位 round((√5 − 1) / 2 × W × H) 个位置（黄金分割比）；
3. 解混淆时反向移位。

算法没有密钥，全部参数由图像尺寸决定。曲线具有局部性，混淆结果呈色块状而非随机噪点，
因此能承受平台的有损压缩。

与以下实现的结果一致：奇点站 hideImg1.html、iris10086/pic-scramble、PicEncrypt（TomatoScramble.java）、
sd-image-sorter。本文件依据算法独立实现，未复制上述任何代码。
"""
from __future__ import annotations

import math
import sys
from functools import lru_cache

import numpy as np

sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))


def _sign(v: int) -> int:
    return (v > 0) - (v < 0)


def _generate2d(x: int, y: int, ax: int, ay: int, bx: int, by: int, width: int, out: list) -> None:
    """递归生成 Gilbert 曲线，将经过的像素以行优先线性下标（x + y × width）追加到 out。"""
    w = abs(ax + ay)
    h = abs(bx + by)
    dax, day = _sign(ax), _sign(ay)          # 主方向的单位向量
    dbx, dby = _sign(bx), _sign(by)          # 正交方向的单位向量
    if h == 1:                               # 单行
        for _ in range(w):
            out.append(x + y * width)
            x += dax
            y += day
        return
    if w == 1:                               # 单列
        for _ in range(h):
            out.append(x + y * width)
            x += dbx
            y += dby
        return
    ax2, ay2 = ax // 2, ay // 2              # Python 的 // 对负数同样向下取整，与 JS 的 Math.floor 一致
    bx2, by2 = bx // 2, by // 2
    w2 = abs(ax2 + ay2)
    h2 = abs(bx2 + by2)
    if 2 * w > 3 * h:                        # 宽高比过大时只分为两段
        if (w2 % 2) and (w > 2):
            ax2 += dax
            ay2 += day
        _generate2d(x, y, ax2, ay2, bx, by, width, out)
        _generate2d(x + ax2, y + ay2, ax - ax2, ay - ay2, bx, by, width, out)
        return
    if (h2 % 2) and (h > 2):                 # 一般情况：分为三段
        bx2 += dbx
        by2 += dby
    _generate2d(x, y, bx2, by2, ax2, ay2, width, out)
    _generate2d(x + bx2, y + by2, ax, ay, bx - bx2, by - by2, width, out)
    _generate2d(x + (ax - dax) + (bx2 - dbx), y + (ay - day) + (by2 - dby),
                -bx2, -by2, -(ax - ax2), -(ay - ay2), width, out)


@lru_cache(maxsize=16)
def curve(width: int, height: int) -> np.ndarray:
    """返回按曲线顺序排列的像素线性下标（行优先，x + y × width）。结果按尺寸缓存。"""
    if width <= 0 or height <= 0:
        return np.zeros(0, dtype=np.int64)
    out: list = []
    if width >= height:
        _generate2d(0, 0, width, 0, 0, height, width, out)
    else:
        _generate2d(0, 0, 0, height, width, 0, width, out)
    return np.asarray(out, dtype=np.int64)


def offset(pixel_count: int) -> int:
    """返回循环移位量。

    使用 floor(x + 0.5) 而非 Python 的 round()：参考实现使用 JS 的 Math.round，
    Python 的 round() 对 .5 采用银行家舍入，结果可能相差 1。
    """
    return math.floor((math.sqrt(5) - 1) / 2 * pixel_count + 0.5)


def permutation(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """返回置换下标 (src, dst)。混淆时 out[dst[i]] = in[src[i]]，解混淆时方向相反。"""
    c = curve(width, height)
    return c, np.roll(c, -offset(c.size))


def encode(arr: np.ndarray) -> np.ndarray:
    """混淆图像。arr 为 (H, W) 或 (H, W, C) 数组；按像素整体移动，与通道数无关。"""
    h, w = arr.shape[:2]
    src, dst = permutation(w, h)
    flat = arr.reshape(h * w, -1)
    out = np.empty_like(flat)
    out[dst] = flat[src]
    return out.reshape(arr.shape)


def decode(arr: np.ndarray) -> np.ndarray:
    """解混淆图像，是 :func:`encode` 的逆运算。"""
    h, w = arr.shape[:2]
    src, dst = permutation(w, h)
    flat = arr.reshape(h * w, -1)
    out = np.empty_like(flat)
    out[src] = flat[dst]
    return out.reshape(arr.shape)


def roughness(arr: np.ndarray) -> float:
    """返回相邻像素的平均差异（粗糙度），仅计算 RGB 通道。

    混淆图像的粗糙度较高，正确解混淆后明显下降。命令行据此判断输入是否为小番茄混淆图。
    """
    a = arr.astype(np.int16)
    if a.ndim == 3:
        a = a[:, :, :3]
    dx = np.abs(np.diff(a, axis=1)).mean() if a.shape[1] > 1 else 0.0
    dy = np.abs(np.diff(a, axis=0)).mean() if a.shape[0] > 1 else 0.0
    return float(dx + dy) / 2
