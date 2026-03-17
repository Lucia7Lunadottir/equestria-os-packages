from PyQt6.QtGui import QImage

from ui.adjustments_dialog import _to_argb32, _in_place_arr


def apply_equalize(src: QImage) -> QImage:
    """Histogram equalisation on luminance (hue is preserved)."""
    img = _to_argb32(src)
    try:
        import numpy as np
        img = img.copy()
        arr = _in_place_arr(img)
        R = arr[:, :, 2].astype(np.float32)
        G = arr[:, :, 1].astype(np.float32)
        B = arr[:, :, 0].astype(np.float32)

        luma     = (0.299 * R + 0.587 * G + 0.114 * B).clip(0, 255).astype(np.uint8)
        hist     = np.bincount(luma.flatten(), minlength=256)
        cdf      = hist.cumsum()
        cdf_min  = int(cdf[cdf > 0][0])
        n        = int(luma.size)
        denom    = max(n - cdf_min, 1)
        lut      = np.clip(
            np.round((cdf - cdf_min) / denom * 255), 0, 255).astype(np.uint8)

        new_luma = lut[luma].astype(np.float32)
        scale    = new_luma / np.maximum(luma.astype(np.float32), 1.0)

        arr[:, :, 2] = np.clip(R * scale, 0, 255).astype(np.uint8)
        arr[:, :, 1] = np.clip(G * scale, 0, 255).astype(np.uint8)
        arr[:, :, 0] = np.clip(B * scale, 0, 255).astype(np.uint8)
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
    except ImportError:
        # Fallback: per-channel equalization
        result = img.copy()
        hists  = [[0] * 256, [0] * 256, [0] * 256]
        total  = result.width() * result.height()
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                hists[0][(px >> 16) & 0xFF] += 1
                hists[1][(px >>  8) & 0xFF] += 1
                hists[2][px & 0xFF] += 1
        luts = []
        for hist in hists:
            cdf = 0; cdf_min = None; lut = [0] * 256
            for i, h in enumerate(hist):
                cdf += h
                if cdf > 0 and cdf_min is None:
                    cdf_min = cdf
                if cdf_min is not None and total > cdf_min:
                    lut[i] = round((cdf - cdf_min) / (total - cdf_min) * 255)
            luts.append(lut)
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                a  = (px >> 24) & 0xFF
                r  = luts[0][(px >> 16) & 0xFF]
                g  = luts[1][(px >>  8) & 0xFF]
                b  = luts[2][px & 0xFF]
                result.setPixel(x, y, (a << 24) | (r << 16) | (g << 8) | b)
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
