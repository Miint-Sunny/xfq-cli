# -*- coding: utf-8 -*-
"""--original：读取输入图片的元数据，写入输出文件。

可保留的内容：PNG 文本块（tEXt、iTXt、zTXt）、EXIF、XMP、ICC 色彩配置文件、DPI 和 JPEG 注释。
输出为 JPEG 时无法保存 PNG 文本块，这部分会被略去并在结果中说明。

LSB 隐写等藏在像素中的数据不在此列：它不经过本模块，而是随像素一起被置换，解混淆时随像素一起还原。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image
from PIL.PngImagePlugin import PngInfo

XMP_KEY = 'XML:com.adobe.xmp'      # PNG 中保存 XMP 的 iTXt 关键字


@dataclass
class Metadata:
    texts: dict[str, str] = field(default_factory=dict)   # PNG 文本块，关键字 → 文本
    exif: bytes | None = None
    xmp: bytes | None = None
    icc: bytes | None = None
    dpi: tuple | None = None
    comment: bytes | None = None                          # JPEG 注释（COM 段）

    def items(self) -> list[str]:
        """返回包含的元数据种类，用于结果报告。"""
        out = []
        texts = [k for k in self.texts if k != XMP_KEY]
        if texts:
            out.append(f'文本块 ×{len(texts)}')
        if self.exif:
            out.append('EXIF')
        if self.xmp or XMP_KEY in self.texts:
            out.append('XMP')
        if self.icc:
            out.append('ICC 色彩配置文件')
        if self.dpi:
            out.append('DPI')
        if self.comment:
            out.append('JPEG 注释')
        return out


def read(im: Image.Image) -> Metadata:
    """读取图片的元数据。须在 im.load() 之后调用，PNG 中位于图像数据之后的文本块才会被读到。"""
    info = im.info
    texts = getattr(im, 'text', None)                     # 仅 PNG 提供，包含全部文本块
    xmp = info.get('xmp')
    comment = info.get('comment')
    dpi = info.get('dpi')
    return Metadata(
        texts={k: str(v) for k, v in texts.items()} if isinstance(texts, dict) else {},
        exif=info.get('exif') or None,
        xmp=xmp.encode('utf-8') if isinstance(xmp, str) else (xmp or None),
        icc=info.get('icc_profile') or None,
        dpi=tuple(dpi) if dpi else None,
        comment=comment.encode('utf-8') if isinstance(comment, str) else (comment or None),
    )


def save_options(meta: Metadata, fmt: str) -> tuple[dict, list[str]]:
    """生成写入元数据所需的 Image.save 参数。

    Args:
        fmt: 输出格式，``PNG`` 或 ``JPEG``。

    Returns:
        (参数, 无法写入该格式而被略去的内容)。
    """
    kw, dropped = {}, []
    if meta.icc:
        kw['icc_profile'] = meta.icc
    if meta.exif:
        kw['exif'] = meta.exif
    if meta.dpi:
        kw['dpi'] = meta.dpi
    if fmt == 'PNG':
        info, used = PngInfo(), False
        for k, v in meta.texts.items():
            if k == XMP_KEY:
                info.add_itxt(k, v)                       # PNG 规范要求 XMP 使用 iTXt
            else:
                info.add_text(k, v)                       # 无法用 Latin-1 表示时自动改用 iTXt
            used = True
        if meta.xmp and XMP_KEY not in meta.texts:
            info.add_itxt(XMP_KEY, meta.xmp.decode('utf-8', 'replace'))
            used = True
        if meta.comment and 'Comment' not in meta.texts:  # JPEG 注释改存为 Comment 文本块
            info.add_text('Comment', meta.comment.decode('utf-8', 'replace'))
            used = True
        if used:
            kw['pnginfo'] = info
    else:
        texts = [k for k in meta.texts if k != XMP_KEY]
        if texts:
            dropped.append(f'文本块 ×{len(texts)}')
        xmp = meta.xmp or (meta.texts[XMP_KEY].encode('utf-8') if XMP_KEY in meta.texts else None)
        if xmp:
            kw['xmp'] = xmp
        if meta.comment:
            kw['comment'] = meta.comment
    return kw, dropped
