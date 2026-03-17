"""Color Lookup (LUT) adjustment — loads .cube files and applies them."""

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QFileDialog
from PyQt6.QtGui import QImage

from core.locale import tr
from ui.adjustments_dialog import _to_argb32, _AdjustDialog, _SliderRow


# ── .cube parser ──────────────────────────────────────────────────────────────

def parse_cube(path: str) -> dict | None:
    """Parse a .cube LUT file.

    Returns dict with keys:
      'size'   — int, LUT side length
      'data'   — list of [r,g,b] float triplets (normalised 0..1),
                 ordered R-fastest (r + g*N + b*N*N)
      'domain_min', 'domain_max' — [r,g,b] floats

    Returns None on parse error.
    """
    size = None
    is_3d = True
    domain_min = [0.0, 0.0, 0.0]
    domain_max = [1.0, 1.0, 1.0]
    data: list[list[float]] = []

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                upper = line.upper()
                if upper.startswith("TITLE"):
                    continue
                if upper.startswith("LUT_3D_SIZE"):
                    size = int(line.split()[1])
                    is_3d = True
                elif upper.startswith("LUT_1D_SIZE"):
                    size = int(line.split()[1])
                    is_3d = False
                elif upper.startswith("DOMAIN_MIN"):
                    parts = line.split()
                    domain_min = [float(parts[1]), float(parts[2]), float(parts[3])]
                elif upper.startswith("DOMAIN_MAX"):
                    parts = line.split()
                    domain_max = [float(parts[1]), float(parts[2]), float(parts[3])]
                else:
                    parts = line.split()
                    if len(parts) == 3:
                        try:
                            data.append([float(p) for p in parts])
                        except ValueError:
                            pass
    except OSError:
        return None

    if size is None or not data:
        return None
    expected = size ** 3 if is_3d else size
    if len(data) < expected:
        return None

    return {
        "size": size,
        "is_3d": is_3d,
        "data": data[:expected],
        "domain_min": domain_min,
        "domain_max": domain_max,
    }


# ── pixel function ────────────────────────────────────────────────────────────

def apply_color_lookup(src: QImage, lut: dict, intensity: int) -> QImage:
    """Apply a parsed .cube LUT to *src* at *intensity* % (0..100)."""
    if lut is None:
        return src.copy()

    img = _to_argb32(src)
    size = lut["size"]
    data = lut["data"]
    d = intensity / 100.0

    # ── numpy path ────────────────────────────────────────────────────────────
    try:
        import numpy as np

        lut_arr = np.array(data, dtype=np.float32)  # (N^3, 3)

        img = img.copy()
        ptr = img.bits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, dtype=np.uint8).reshape((img.height(), img.width(), 4))
        B_in = arr[:, :, 0].astype(np.float32) / 255.0
        G_in = arr[:, :, 1].astype(np.float32) / 255.0
        R_in = arr[:, :, 2].astype(np.float32) / 255.0

        if lut["is_3d"]:
            # Reshape to (B, G, R, 3) — R-index varies fastest in .cube spec
            lut3 = lut_arr.reshape(size, size, size, 3)  # axes: b, g, r

            s = size - 1
            ri = np.clip(R_in * s, 0.0, s)
            gi = np.clip(G_in * s, 0.0, s)
            bi = np.clip(B_in * s, 0.0, s)

            r0 = np.floor(ri).astype(np.int32); r1 = np.minimum(r0 + 1, s)
            g0 = np.floor(gi).astype(np.int32); g1 = np.minimum(g0 + 1, s)
            b0 = np.floor(bi).astype(np.int32); b1 = np.minimum(b0 + 1, s)

            rf = (ri - r0)[..., np.newaxis]
            gf = (gi - g0)[..., np.newaxis]
            bf = (bi - b0)[..., np.newaxis]

            # Trilinear interpolation
            out = (lut3[b0, g0, r0] * (1 - rf) * (1 - gf) * (1 - bf) +
                   lut3[b0, g0, r1] * rf        * (1 - gf) * (1 - bf) +
                   lut3[b0, g1, r0] * (1 - rf)  * gf       * (1 - bf) +
                   lut3[b0, g1, r1] * rf         * gf       * (1 - bf) +
                   lut3[b1, g0, r0] * (1 - rf)  * (1 - gf) * bf       +
                   lut3[b1, g0, r1] * rf         * (1 - gf) * bf       +
                   lut3[b1, g1, r0] * (1 - rf)  * gf        * bf       +
                   lut3[b1, g1, r1] * rf         * gf        * bf)
            # out shape: (H, W, 3) — columns are (out_R, out_G, out_B)

        else:
            # 1D LUT: apply per-channel
            lut1 = lut_arr  # (N, 3)
            s = size - 1
            ri = np.clip(R_in * s, 0.0, s)
            gi = np.clip(G_in * s, 0.0, s)
            bi = np.clip(B_in * s, 0.0, s)
            r0 = np.floor(ri).astype(np.int32); r1 = np.minimum(r0 + 1, s)
            g0 = np.floor(gi).astype(np.int32); g1 = np.minimum(g0 + 1, s)
            b0 = np.floor(bi).astype(np.int32); b1 = np.minimum(b0 + 1, s)
            rf = ri - r0; gf = gi - g0; bf = bi - b0
            out_R = lut1[r0, 0] * (1 - rf) + lut1[r1, 0] * rf
            out_G = lut1[g0, 1] * (1 - gf) + lut1[g1, 1] * gf
            out_B = lut1[b0, 2] * (1 - bf) + lut1[b1, 2] * bf
            out = np.stack([out_R, out_G, out_B], axis=-1)

        arr[:, :, 2] = np.clip(R_in * 255 * (1 - d) + out[:, :, 0] * 255 * d,
                               0, 255).astype(np.uint8)
        arr[:, :, 1] = np.clip(G_in * 255 * (1 - d) + out[:, :, 1] * 255 * d,
                               0, 255).astype(np.uint8)
        arr[:, :, 0] = np.clip(B_in * 255 * (1 - d) + out[:, :, 2] * 255 * d,
                               0, 255).astype(np.uint8)
        del arr
        del ptr
        return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    # ── pure-Python fallback (nearest-neighbour) ──────────────────────────────
    except ImportError:
        s = size - 1
        result = img.copy()
        for y in range(result.height()):
            for x in range(result.width()):
                px = result.pixel(x, y)
                a  = (px >> 24) & 0xFF
                r  = (px >> 16) & 0xFF
                g  = (px >>  8) & 0xFF
                b  = px & 0xFF
                ri = round(r / 255.0 * s)
                gi = round(g / 255.0 * s)
                bi = round(b / 255.0 * s)
                idx = ri + gi * size + bi * size * size
                lr, lg, lb = data[idx]
                r2 = int(max(0, min(255, r * (1 - d) + lr * 255 * d)))
                g2 = int(max(0, min(255, g * (1 - d) + lg * 255 * d)))
                b2 = int(max(0, min(255, b * (1 - d) + lb * 255 * d)))
                result.setPixel(x, y, (a << 24) | (r2 << 16) | (g2 << 8) | b2)
        return result.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


