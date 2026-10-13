from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter, Qt
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from src.config import PART_LABELS, STYLES, Settings, load_settings, save_settings
from src.engine import CensorEngine, CensorOverlay, ScreenGrabber

WM_HOTKEY, VK_F8, MOD_NOREPEAT, HOTKEY_ID = 0x0312, 0x77, 0x4000, 1
CSS = """
QWidget{background:#0c0c10;color:#f3eef2;font-family:"Segoe UI";font-size:13px}
#kicker{color:#ff7aa8;letter-spacing:2px;font-size:11px;font-weight:700}
#title{font-size:28px;font-weight:800}
#subtitle,#hint{color:#b9a8b3} #status{color:#ffd0e0;padding:8px 0}
#card{background:#16161d;border:1px solid #2a2430;border-radius:12px;padding:8px}
#cardTitle{font-weight:700;padding-bottom:4px}
QPushButton#start,QPushButton#stop{border:none;border-radius:10px;padding:12px;font-size:15px;font-weight:700}
QPushButton#start{background:#ff4d8d;color:#14040a} QPushButton#start:hover{background:#ff73a6}
QPushButton#stop{background:#3a111c;color:#ffd0e0}
QPushButton#chip{background:#211820;border:1px solid #3a2d38;border-radius:8px;padding:7px 10px}
QPushButton#chip:checked{background:#ff4d8d;color:#14040a;border:none;font-weight:700}
QComboBox,QSlider{background:#211820} QCheckBox::indicator{width:16px;height:16px}
"""


class HotkeyFilter(QAbstractNativeEventFilter):
    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def nativeEventFilter(self, eventType, message):
        kind = bytes(eventType).decode("utf-8", errors="ignore") if not isinstance(eventType, str) else eventType
        if kind in {"windows_generic_MSG", "windows_dispatcher_MSG"}:
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == WM_HOTKEY and int(msg.wParam) == HOTKEY_ID:
                    self._callback()
            except Exception:
                pass
        return False, 0


