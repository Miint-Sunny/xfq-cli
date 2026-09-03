# -*- coding: utf-8 -*-
"""小番茄图片混淆的算法本体。

这不是加密，是像素置换：
  1. 对 W×H 的图生成一条广义希尔伯特曲线（Gilbert 曲线），把所有像素按曲线顺序排成一维；
  2. 整体循环移位 round((√5 − 1) / 2 × W × H) 个位置（黄金分割）；
  3. 解混淆就是反向移位。
没有密码，参数全由尺寸决定。曲线保持局部性，所以混淆后是色块糊成一片而不是纯噪点，经得起平台二压。
算法和奇点站 hideImg1.html、iris10086/pic-scramble、PicEncrypt（TomatoScramble.java）、sd-image-sorter 一致，
本文件按算法自己写，未复制任何一方代码。
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
    """Gilbert 曲线递归。out 里直接放线性下标 x + y*width。"""
    w = abs(ax + ay)
    h = abs(bx + by)
    dax, day = _sign(ax), _sign(ay)          # 主方向单位向量
    dbx, dby = _sign(bx), _sign(by)          # 正交方向单位向量
    if h == 1:                               # 一行
        for _ in range(w):
            out.append(x + y * width)
            x += dax
            y += day
        return
    if w == 1:                               # 一列
        for _ in range(h):
            out.append(x + y * width)
            x += dbx
            y += dby
        return
    ax2, ay2 = ax // 2, ay // 2              # Python 的 // 就是 Math.floor，负数也对
    bx2, by2 = bx // 2, by // 2
    w2 = abs(ax2 + ay2)
    h2 = abs(bx2 + by2)
    if 2 * w > 3 * h:                        # 太扁：只切两段
        if (w2 % 2) and (w > 2):
            ax2 += dax
            ay2 += day
        _generate2d(x, y, ax2, ay2, bx, by, width, out)
        _generate2d(x + ax2, y + ay2, ax - ax2, ay - ay2, bx, by, width, out)
        return
    if (h2 % 2) and (h > 2):                 # 标准：上一步、横一长段、下一步
        bx2 += dbx
        by2 += dby
    _generate2d(x, y, bx2, by2, ax2, ay2, width, out)
    _generate2d(x + bx2, y + by2, ax, ay, bx - bx2, by - by2, width, out)
    _generate2d(x + (ax - dax) + (bx2 - dbx), y + (ay - day) + (by2 - dby),
                -bx2, -by2, -(ax - ax2), -(ay - ay2), width, out)


@lru_cache(maxsize=16)
def curve(width: int, height: int) -> np.ndarray:
    """曲线顺序下的像素线性下标（行优先 x + y*width）。同尺寸的图只算一次。"""
    if width <= 0 or height <= 0:
        return np.zeros(0, dtype=np.int64)
    out: list = []
    if width >= height:
        _generate2d(0, 0, width, 0, 0, height, width, out)
    else:
        _generate2d(0, 0, 0, height, width, 0, width, out)
    return np.asarray(out, dtype=np.int64)


def offset(pixel_count: int) -> int:
    """黄金分割偏移。用 floor(x + 0.5) 而不是 Python 的 round()：参考实现是 JS 的 Math.round。"""
    return math.floor((math.sqrt(5) - 1) / 2 * pixel_count + 0.5)


def permutation(width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """返回 (src, dst)：混淆时 out[dst[i]] = in[src[i]]，解混淆反过来。"""
    c = curve(width, height)
    return c, np.roll(c, -offset(c.size))


def encode(arr: np.ndarray) -> np.ndarray:
    """混淆。arr 是 (H, W, C) 或 (H, W) 的数组，逐像素整体搬动，通道数无所谓。"""
    h, w = arr.shape[:2]
    src, dst = permutation(w, h)
    flat = arr.reshape(h * w, -1)
    out = np.empty_like(flat)
    out[dst] = flat[src]
    return out.reshape(arr.shape)


def decode(arr: np.ndarray) -> np.ndarray:
    """解混淆。"""
    h, w = arr.shape[:2]
    src, dst = permutation(w, h)
    flat = arr.reshape(h * w, -1)
    out = np.empty_like(flat)
    out[src] = flat[dst]
    return out.reshape(arr.shape)


def roughness(arr: np.ndarray) -> float:
    """相邻像素平均差异。混淆过的图这个值很大，解对了会掉一个量级；用来判断「这图到底是不是小番茄」。"""
    a = arr.astype(np.int16)
    if a.ndim == 3:
        a = a[:, :, :3]
    dx = np.abs(np.diff(a, axis=1)).mean() if a.shape[1] > 1 else 0.0
    dy = np.abs(np.diff(a, axis=0)).mean() if a.shape[0] > 1 else 0.0
    return float(dx + dy) / 2
