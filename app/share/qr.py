# -*- coding: utf-8 -*-
"""二维码生成（给界面直接显示用）。"""
from __future__ import annotations

import io

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
    _HAS_QR = True
except Exception:  # pragma: no cover
    _HAS_QR = False


def available() -> bool:
    return _HAS_QR


def make_image(data: str, box: int = 10, border: int = 3,
               fill: str = "#101722", back: str = "#ffffff"):
    """返回 PIL.Image，失败返回 None。"""
    if not _HAS_QR or not data:
        return None
    try:
        qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_M,
                           box_size=box, border=border)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color=fill, back_color=back).convert("RGB")
        return img
    except Exception:
        return None


def make_png_bytes(data: str, box: int = 10, border: int = 3) -> bytes | None:
    img = make_image(data, box=box, border=border)
    if img is None:
        return None
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_svg(data: str, border: int = 3) -> str | None:
    """不依赖 PIL 的 SVG 版二维码（网页/文档里可用）。"""
    if not _HAS_QR or not data:
        return None
    try:
        import qrcode.image.svg as svg_mod

        factory = svg_mod.SvgPathImage
        qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, border=border,
                           image_factory=factory)
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image()
        buf = io.BytesIO()
        img.save(buf)
        return buf.getvalue().decode("utf-8")
    except Exception:
        return None