class ControlPanel(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings, self.engine, self.overlays = settings, CensorEngine(), {}
        self._blocking, self._hotkey_filter, self._quiet = False, None, False
        self.setWindowTitle("Beta Censor")
        self.setFixedWidth(440)
        self.setStyleSheet(CSS)
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)
        for name, text in (("kicker", "OUTIL LOCAL · 18+"), ("title", "Beta Censor")):
            lab = QLabel(text)
            lab.setObjectName(name)
            root.addWidget(lab)
        sub = QLabel("Capture live. Niveau haut = plus de zones. Toutes on/off d’un clic.")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)
        self.start_btn = QPushButton("Démarrer Beta Censor")
        self.start_btn.setObjectName("start")
        self.start_btn.clicked.connect(self.toggle)
        root.addWidget(self.start_btn)
        self.status = QLabel("En pause · F8 pour démarrer / arrêter")
        self.status.setObjectName("status")
        root.addWidget(self.status)
        root.addWidget(self._card_parts())
        root.addWidget(self._card_look())
        hint = QLabel("Rien n’est envoyé. F8 stop. BNWO : logo Blacked blanc + QoS ancrés dans la peau.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        self.engine.overlays_ready.connect(self._on_regions)
        self.engine.status.connect(lambda t: self._blocking and self.status.setText(t))
        self.engine.failed.connect(self._on_fail)

    def _card(self, title: str) -> tuple[QFrame, QVBoxLayout]:
        card, lay, lab = QFrame(), QVBoxLayout(), QLabel(title)
        card.setObjectName("card")
        lab.setObjectName("cardTitle")
        lay.setContentsMargins(8, 8, 8, 8)
        card.setLayout(lay)
        lay.addWidget(lab)
        return card, lay

    def _chips(self, items, current, on_click) -> tuple[QButtonGroup, dict]:
        group, btns, row = QButtonGroup(self), {}, QHBoxLayout()
        for key, name in items:
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("chip")
            btn.setChecked(current == key)
            group.addButton(btn)
            btns[key] = btn
            btn.clicked.connect(on_click)
            row.addWidget(btn)
        return group, btns, row

    def _card_parts(self) -> QFrame:
        card, layout = self._card("Parties à censurer")
        self.all_box = QCheckBox("Toutes les parties")
        self.all_box.setChecked(self.settings.parts_on and all(self.settings.parts.values()))
        self.all_box.toggled.connect(self._toggle_all)
        layout.addWidget(self.all_box)
        row = QHBoxLayout()
        row.addWidget(QLabel("Niveau"))
        self.level_group, self.level_btns, chips = self._chips(((n, str(n)) for n in range(1, 5)), self.settings.level, self._on_level)
        row.addLayout(chips)
        layout.addLayout(row)
        layout.addWidget(QLabel("1 entrejambe · 2 +seins · 3 +fesses · 4 tout"))
        grid, col_a, col_b = QHBoxLayout(), QVBoxLayout(), QVBoxLayout()
        self.part_boxes = {}
        for i, key in enumerate(PART_LABELS):
            box = QCheckBox(PART_LABELS[key])
            box.setChecked(self.settings.parts.get(key, False))
            box.toggled.connect(self._sync_settings)
            self.part_boxes[key] = box
            (col_a if i < 3 else col_b).addWidget(box)
        grid.addLayout(col_a)
        grid.addLayout(col_b)
        layout.addLayout(grid)
        return card

    def _card_look(self) -> QFrame:
        card, layout = self._card("Rendu")
        row = QHBoxLayout()
        row.addWidget(QLabel("Style"))
        self.style_box = QComboBox()
        self.style_box.addItems(["Flou", "Pixel", "Barre", "Noir", "Aucun"])
        self.style_box.setCurrentIndex(STYLES.index(self.settings.style) if self.settings.style in STYLES else 0)
        self.style_box.currentIndexChanged.connect(self._sync_settings)
        row.addWidget(self.style_box, 1)
        layout.addLayout(row)
        prow = QHBoxLayout()
        prow.addWidget(QLabel("Perf"))
        self.preset_group, self.preset_btns, chips = self._chips((("low", "Low"), ("medium", "Med"), ("high", "High")), self.settings.preset, self._sync_settings)
        prow.addLayout(chips)
        layout.addLayout(prow)
        crow = QHBoxLayout()
        crow.addWidget(QLabel("Agressivité"))
        self.conf_slider = QSlider(Qt.Orientation.Horizontal)
        self.conf_slider.setRange(10, 100)
        self.conf_slider.setValue(int(self.settings.aggressiveness))
        self.conf_slider.valueChanged.connect(self._sync_settings)
        self.conf_value = QLabel(f"{self.settings.aggressiveness}%")
        crow.addWidget(self.conf_slider, 1)
        crow.addWidget(self.conf_value)
        layout.addLayout(crow)
        self.bnwo_box = QCheckBox("BNWO / Blacked extrême (tatouages QoS)")
        self.bnwo_box.setChecked(self.settings.bnwo)
        self.bnwo_box.toggled.connect(self._sync_settings)
        layout.addWidget(self.bnwo_box)
        return card

    def showEvent(self, event) -> None:
        super().showEvent(event)
        ctypes.windll.user32.RegisterHotKey(int(self.winId()), HOTKEY_ID, MOD_NOREPEAT, VK_F8)
        if self._hotkey_filter is None:
            self._hotkey_filter = HotkeyFilter(self.toggle)
            QApplication.instance().installNativeEventFilter(self._hotkey_filter)

    def _on_level(self) -> None:
        for n, btn in self.level_btns.items():
            if btn.isChecked():
                self.settings.apply_level(n)
        self._quiet = True
        for key, box in self.part_boxes.items():
            box.setChecked(self.settings.parts[key])
        self.all_box.setChecked(all(self.settings.parts.values()))
        self._quiet = False
        self._sync_settings()

    def _toggle_all(self, on: bool) -> None:
        if self._quiet:
            return
        self.settings.parts_on = on
        if on:
            self.settings.apply_level(4)
            self._quiet = True
            self.level_btns[4].setChecked(True)
            for key, box in self.part_boxes.items():
                box.setChecked(True)
            self._quiet = False
        else:
            for box in self.part_boxes.values():
                box.setChecked(False)
        self._sync_settings()

    def _sync_settings(self) -> None:
        if self._quiet:
            return
        for key, box in self.part_boxes.items():
            self.settings.parts[key] = box.isChecked()
        self.settings.parts_on = any(self.settings.parts.values())
        self.settings.style = STYLES[self.style_box.currentIndex()]
        for key, btn in self.preset_btns.items():
            if btn.isChecked():
                self.settings.preset = key
        for n, btn in self.level_btns.items():
            if btn.isChecked():
                self.settings.level = n
        self.settings.aggressiveness = int(self.conf_slider.value())
        self.settings.bnwo = self.bnwo_box.isChecked()
        self.conf_value.setText(f"{self.settings.aggressiveness}%")
        self._quiet = True
        self.all_box.setChecked(self.settings.parts_on and all(self.settings.parts.values()))
        self._quiet = False
        save_settings(self.settings)
        self.engine.set_settings(self.settings)
        for overlay in self.overlays.values():
            overlay.set_style(self.settings.style)

    def toggle(self) -> None:
        self.stop_blocking() if self._blocking else self.start_blocking()

    def start_blocking(self) -> None:
        if self._blocking:
            return
        self._sync_settings()
        if self.engine.isRunning():
            self.engine.stop()
            self.engine.wait(2000)
        self.engine = CensorEngine()
        self.engine.overlays_ready.connect(self._on_regions)
        self.engine.status.connect(lambda t: self._blocking and self.status.setText(t))
        self.engine.failed.connect(self._on_fail)
        self._ensure_overlays()
        for overlay in self.overlays.values():
            overlay.set_style(self.settings.style)
            overlay.show()
        self.engine.set_settings(self.settings)
        self.engine.start()
        self._blocking = True
        self.start_btn.setText("Arrêter Beta Censor")
        self.start_btn.setObjectName("stop")
        self.start_btn.setStyle(self.start_btn.style())
        self.status.setText("Censure en cours…")

    def stop_blocking(self) -> None:
        self._blocking = False
        self.engine.stop()
        if self.engine.isRunning():
            self.engine.wait(1500)
        for overlay in self.overlays.values():
            overlay.clear()
            overlay.hide()
        self.start_btn.setText("Démarrer Beta Censor")
        self.start_btn.setObjectName("start")
        self.start_btn.setStyle(self.start_btn.style())
        self.status.setText("En pause · F8 pour démarrer / arrêter")

    def _ensure_overlays(self) -> None:
        screens, grabber = list(QApplication.screens()), ScreenGrabber()
        monitors = grabber.monitors()
        grabber.close()
        for overlay in self.overlays.values():
            overlay.close()
        self.overlays.clear()
        used = set()
        for monitor in monitors:
            screen = _best_screen(screens, monitor, used)
            if screen is not None:
                used.add(id(screen))
                g = screen.geometry()
                self.overlays[monitor.index] = CensorOverlay(g.x(), g.y(), g.width(), g.height())
            else:
                self.overlays[monitor.index] = CensorOverlay(monitor.left, monitor.top, monitor.width, monitor.height)

    def _on_regions(self, payload: dict) -> None:
        for index, overlay in self.overlays.items():
            overlay.set_regions(payload.get(index, []))

    def _on_fail(self, text: str) -> None:
        self.stop_blocking()
        QMessageBox.critical(self, "Beta Censor", text)

    def closeEvent(self, event: QCloseEvent) -> None:
        try:
            ctypes.windll.user32.UnregisterHotKey(int(self.winId()), HOTKEY_ID)
        except Exception:
            pass
        self.stop_blocking()
        for overlay in self.overlays.values():
            overlay.close()
        event.accept()


def _best_screen(screens, monitor, used):
    mx, my, best, best_dist = monitor.left + monitor.width / 2, monitor.top + monitor.height / 2, None, None
    for screen in screens:
        if id(screen) in used:
            continue
        dpr, geo = float(screen.devicePixelRatio() or 1.0), screen.geometry()
        dist = ((geo.x() + geo.width() / 2) * dpr - mx) ** 2 + ((geo.y() + geo.height() / 2) * dpr - my) ** 2
        if best_dist is None or dist < best_dist:
            best, best_dist = screen, dist
    return best


def _dpi_aware() -> None:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def main() -> int:
    _dpi_aware()
    app = QApplication(sys.argv)
    app.setApplicationName("Beta Censor")
    settings = load_settings()
    if not settings.accepted_18:
        reply = QMessageBox.question(
            None, "Beta Censor · 18+",
            "Cette application est destinée aux adultes (18+).\nConfirmes-tu avoir 18 ans ou plus ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return 0
        settings.accepted_18 = True
        save_settings(settings)
    panel = ControlPanel(settings)
    panel.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
