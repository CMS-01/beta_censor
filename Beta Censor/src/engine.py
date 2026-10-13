from __future__ import annotations

import ctypes
import threading
import time
from copy import deepcopy
from dataclasses import dataclass, field

import cv2
import mss
import numpy as np
from PyQt6.QtCore import QRect, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import QWidget

from src.config import Settings
from src.detect import BodyDetector
from src.render import pad_box, render_region

WDA_EXCLUDEFROMCAPTURE = 0x00000011
FAMILIES = {
    "seins": {"FEMALE_BREAST_EXPOSED", "FEMALE_BREAST_COVERED"},
    "entrejambe": {"FEMALE_GENITALIA_EXPOSED", "FEMALE_GENITALIA_COVERED", "ANUS_EXPOSED", "ANUS_COVERED"},
    "fesses": {"BUTTOCKS_EXPOSED", "BUTTOCKS_COVERED"},
    "ventre": {"BELLY_EXPOSED", "BELLY_COVERED"},
    "aisselles": {"ARMPITS_EXPOSED", "ARMPITS_COVERED"},
    "pieds": {"FEET_EXPOSED", "FEET_COVERED"},
}
_FAM = {lab: fam for fam, labs in FAMILIES.items() for lab in labs}


@dataclass
class Monitor:
    index: int
    left: int
    top: int
    width: int
    height: int


@dataclass
class OverlayRegion:
    x: int
    y: int
    w: int
    h: int
    pixmap: QPixmap | None = field(default=None)


@dataclass
class TrackedBox:
    x: float
    y: float
    w: float
    h: float
    label: str
    score: float
    ttl: int
    vx: float = 0.0
    vy: float = 0.0
    miss: int = 0


def numpy_to_pixmap(frame_bgr: np.ndarray) -> QPixmap:
    rgb = frame_bgr[:, :, ::-1].copy()
    h, w, ch = rgb.shape
    return QPixmap.fromImage(QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy())


def _iou(a: TrackedBox, x, y, w, h) -> float:
    ix1, iy1 = max(a.x, x), max(a.y, y)
    ix2, iy2 = min(a.x + a.w, x + w), min(a.y + a.h, y + h)
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = a.w * a.h + w * h - inter
    return inter / union if union > 0 else 0.0


class ScreenGrabber:
    def __init__(self) -> None:
        self._sct, self._dx, self._cams = mss.mss(), None, {}
        try:
            import dxcam
            self._dx = dxcam
        except Exception:
            pass

    def monitors(self) -> list[Monitor]:
        return [Monitor(i, int(m["left"]), int(m["top"]), int(m["width"]), int(m["height"])) for i, m in enumerate(self._sct.monitors[1:], 1)]

    def grab(self, monitor: Monitor) -> np.ndarray:
        cam = self._camera(monitor)
        if cam is not None:
            for fn in (cam.get_latest_frame, cam.grab):
                try:
                    frame = fn()
                    if frame is not None:
                        return np.asarray(frame)
                except Exception:
                    pass
        frame = np.asarray(self._sct.grab({"left": monitor.left, "top": monitor.top, "width": monitor.width, "height": monitor.height}))
        return frame[:, :, :3] if frame.ndim == 3 and frame.shape[2] == 4 else frame

    def _camera(self, monitor: Monitor):
        if self._dx is None:
            return None
        if monitor.index in self._cams:
            return self._cams[monitor.index]
        try:
            cam = self._dx.create(output_idx=max(0, monitor.index - 1), output_color="BGR")
            try:
                cam.start(target_fps=48, video_mode=True)
            except TypeError:
                cam.start(target_fps=48)
            self._cams[monitor.index] = cam
            return cam
        except Exception:
            self._cams[monitor.index] = None
            return None

    def close(self) -> None:
        for cam in self._cams.values():
            if cam is None:
                continue
            for fn in (cam.stop, cam.release):
                try:
                    fn()
                except Exception:
                    pass
        self._cams.clear()
        self._sct.close()


