from __future__ import annotations

import os
from typing import Any

import cv2
import numpy as np

LABELS = [
    "FEMALE_GENITALIA_COVERED", "FACE_FEMALE", "BUTTOCKS_EXPOSED", "FEMALE_BREAST_EXPOSED",
    "FEMALE_GENITALIA_EXPOSED", "MALE_BREAST_EXPOSED", "ANUS_EXPOSED", "FEET_EXPOSED",
    "BELLY_COVERED", "FEET_COVERED", "ARMPITS_COVERED", "ARMPITS_EXPOSED", "FACE_MALE",
    "BELLY_EXPOSED", "MALE_GENITALIA_EXPOSED", "ANUS_COVERED", "FEMALE_BREAST_COVERED", "BUTTOCKS_COVERED",
]
FACE = {"FACE_FEMALE"}
FEET, ARMPIT = {"FEET_EXPOSED", "FEET_COVERED"}, {"ARMPITS_EXPOSED", "ARMPITS_COVERED"}
MALE = {"MALE_BREAST_EXPOSED", "MALE_GENITALIA_EXPOSED", "FACE_MALE"}
FEMALE = {"FACE_FEMALE", "FEMALE_BREAST_EXPOSED", "FEMALE_BREAST_COVERED", "FEMALE_GENITALIA_EXPOSED", "FEMALE_GENITALIA_COVERED"}


class NudeSession:
    def __init__(self) -> None:
        import nudenet
        import onnxruntime as ort

        model = os.path.join(os.path.dirname(nudenet.__file__), "320n.onnx")
        available = list(ort.get_available_providers())
        providers = [p for p in ("DmlExecutionProvider", "CUDAExecutionProvider", "CPUExecutionProvider") if p in available] or None
        self.session = ort.InferenceSession(model, providers=providers)
        self.input_name = self.session.get_inputs()[0].name
        self.size = 320
        self.provider = (self.session.get_providers() or ["CPUExecutionProvider"])[0]

    def detect_batch(self, images_rgba: list[np.ndarray], score_thresh: float, nms_thresh: float = 0.52, batch_size: int = 8):
        all_dets: list[list[dict[str, Any]]] = []
        for i in range(0, len(images_rgba), batch_size):
            chunk = images_rgba[i : i + batch_size]
            blobs, meta = [], []
            for image in chunk:
                blob, info = _blob(image, self.size)
                blobs.append(blob)
                meta.append(info)
            outputs = self.session.run(None, {self.input_name: np.vstack(blobs)})
            for j, info in enumerate(meta):
                all_dets.append(_postprocess([outputs[0][j : j + 1]], info, self.size, score_thresh, nms_thresh))
        return all_dets


def _blob(image: np.ndarray, target: int):
    mat = image
    if mat.ndim == 2:
        mat = cv2.cvtColor(mat, cv2.COLOR_GRAY2BGR)
    elif mat.shape[2] == 4:
        mat = cv2.cvtColor(mat, cv2.COLOR_RGBA2BGR)
    h, w = mat.shape[:2]
    x_pad, y_pad = max(h, w) - w, max(h, w) - h
    padded = cv2.copyMakeBorder(mat, 0, y_pad, 0, x_pad, cv2.BORDER_CONSTANT)
    blob = cv2.dnn.blobFromImage(padded, 1 / 255.0, (target, target), (0, 0, 0), swapRB=True, crop=False)
    return blob, (w, h, x_pad, y_pad)


def _postprocess(output, info, model_size, score_thresh, nms_thresh):
    orig_w, orig_h, x_pad, y_pad = info
    raw = np.transpose(np.squeeze(output[0]))
    if raw.ndim != 2 or raw.shape[0] == 0:
        return []
    class_scores = raw[:, 4:]
    scores = class_scores.max(axis=1)
    keep = scores >= score_thresh
    if not np.any(keep):
        return []
    raw, scores, class_ids = raw[keep], scores[keep], class_scores[keep].argmax(axis=1)
    cx, cy, bw, bh = raw[:, 0], raw[:, 1], raw[:, 2], raw[:, 3]
    scale_w, scale_h = (orig_w + x_pad) / model_size, (orig_h + y_pad) / model_size
    x = np.clip((cx - bw / 2) * scale_w, 0, orig_w)
    y = np.clip((cy - bh / 2) * scale_h, 0, orig_h)
    w = np.minimum(bw * scale_w, orig_w - x)
    h = np.minimum(bh * scale_h, orig_h - y)
    boxes = np.stack([x, y, w, h], axis=1).tolist()
    score_list = scores.astype(float).tolist()
    indices = cv2.dnn.NMSBoxes(boxes, score_list, float(score_thresh), float(nms_thresh))
    if indices is None or len(indices) == 0:
        return []
    out = []
    for idx in np.array(indices).flatten():
        class_id = int(class_ids[int(idx)])
        if 0 <= class_id < len(LABELS):
            bx, by, bw_, bh_ = boxes[int(idx)]
            out.append({"class": LABELS[class_id], "score": float(score_list[int(idx)]), "box": [float(bx), float(by), float(bw_), float(bh_)]})
    return out


