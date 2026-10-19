"""QR (type: qrcode[pil]) and Code128 (python-barcode) generation.

SVG for Code128 is emitted natively by python-barcode without Pillow. QR uses
qrcode + Pillow to produce PNG; SVG-QR would require lxml, so the QR is served
as a PNG image via an inline data URI (or a dedicated endpoint) — good enough
for label printing and html5-qrcode camera scanning.
"""
import base64
import io

import qrcode
from barcode import Code128
from barcode.writer import ImageWriter, SVGWriter


def code128_svg(data):
    """Return Code128 barcode as an SVG string (no Pillow needed)."""
    buffer = io.BytesIO()
    Code128(str(data), writer=SVGWriter()).write(buffer)
    return buffer.getvalue().decode()


def code128_png(data):
    """Return Code128 barcode as raw PNG bytes (uses Pillow)."""
    buffer = io.BytesIO()
    Code128(str(data), writer=ImageWriter()).write(buffer)
    return buffer.getvalue()


def qr_png_base64(data, box_size=8, border=2):
    """Return a base64-encoded QR code PNG for <img src="data:image/png;base64,...">."""
    qr = qrcode.QRCode(box_size=box_size, border=border, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()