class CensorOverlay(QWidget):
    def __init__(self, left, top, width, height) -> None:
        super().__init__()
        self._regions, self._dpr, self._style = [], 1.0, "flou"
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool | Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setGeometry(left, top, width, height)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        try:
            ctypes.windll.user32.SetWindowDisplayAffinity(int(self.winId()), WDA_EXCLUDEFROMCAPTURE)
        except Exception:
            pass
        self._dpr = float(self.devicePixelRatioF() or 1.0)

    def set_style(self, style: str) -> None:
        self._style = style

    def set_regions(self, regions) -> None:
        self._regions = regions
        self.update()

    def clear(self) -> None:
        self._regions = []
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        dpr = self._dpr or 1.0
        for r in self._regions:
            rect = QRect(int(r.x / dpr), int(r.y / dpr), max(1, int(r.w / dpr)), max(1, int(r.h / dpr)))
            if r.pixmap is not None:
                painter.drawPixmap(rect, r.pixmap)
            else:
                painter.setPen(QPen(QColor(10, 10, 12, 240), 1))
                painter.setBrush(QBrush(QColor(8, 8, 10, 235)))
                painter.drawRoundedRect(rect, 6, 6)
        painter.end()


class BoxTracker:
    def __init__(self, ttl=22, smooth=0.16) -> None:
        self.ttl, self.smooth, self._tracks = ttl, smooth, []

    def tracks(self):
        return list(self._tracks)

    def flow(self, prev_gray, gray) -> None:
        if prev_gray is None or not self._tracks or prev_gray.shape != gray.shape:
            return
        pts, owners = [], []
        for i, t in enumerate(self._tracks):
            cx, cy, ox, oy = t.x + t.w * 0.5, t.y + t.h * 0.5, max(4.0, t.w * 0.28), max(4.0, t.h * 0.28)
            for p in ((cx, cy), (cx - ox, cy), (cx + ox, cy), (cx, cy - oy), (cx, cy + oy), (cx - ox, cy - oy), (cx + ox, cy - oy), (cx - ox, cy + oy), (cx + ox, cy + oy)):
                pts.append(p)
                owners.append(i)
        if not pts:
            return
        p0 = np.array(pts, dtype=np.float32).reshape(-1, 1, 2)
        p1, status, _ = cv2.calcOpticalFlowPyrLK(prev_gray, gray, p0, None, winSize=(31, 31), maxLevel=4, criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03))
        if p1 is None or status is None:
            for t in self._tracks:
                t.x = float(np.clip(t.x + t.vx, 0, max(0, gray.shape[1] - 1)))
                t.y = float(np.clip(t.y + t.vy, 0, max(0, gray.shape[0] - 1)))
                t.vx *= 0.88
                t.vy *= 0.88
            return
        buckets: dict[int, list] = {}
        for i, st in enumerate(status.reshape(-1)):
            if int(st) != 1:
                continue
            dx, dy = float(p1[i, 0, 0] - p0[i, 0, 0]), float(p1[i, 0, 1] - p0[i, 0, 1])
            if abs(dx) <= 160 and abs(dy) <= 160:
                buckets.setdefault(owners[i], []).append((dx, dy))
        gh, gw = gray.shape[:2]
        for i, t in enumerate(self._tracks):
            deltas = buckets.get(i)
            if deltas:
                t.vx, t.vy = float(np.median([d[0] for d in deltas])), float(np.median([d[1] for d in deltas]))
            else:
                t.vx *= 0.88
                t.vy *= 0.88
            t.x = float(np.clip(t.x + t.vx, 0, max(0, gw - 1)))
            t.y = float(np.clip(t.y + t.vy, 0, max(0, gh - 1)))
            t.w, t.h = float(min(t.w, gw - t.x)), float(min(t.h, gh - t.y))

    def update(self, detections):
        unmatched = list(detections)
        for t in self._tracks:
            best_i, best = -1, 0.10
            tcx, tcy = t.x + t.w * 0.5 + t.vx, t.y + t.h * 0.5 + t.vy
            for i, (x, y, w, h, label, _) in enumerate(unmatched):
                if not (t.label == label or (_FAM.get(t.label) == _FAM.get(label) and t.label in _FAM)):
                    continue
                dist = ((x + w * 0.5 - tcx) ** 2 + (y + h * 0.5 - tcy) ** 2) ** 0.5
                score = _iou(t, x, y, w, h) * 0.55 + max(0.0, 1.0 - dist / max(18.0, (t.w + t.h + w + h) * 0.32)) * 0.45
                if score > best:
                    best, best_i = score, i
            if best_i >= 0:
                x, y, w, h, label, score = unmatched.pop(best_i)
                a = self.smooth
                t.x, t.y, t.w, t.h = t.x * a + x * (1 - a), t.y * a + y * (1 - a), t.w * a + w * (1 - a), t.h * a + h * (1 - a)
                t.label, t.score, t.ttl, t.miss = label, score, self.ttl, 0
            else:
                t.miss += 1
                t.ttl -= 1
                t.vx *= 0.9
                t.vy *= 0.9
        self._tracks = [t for t in self._tracks if t.ttl > 0]
        for x, y, w, h, label, score in unmatched:
            self._tracks.append(TrackedBox(x, y, w, h, label, score, self.ttl))
        return list(self._tracks)