def _iou_box(a, b) -> float:
    ax, ay, aw, ah, bx, by, bw, bh = *a[:4], *b[:4]
    ix1, iy1, ix2, iy2 = max(ax, bx), max(ay, by), min(ax + aw, bx + bw), min(ay + ah, by + bh)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = aw * ah + bw * bh - inter
    return inter / union if union > 0 else 0.0


def _nms(dets, iou_thresh=0.55):
    by: dict[str, list] = {}
    for d in dets:
        by.setdefault(d[4], []).append(d)
    kept = []
    for group in by.values():
        group = sorted(group, key=lambda d: d[5], reverse=True)
        while group:
            best = group.pop(0)
            kept.append(best)
            group = [o for o in group if _iou_box(best, o) < iou_thresh]
    return kept


class BodyDetector:
    def __init__(self) -> None:
        self._inner: NudeSession | None = None

    @property
    def provider(self) -> str:
        return self._inner.provider if self._inner else "CPUExecutionProvider"

    def load(self) -> None:
        if self._inner is None:
            self._inner = NudeSession()

    def detect(self, frame_bgr, enabled: set[str], confidence: float, grid=(3, 2), tiny=True, max_refine=28, max_skin=16):
        if self._inner is None:
            raise RuntimeError("Modèle non chargé")
        h, w = frame_bgr.shape[:2]
        if w <= 0 or h <= 0 or not enabled:
            return []
        frame_bgr = _enhance(frame_bgr)
        rgba = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGBA if frame_bgr.shape[2] == 3 else cv2.COLOR_BGRA2RGBA)
        tiles = _grid(w, h, *grid, 0.42)
        crops, origins, scales = _prep([np.ascontiguousarray(rgba[y : y + th, x : x + tw]) for x, y, tw, th in tiles], [(x, y) for x, y, _, _ in tiles])
        parsed, faces, males, females = self._run(crops, origins, scales, enabled, confidence)
        refine = []
        for fx, fy, fw, fh, _ in sorted(faces, key=lambda f: f[2] * f[3], reverse=True):
            box = _face_body(fx, fy, fw, fh, w, h)
            if box and all(_rect_iou(box, p) <= 0.55 for p in refine):
                refine.append(box)
            if len(refine) >= max_refine:
                break
        if tiny:
            for box in _skin_boxes(frame_bgr, max_skin):
                if all(_rect_iou(box, p) <= 0.5 for p in refine):
                    refine.append(box)
        if refine:
            more, _, m2, f2 = self._run(*_prep([np.ascontiguousarray(rgba[y : y + bh, x : x + bw]) for x, y, bw, bh in refine], [(x, y) for x, y, _, _ in refine]), enabled, confidence)
            parsed.extend(more)
            males.extend(m2)
            females.extend(f2)
        return _nms(_drop_male(parsed, males, females), 0.45)

    def _run(self, crops, origins, scales, enabled, confidence):
        out, faces, males, females = [], [], [], []
        if not crops or self._inner is None:
            return out, faces, males, females
        for origin, scale, raw in zip(origins, scales, self._inner.detect_batch(crops, 0.05, 0.48, 8)):
            ox, oy = origin
            inv = 1.0 / scale if scale else 1.0
            for item in raw or []:
                label, score, box = str(item.get("class", "")), float(item.get("score", 0.0)), item.get("box") or []
                if len(box) < 4:
                    continue
                x, y, bw, bh = [float(v) * inv for v in box[:4]]
                if bw < 0.4 or bh < 0.4:
                    continue
                ax, ay = x + ox, y + oy
                det = (ax, ay, bw, bh, label, score)
                if label in MALE:
                    males.append(det)
                    continue
                if label in FEMALE:
                    females.append(det)
                if label in FACE:
                    faces.append((ax, ay, bw, bh, score))
                need = confidence * (0.70 if label in FEMALE else 0.72 if label in FEET else 0.82 if label in ARMPIT else 1.0)
                if label in enabled and score >= need:
                    out.append(det)
        return out, faces, males, females