# ── dialog ────────────────────────────────────────────────────────────────────

class ColorLookupDialog(_AdjustDialog):
    def __init__(self, image: QImage, parent=None):
        super().__init__(tr("adj.color_lookup.title"), image, parent)
        self.setMinimumWidth(400)
        self._lut: dict | None = None

        # ── File picker row ───────────────────────────────────────────────────
        file_row = QHBoxLayout()
        load_btn = QPushButton(tr("adj.color_lookup.load_btn"))
        load_btn.clicked.connect(self._load_lut)
        self._file_lbl = QLabel(tr("adj.color_lookup.no_file"))
        self._file_lbl.setStyleSheet("color: #7f849c; font-size: 11px;")
        file_row.addWidget(load_btn)
        file_row.addWidget(self._file_lbl, 1)
        self._vbox.addLayout(file_row)

        # ── Intensity slider ──────────────────────────────────────────────────
        self._intensity = _SliderRow(tr("adj.color_lookup.intensity"), 0, 100, 100)
        self._add_row(self._intensity)

        self._seal(reset_fn=self._do_reset)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _load_lut(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("adj.color_lookup.open_dlg"), "",
            tr("adj.color_lookup.filter"))
        if not path:
            return
        lut = parse_cube(path)
        if lut is None:
            self._file_lbl.setText(tr("adj.color_lookup.error"))
            self._file_lbl.setStyleSheet("color: #f38ba8; font-size: 11px;")
            return
        self._lut = lut
        name = path.rsplit("/", 1)[-1]
        self._file_lbl.setText(name)
        self._file_lbl.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        self._on_change()

    def _do_reset(self):
        self._timer.stop()
        self._lut = None
        self._file_lbl.setText(tr("adj.color_lookup.no_file"))
        self._file_lbl.setStyleSheet("color: #7f849c; font-size: 11px;")
        self._intensity.reset()
        self._apply_preview()

    def _apply_preview(self):
        if not getattr(self, "_is_adj_layer", False):
            from PyQt6.QtGui import QPainter
            p = QPainter(self._image)
            p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            if self._lut is None:
                p.drawImage(0, 0, self._original)
            else:
                res = apply_color_lookup(self._orig_argb32, self._lut, self._intensity.value())
                p.drawImage(0, 0, res)
            p.end()
        if hasattr(self, "_canvas_refresh"): self._canvas_refresh()
        elif self.parent() and hasattr(self.parent(), "_canvas_refresh"): self.parent()._canvas_refresh()