class CensorEngine(QThread):
    overlays_ready = pyqtSignal(dict)
    status = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._running, self._settings, self._detector = False, Settings(), BodyDetector()
        self._lock, self._frames, self._dets, self._dets_gen, self._seen_gen = threading.Lock(), {}, {}, 0, -1

    def set_settings(self, settings: Settings) -> None:
        self._settings = deepcopy(settings)

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        self._running = True
        self.status.emit("Chargement du modèle…")
        try:
            self._detector.load()
        except Exception as exc:
            self.failed.emit(f"Impossible de charger le modèle : {exc}")
            return
        grabber, trackers, prev_gray = ScreenGrabber(), {}, {}
        gpu = "GPU" if "CPU" not in self._detector.provider else "CPU"
        self.status.emit(f"Censure live · {gpu} · le flou suit le mouvement")
        detect_thread = threading.Thread(target=self._detect_loop, daemon=True)
        detect_thread.start()
        try:
            while self._running:
                started, settings, enabled, payload = time.perf_counter(), self._settings, self._settings.enabled_classes(), {}
                if not enabled:
                    self.overlays_ready.emit(payload)
                    self.msleep(40)
                    continue
                dets_map = None
                if self._seen_gen != self._dets_gen:
                    with self._lock:
                        dets_map = {k: list(v) for k, v in self._dets.items()}
                        self._seen_gen = self._dets_gen
                for monitor in grabber.monitors():
                    if not self._running:
                        break
                    frame = grabber.grab(monitor)
                    if frame is None or frame.size == 0:
                        continue
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    tracker = trackers.setdefault(monitor.index, BoxTracker())
                    tracker.flow(prev_gray.get(monitor.index), gray)
                    prev_gray[monitor.index] = gray
                    with self._lock:
                        self._frames[monitor.index] = frame
                    if dets_map is not None:
                        tracker.update(dets_map.get(monitor.index, []))
                    mh, mw = frame.shape[:2]
                    regions = []
                    for box in tracker.tracks():
                        extra = 0.12 if "BREAST" in box.label or "GENITALIA" in box.label else 0.0
                        pad = settings.padding + extra
                        ix, iy, iw, ih = pad_box(box.x, box.y, box.w, box.h, pad, mw, mh)
                        x, y, w, h = pad_box(box.x, box.y, box.w, box.h, pad + (0.62 if settings.bnwo else 0), mw, mh)
                        crop, pixmap = frame[y : y + h, x : x + w], None
                        if crop.size:
                            pixmap = numpy_to_pixmap(render_region(crop, settings.style, settings.bnwo, box.label, (ix - x, iy - y, iw, ih)))
                        regions.append(OverlayRegion(x, y, w, h, pixmap))
                    payload[monitor.index] = regions
                self.overlays_ready.emit(payload)
                self.msleep(max(1, int(settings.overlay_ms() - (time.perf_counter() - started) * 1000)))
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            self._running = False
            detect_thread.join(timeout=2.0)
            grabber.close()
            self.status.emit("Arrêté")

    def _detect_loop(self) -> None:
        while self._running:
            settings, enabled = self._settings, self._settings.enabled_classes()
            if not enabled:
                time.sleep(0.05)
                continue
            with self._lock:
                frames = {idx: frm.copy() for idx, frm in self._frames.items()}
            if not frames:
                time.sleep(0.01)
                continue
            try:
                new_dets = {idx: self._detector.detect(frame, enabled, settings.confidence(), settings.grid(), settings.tiny(), settings.max_refine(), settings.max_skin()) for idx, frame in frames.items()}
            except Exception:
                time.sleep(0.05)
                continue
            with self._lock:
                self._dets = new_dets
                self._dets_gen += 1