def _grid(width, height, cols, rows, overlap):
    tiles = [(0, 0, width, height)]
    cols, rows, extra = max(1, cols), max(1, rows), max(0.0, min(0.5, overlap))
    tw, th = min(width, int(width / cols * (1 + extra))), min(height, int(height / rows * (1 + extra)))
    if tw < 48 or th < 48:
        return tiles
    xs = (width - tw) / max(1, cols - 1) if cols > 1 else 0
    ys = (height - th) / max(1, rows - 1) if rows > 1 else 0
    seen = set(tiles)
    for r in range(rows):
        for c in range(cols):
            x = min(int(round(c * xs)) if cols > 1 else 0, max(0, width - tw))
            y = min(int(round(r * ys)) if rows > 1 else 0, max(0, height - th))
            tile = (x, y, tw, th)
            if tile not in seen:
                seen.add(tile)
                tiles.append(tile)
    return tiles


def _enhance(bgr: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(bgr, cv2.COLOR_BGR2LAB)
    l, a, b = cv2.split(lab)
    l = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8)).apply(l)
    return cv2.cvtColor(cv2.merge((l, a, b)), cv2.COLOR_LAB2BGR)


def _face_body(x, y, w, h, max_w, max_h):
    x1, y1 = int(max(0, x - w * 1.05)), int(max(0, y - h * 0.2))
    x2, y2 = int(min(max_w, x + w * 2.05)), int(min(max_h, y + h * 7.2))
    bw, bh = x2 - x1, y2 - y1
    return None if bw < 12 or bh < 12 else (x1, y1, bw, bh)


def _center(d):
    return d[0] + d[2] * 0.5, d[1] + d[3] * 0.5


def _drop_male(dets, males, females):
    if not dets:
        return dets
    kept = []
    for d in dets:
        if d[4] in MALE or "MALE" in d[4]:
            continue
        if d[4] in FEMALE:
            kept.append(d)
            continue
        cx, cy = _center(d)
        md = min(( (cx - _center(m)[0]) ** 2 + (cy - _center(m)[1]) ** 2 for m in males), default=1e18)
        fd = min(( (cx - _center(f)[0]) ** 2 + (cy - _center(f)[1]) ** 2 for f in females), default=1e18)
        if males and md < fd and md < (max(d[2], d[3]) * 2.2) ** 2:
            continue
        if any(_iou_box(d, m) > 0.18 for m in males) and (not females or all(_iou_box(d, f) < 0.12 for f in females)):
            continue
        kept.append(d)
    return kept


def _boost(rgba):
    h, w = rgba.shape[:2]
    m = max(h, w)
    if m >= 260 or m <= 0:
        return rgba, 1.0
    s = 320.0 / m
    return np.ascontiguousarray(cv2.resize(rgba, (max(8, int(w * s)), max(8, int(h * s))), interpolation=cv2.INTER_CUBIC)), s


def _prep(crops, origins):
    out_c, out_o, scales = [], [], []
    for crop, origin in zip(crops, origins):
        if crop.size == 0:
            continue
        boosted, scale = _boost(crop)
        out_c.append(boosted)
        out_o.append(origin)
        scales.append(scale)
    return out_c, out_o, scales


def _skin_boxes(bgr, limit):
    if limit <= 0:
        return []
    small = cv2.resize(bgr, (0, 0), fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    mask = cv2.medianBlur(cv2.inRange(cv2.cvtColor(small, cv2.COLOR_BGR2YCrCb), (0, 133, 77), (255, 173, 127)), 5)
    boxes = []
    fh, fw = bgr.shape[:2]
    for cnt in cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0]:
        x, y, w, h = cv2.boundingRect(cnt)
        if not (8 < w * h < 140 * 140):
            continue
        x, y, w, h = x * 2, y * 2, w * 2, h * 2
        x1, y1 = max(0, x - 10), max(0, y - 10)
        x2, y2 = min(fw, x + w + 10), min(fh, y + h + 10)
        boxes.append((x1, y1, x2 - x1, y2 - y1, w * h))
    boxes.sort(key=lambda b: b[4], reverse=True)
    return [(x, y, w, h) for x, y, w, h, _ in boxes[:limit]]


def _rect_iou(a, b) -> float:
    return _iou_box(a, b)
