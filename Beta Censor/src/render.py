from __future__ import annotations

import cv2
import numpy as np

_CACHE: dict[str, np.ndarray] = {}
_PLACES = {
    "seins": (("qos", 0.02, 0.08, 0.32), ("qos", 0.66, 0.08, 0.32), ("blacked", 0.12, 0.00, 0.76), ("bnwo", 0.22, 0.80, 0.56)),
    "ventre": (("blacked", 0.10, 0.22, 0.80), ("qos", 0.32, 0.48, 0.36), ("bnwo", 0.18, 0.72, 0.64)),
    "entrejambe": (("blacked", 0.08, 0.00, 0.84), ("qos", 0.30, 0.02, 0.40), ("qos", 0.00, 0.40, 0.24), ("qos", 0.76, 0.40, 0.24), ("bnwo", 0.14, 0.82, 0.72)),
    "fesses": (("blacked", 0.14, 0.00, 0.72), ("qos", 0.32, 0.06, 0.36), ("qos", 0.04, 0.44, 0.34), ("qos", 0.62, 0.44, 0.34)),
    "autre": (("qos", 0.28, 0.08, 0.44), ("bnwo", 0.12, 0.78, 0.76)),
}


def apply_style(crop: np.ndarray, style: str) -> np.ndarray:
    if crop.size == 0 or style == "aucun":
        return crop
    h, w = crop.shape[:2]
    if style == "pixel":
        small = cv2.resize(crop, (max(2, w // 14), max(2, h // 14)), interpolation=cv2.INTER_LINEAR)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)
    if style == "flou":
        k = min(71, max(15, (min(w, h) // 6) | 1))
        if k % 2 == 0:
            k += 1
        return cv2.GaussianBlur(crop, (k, k), 0)
    return np.zeros_like(crop)


def render_region(
    crop: np.ndarray,
    style: str,
    bnwo: bool,
    label: str,
    inner: tuple[int, int, int, int] | None = None,
) -> np.ndarray:
    if crop.size == 0:
        return crop
    work = apply_bnwo(crop.copy(), label) if bnwo else crop.copy()
    if style == "aucun" or not bnwo or inner is None:
        return work if style == "aucun" else apply_style(work, style)
    return _censor_inner(work, style, inner)


def pad_box(x, y, w, h, pad, max_w, max_h, min_size=10):
    extra_w = max(w * pad, (min_size - w) * 0.5)
    extra_h = max(h * pad, (min_size - h) * 0.5)
    x1, y1 = int(max(0, x - extra_w)), int(max(0, y - extra_h))
    x2, y2 = int(min(max_w, x + w + extra_w)), int(min(max_h, y + h + extra_h))
    return x1, y1, max(1, x2 - x1), max(1, y2 - y1)


def apply_bnwo(crop: np.ndarray, label: str) -> np.ndarray:
    if crop.size == 0 or min(crop.shape[:2]) < 8:
        return crop
    out, skin = crop.copy(), _skin(crop)
    kind = "seins" if "BREAST" in label else "entrejambe" if ("GENITALIA" in label or "ANUS" in label) else "fesses" if "BUTTOCKS" in label else "ventre" if "BELLY" in label else "autre"
    h, w = out.shape[:2]
    for name, fx, fy, fw in _PLACES[kind]:
        _stamp(out, skin, _sprite(name), int(w * fx), int(h * fy), int(min(w, h) * fw if name == "qos" else w * fw))
    return out


def _censor_inner(tattooed: np.ndarray, style: str, inner: tuple[int, int, int, int]) -> np.ndarray:
    h, w = tattooed.shape[:2]
    ix, iy, iw, ih = inner
    ix, iy = max(0, min(w - 1, ix)), max(0, min(h - 1, iy))
    iw, ih = max(1, min(w - ix, iw)), max(1, min(h - iy, ih))
    out = tattooed.copy()
    patch = tattooed[iy : iy + ih, ix : ix + iw]
    if patch.size:
        out[iy : iy + ih, ix : ix + iw] = apply_style(patch, style)
    mask = np.zeros((h, w), np.float32)
    cv2.ellipse(mask, (ix + iw // 2, iy + ih // 2), (max(1, int(iw * 0.46)), max(1, int(ih * 0.46))), 0, 0, 360, 1.0, -1)
    k = max(7, (min(iw, ih) // 8) | 1) | 1
    mask = cv2.GaussianBlur(mask, (k, k), 0)[:, :, None]
    return np.clip(tattooed.astype(np.float32) * (1 - mask) + out.astype(np.float32) * mask, 0, 255).astype(np.uint8)


def _skin(bgr: np.ndarray) -> np.ndarray:
    y = cv2.inRange(cv2.cvtColor(bgr, cv2.COLOR_BGR2YCrCb), (0, 133, 77), (255, 173, 127))
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    m = cv2.bitwise_or(y, cv2.bitwise_or(cv2.inRange(hsv, (0, 15, 50), (25, 180, 255)), cv2.inRange(hsv, (160, 15, 50), (180, 180, 255))))
    return cv2.GaussianBlur(m, (7, 7), 0)


def _sprite(name: str) -> np.ndarray:
    if name in _CACHE:
        return _CACHE[name]
    img = _qos(240) if name == "qos" else _logo("BLACKED" if name == "blacked" else "BNWO", 560 if name == "blacked" else 380)
    noise = np.random.RandomState(3).normal(0, 5, img.shape).astype(np.float32)
    img = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    _CACHE[name] = img
    return img


def _qos(size: int) -> np.ndarray:
    img = np.zeros((size, size, 4), np.uint8)
    cx, cy, r = size // 2, int(size * 0.40), int(size * 0.20)
    ink, q = (28, 22, 18, 255), (245, 246, 250, 255)
    cv2.circle(img, (cx - r, cy), r, ink, -1, cv2.LINE_AA)
    cv2.circle(img, (cx + r, cy), r, ink, -1, cv2.LINE_AA)
    tip = np.array([[cx - int(size * 0.40), cy], [cx + int(size * 0.40), cy], [cx, int(size * 0.90)]], np.int32)
    cv2.fillConvexPoly(img, tip, ink, cv2.LINE_AA)
    stem = np.array(
        [[cx - int(size * 0.06), int(size * 0.62)], [cx + int(size * 0.06), int(size * 0.62)], [cx + int(size * 0.16), int(size * 0.98)], [cx - int(size * 0.16), int(size * 0.98)]],
        np.int32,
    )
    cv2.fillConvexPoly(img, stem, ink, cv2.LINE_AA)
    cv2.putText(img, "Q", (int(size * 0.34), int(size * 0.50)), cv2.FONT_HERSHEY_DUPLEX, size / 260.0, q, max(1, size // 85), cv2.LINE_AA)
    glow = np.zeros_like(img)
    cv2.ellipse(glow, (int(size * 0.38), int(size * 0.28)), (int(size * 0.10), int(size * 0.06)), -28, 0, 360, (255, 255, 255, 90), -1, cv2.LINE_AA)
    img[:, :, :3] = cv2.add(img[:, :, :3], glow[:, :, :3])
    img[:, :, 3] = cv2.GaussianBlur(img[:, :, 3], (5, 5), 0)
    return img


def _logo(text: str, width: int) -> np.ndarray:
    h = 92
    img = np.zeros((h, width, 4), np.uint8)
    cv2.rectangle(img, (6, 10), (width - 6, h - 10), (18, 16, 14, 255), -1, cv2.LINE_AA)
    cv2.rectangle(img, (6, 10), (width - 6, h - 10), (40, 34, 30, 180), 2, cv2.LINE_AA)
    scale, thick = width / (15.5 * max(4, len(text))), max(2, h // 16)
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_DUPLEX, scale, thick)
    x, y = max(8, (width - tw) // 2), max(th + 8, (h + th) // 2 - 2)
    cv2.putText(img, text, (x, y), cv2.FONT_HERSHEY_DUPLEX, scale, (236, 238, 242, 255), thick, cv2.LINE_AA)
    m = np.float32([[1, -0.18, 10], [0, 1, 0]])
    img = cv2.warpAffine(img, m, (width, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    img[:, :, 3] = cv2.GaussianBlur(np.maximum(img[:, :, 3], cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)), (3, 3), 0)
    return img


def _stamp(dst, skin, sprite, x, y, width) -> None:
    if width < 10:
        return
    sh, sw = sprite.shape[:2]
    nw, nh = max(8, int(width)), max(8, int(width * sh / max(1, sw)))
    dh, dw = dst.shape[:2]
    if x >= dw or y >= dh:
        return
    nw, nh = min(nw, dw - max(0, x)), min(nh, dh - max(0, y))
    if nw < 6 or nh < 6:
        return
    x0, y0 = max(0, x), max(0, y)
    roi = dst[y0 : y0 + nh, x0 : x0 + nw]
    tat = _wrap(cv2.resize(sprite, (nw, nh), interpolation=cv2.INTER_AREA), roi)
    _blend(dst, skin, tat, x0, y0)


def _wrap(sprite: np.ndarray, roi: np.ndarray) -> np.ndarray:
    h, w = roi.shape[:2]
    if sprite.shape[0] != h or sprite.shape[1] != w:
        sprite = cv2.resize(sprite, (w, h), interpolation=cv2.INTER_LINEAR)
    gray = cv2.GaussianBlur(cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY), (9, 9), 0).astype(np.float32)
    gx, gy = cv2.Sobel(gray, cv2.CV_32F, 1, 0, 5), cv2.Sobel(gray, cv2.CV_32F, 0, 1, 5)
    yy, xx = np.indices((h, w), dtype=np.float32)
    nx = xx / max(w - 1, 1) - 0.5
    mx = np.clip(xx + gx * 0.08 + nx * np.abs(nx) * w * 0.05, 0, w - 1)
    my = np.clip(yy + gy * 0.05 + (nx ** 2) * h * 0.11, 0, h - 1)
    return cv2.remap(sprite, mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)


def _blend(dst, skin, tattoo, x, y) -> None:
    th, tw = tattoo.shape[:2]
    roi = dst[y : y + th, x : x + tw]
    if roi.size == 0:
        return
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    spec = np.clip((gray - 0.62) * 3.4, 0, 1)
    shade = np.clip((0.48 - gray) * 2.0, 0, 1)
    alpha = tattoo[:, :, 3].astype(np.float32) / 255.0
    alpha *= 0.28 + 0.72 * (skin[y : y + th, x : x + tw].astype(np.float32) / 255.0)
    alpha *= 0.70 + 0.22 * shade + 0.08 * (1.0 - spec)
    alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
    ink = tattoo[:, :, :3].astype(np.float32)
    base = roi.astype(np.float32)
    lum = cv2.cvtColor(tattoo[:, :, :3], cv2.COLOR_BGR2GRAY).astype(np.float32) / 255.0
    white = np.clip((lum - 0.55) * 2.4, 0, 1) * (tattoo[:, :, 3].astype(np.float32) / 255.0)
    buried = base * (0.42 + 0.58 * ink / 255.0)
    mixed = base * (1 - alpha[..., None]) + buried * alpha[..., None]
    letter = np.clip(base * 0.25 + ink * 0.90, 0, 255)
    mixed = mixed * (1 - white[..., None] * alpha[..., None]) + letter * white[..., None] * alpha[..., None]
    shine = spec[..., None] * alpha[..., None] * 0.28
    dst[y : y + th, x : x + tw] = np.clip(mixed * (1 - shine) + base * shine, 0, 255).astype(np.uint8)
