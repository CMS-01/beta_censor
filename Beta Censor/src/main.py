from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PyQt6.QtCore import QAbstractNativeEventFilter, Qt, QTimer
from PyQt6.QtGui import QCloseEvent, QFont, QPalette, QColor
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
    QSpacerItem,
    QSizePolicy,
    QScrollArea,
    QGridLayout,
)

from src.config import PART_LABELS, STYLES, Settings, load_settings, save_settings
from src.engine import CensorEngine, CensorOverlay, ScreenGrabber

WM_HOTKEY, VK_F8, MOD_NOREPEAT, HOTKEY_ID = 0x0312, 0x77, 0x4000, 1

CSS = """
QWidget {
    background: #080810;
    color: #e8e0f0;
    font-family: "Segoe UI";
    font-size: 13px;
}
QScrollArea { border: none; background: transparent; }
QScrollBar:vertical {
    background: #0e0e18;
    width: 6px;
    border-radius: 3px;
}
QScrollBar::handle:vertical {
    background: #2a1f3d;
    border-radius: 3px;
    min-height: 30px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

#sidebar {
    background: #0e0e1a;
    border-right: 1px solid #1e1830;
    min-width: 260px;
    max-width: 260px;
}
#content {
    background: #080810;
}

#logo_badge {
    background: #1a0e2e;
    border: 1px solid #3d1f6e;
    border-radius: 6px;
    padding: 4px 10px;
    color: #c084fc;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 2px;
}
#app_title {
    font-size: 22px;
    font-weight: 800;
    color: #f0e8ff;
    letter-spacing: 0.5px;
}
#app_version {
    font-size: 11px;
    color: #5a4870;
}

#nav_btn {
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 10px 16px;
    text-align: left;
    font-size: 13px;
    color: #7a6890;
}
#nav_btn:hover {
    background: #14102a;
    color: #c084fc;
}
#nav_btn[active="true"] {
    background: #1a0e2e;
    color: #c084fc;
    font-weight: 700;
    border-left: 3px solid #9333ea;
}

#status_bar {
    background: #0e0e1a;
    border-top: 1px solid #1e1830;
    padding: 8px 20px;
}
#status_dot_on {
    background: #9333ea;
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}
#status_dot_off {
    background: #2a1f3d;
    border-radius: 5px;
    min-width: 10px;
    max-width: 10px;
    min-height: 10px;
    max-height: 10px;
}
#status_text {
    color: #7a6890;
    font-size: 12px;
}
#status_text_active {
    color: #c084fc;
    font-size: 12px;
}

QPushButton#start_btn {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #7c3aed, stop:1 #9333ea);
    color: #ffffff;
    border: none;
    border-radius: 10px;
    padding: 14px 28px;
    font-size: 15px;
    font-weight: 700;
    letter-spacing: 0.5px;
    min-height: 48px;
}
QPushButton#start_btn:hover {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #8b5cf6, stop:1 #a855f7);
}
QPushButton#stop_btn {
    background: #1a0e2e;
    color: #c084fc;
    border: 2px solid #3d1f6e;
    border-radius: 10px;
    padding: 14px 28px;
    font-size: 15px;
    font-weight: 700;
    min-height: 48px;
}
QPushButton#stop_btn:hover {
    background: #220f3a;
    border-color: #6d28d9;
}

#section_title {
    font-size: 11px;
    font-weight: 700;
    color: #5a4870;
    letter-spacing: 2px;
    padding: 0 0 8px 0;
}
#card {
    background: #0e0e1a;
    border: 1px solid #1e1830;
    border-radius: 12px;
}
#card_title {
    font-size: 14px;
    font-weight: 700;
    color: #e8e0f0;
}
#card_sub {
    font-size: 11px;
    color: #5a4870;
}

QPushButton#chip {
    background: #14102a;
    border: 1px solid #2a1f3d;
    border-radius: 6px;
    padding: 6px 14px;
    color: #7a6890;
    font-size: 12px;
    font-weight: 600;
    min-width: 38px;
}
QPushButton#chip:hover {
    background: #1a0e2e;
    color: #c084fc;
    border-color: #4c1d95;
}
QPushButton#chip:checked {
    background: #4c1d95;
    color: #e8d5ff;
    border: none;
    font-weight: 700;
}

QCheckBox {
    spacing: 10px;
    color: #c0b0d8;
    font-size: 13px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border-radius: 5px;
    border: 1.5px solid #2a1f3d;
    background: #14102a;
}
QCheckBox::indicator:checked {
    background: #7c3aed;
    border: none;
    image: none;
}
QCheckBox::indicator:hover {
    border-color: #7c3aed;
}

QComboBox {
    background: #14102a;
    border: 1px solid #2a1f3d;
    border-radius: 7px;
    padding: 7px 12px;
    color: #e8e0f0;
    min-height: 32px;
    selection-background-color: #4c1d95;
}
QComboBox:hover { border-color: #4c1d95; }
QComboBox::drop-down {
    border: none;
    width: 28px;
}
QComboBox QAbstractItemView {
    background: #14102a;
    border: 1px solid #2a1f3d;
    border-radius: 7px;
    color: #e8e0f0;
    selection-background-color: #4c1d95;
    padding: 4px;
}

QSlider::groove:horizontal {
    background: #1e1830;
    height: 4px;
    border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #7c3aed;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover {
    background: #9333ea;
}
QSlider::sub-page:horizontal {
    background: #7c3aed;
    border-radius: 2px;
}

QLabel#field_label {
    font-size: 12px;
    color: #7a6890;
    font-weight: 600;
}
QLabel#value_label {
    font-size: 12px;
    color: #c084fc;
    font-weight: 700;
    min-width: 42px;
    qproperty-alignment: AlignRight;
}
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


def _make_separator():
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("background: #1e1830; max-height: 1px; border: none;")
    return line


class ControlPanel(QWidget):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings, self.engine, self.overlays = settings, CensorEngine(), {}
        self._blocking, self._hotkey_filter, self._quiet = False, None, False

        self.setWindowTitle("Beta Censor")
        self.setFixedSize(1280, 720)
        self.setStyleSheet(CSS)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        sidebar = self._build_sidebar()
        root.addWidget(sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        content_area = self._build_content()
        right.addWidget(content_area, 1)

        status_bar = self._build_status_bar()
        right.addWidget(status_bar)

        right_widget = QWidget()
        right_widget.setObjectName("content")
        right_widget.setLayout(right)
        root.addWidget(right_widget, 1)

        self.engine.overlays_ready.connect(self._on_regions)
        self.engine.status.connect(lambda t: self._blocking and self._set_status(t, True))
        self.engine.failed.connect(self._on_fail)

    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(20, 28, 20, 20)
        lay.setSpacing(4)

        badge = QLabel("LOCAL TOOL  18+")
        badge.setObjectName("logo_badge")
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(badge)

        lay.addSpacing(16)

        title = QLabel("Beta Censor")
        title.setObjectName("app_title")
        lay.addWidget(title)

        version = QLabel("v2.0")
        version.setObjectName("app_version")
        lay.addWidget(version)

        lay.addSpacing(28)
        lay.addWidget(_make_separator())
        lay.addSpacing(12)

        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("section_title")
        lay.addWidget(nav_label)

        self.main_btn = QPushButton("  \u25CF  Protection")
        self.main_btn.setObjectName("nav_btn")
        self.main_btn.setProperty("active", "true")
        self.main_btn.setCheckable(True)
        self.main_btn.setChecked(True)
        lay.addWidget(self.main_btn)

        self.parts_nav = QPushButton("  \u25CB  Body Parts")
        self.parts_nav.setObjectName("nav_btn")
        self.parts_nav.setCheckable(True)
        lay.addWidget(self.parts_nav)

        self.style_nav = QPushButton("  \u25CB  Style & Render")
        self.style_nav.setObjectName("nav_btn")
        self.style_nav.setCheckable(True)
        lay.addWidget(self.style_nav)

        lay.addStretch()
        lay.addWidget(_make_separator())
        lay.addSpacing(12)

        hint = QLabel("Nothing is sent.\nF8 to start / stop.")
        hint.setStyleSheet("color: #3a2d52; font-size: 11px; line-height: 1.5;")
        hint.setWordWrap(True)
        lay.addWidget(hint)

        return sidebar

    def _build_content(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        inner = QWidget()
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(40, 36, 40, 36)
        lay.setSpacing(28)

        lay.addWidget(self._section_hero())
        lay.addWidget(self._section_parts())
        lay.addWidget(self._section_render())
        lay.addStretch()

        scroll.setWidget(inner)
        return scroll

    def _section_hero(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        title_row = QHBoxLayout()
        h = QLabel("Real-time Screen Filter")
        h.setStyleSheet("font-size: 26px; font-weight: 800; color: #f0e8ff;")
        title_row.addWidget(h)
        title_row.addStretch()
        lay.addLayout(title_row)

        sub = QLabel("Censors content the moment it appears, no matter what app or browser you're watching.")
        sub.setStyleSheet("font-size: 13px; color: #5a4870; line-height: 1.5;")
        sub.setWordWrap(True)
        lay.addWidget(sub)

        self.main_toggle = QPushButton("Start Protection")
        self.main_toggle.setObjectName("start_btn")
        self.main_toggle.setFixedHeight(52)
        self.main_toggle.setFixedWidth(260)
        self.main_toggle.clicked.connect(self.toggle)
        lay.addWidget(self.main_toggle)

        return w

    def _section_parts(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(14)

        title_row = QHBoxLayout()
        titles = QVBoxLayout()
        t = QLabel("Body Parts")
        t.setObjectName("card_title")
        s = QLabel("Select which areas to censor")
        s.setObjectName("card_sub")
        titles.addWidget(t)
        titles.addWidget(s)
        title_row.addLayout(titles)
        title_row.addStretch()
        self.all_box = QCheckBox("All parts")
        self.all_box.setChecked(self.settings.parts_on and all(self.settings.parts.values()))
        self.all_box.toggled.connect(self._toggle_all)
        title_row.addWidget(self.all_box)
        lay.addLayout(title_row)

        lay.addWidget(_make_separator())

        level_row = QHBoxLayout()
        fl = QLabel("Detection level")
        fl.setObjectName("field_label")
        level_row.addWidget(fl)
        level_row.addStretch()
        desc = QLabel("1 groin  2 +chest  3 +buttocks  4 all")
        desc.setStyleSheet("font-size: 11px; color: #3a2d52;")
        level_row.addWidget(desc)
        lay.addLayout(level_row)

        self.level_group, self.level_btns, chips_lay = self._chips(
            ((n, str(n)) for n in range(1, 5)),
            self.settings.level,
            self._on_level
        )
        chips_row = QHBoxLayout()
        chips_row.setSpacing(8)
        chips_row.addLayout(chips_lay)
        chips_row.addStretch()
        lay.addLayout(chips_row)

        lay.addWidget(_make_separator())

        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(10)
        self.part_boxes = {}
        keys = list(PART_LABELS.keys())
        for i, key in enumerate(keys):
            box = QCheckBox(PART_LABELS[key])
            box.setChecked(self.settings.parts.get(key, False))
            box.toggled.connect(self._sync_settings)
            self.part_boxes[key] = box
            grid.addWidget(box, i // 3, i % 3)
        lay.addLayout(grid)

        return card

    def _section_render(self) -> QWidget:
        card = QFrame()
        card.setObjectName("card")
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(16)

        t = QLabel("Style & Performance")
        t.setObjectName("card_title")
        s = QLabel("Configure the visual effect and processing speed")
        s.setObjectName("card_sub")
        lay.addWidget(t)
        lay.addWidget(s)
        lay.addWidget(_make_separator())

        style_row = QHBoxLayout()
        fl = QLabel("Censor style")
        fl.setObjectName("field_label")
        style_row.addWidget(fl)
        style_row.addStretch()
        self.style_box = QComboBox()
        self.style_box.addItems(["Blur", "Pixel", "Bar", "Black", "None"])
        self.style_box.setCurrentIndex(STYLES.index(self.settings.style) if self.settings.style in STYLES else 0)
        self.style_box.currentIndexChanged.connect(self._sync_settings)
        self.style_box.setFixedWidth(160)
        style_row.addWidget(self.style_box)
        lay.addLayout(style_row)

        perf_row = QHBoxLayout()
        fl2 = QLabel("Performance preset")
        fl2.setObjectName("field_label")
        perf_row.addWidget(fl2)
        perf_row.addStretch()
        self.preset_group, self.preset_btns, chips_lay2 = self._chips(
            (("low", "Low"), ("medium", "Med"), ("high", "High")),
            self.settings.preset,
            self._sync_settings
        )
        perf_row.addLayout(chips_lay2)
        lay.addLayout(perf_row)

        agg_row = QHBoxLayout()
        fl3 = QLabel("Aggressiveness")
        fl3.setObjectName("field_label")
        agg_row.addWidget(fl3)
        self.conf_slider = QSlider(Qt.Orientation.Horizontal)
        self.conf_slider.setRange(10, 100)
        self.conf_slider.setValue(int(self.settings.aggressiveness))
        self.conf_slider.valueChanged.connect(self._sync_settings)
        agg_row.addWidget(self.conf_slider, 1)
        self.conf_value = QLabel(f"{self.settings.aggressiveness}%")
        self.conf_value.setObjectName("value_label")
        agg_row.addWidget(self.conf_value)
        lay.addLayout(agg_row)

        lay.addWidget(_make_separator())

        self.bnwo_box = QCheckBox("BNWO / Blacked extreme (QoS tattoos)")
        self.bnwo_box.setChecked(self.settings.bnwo)
        self.bnwo_box.toggled.connect(self._sync_settings)
        lay.addWidget(self.bnwo_box)

        return card

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("status_bar")
        bar.setFixedHeight(46)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(10)

        self.status_dot = QLabel()
        self.status_dot.setObjectName("status_dot_off")
        self.status_dot.setFixedSize(10, 10)
        lay.addWidget(self.status_dot)

        self.status_label = QLabel("Paused  ·  F8 to start / stop")
        self.status_label.setObjectName("status_text")
        lay.addWidget(self.status_label)

        lay.addStretch()

        hotkey_badge = QLabel("F8  TOGGLE")
        hotkey_badge.setStyleSheet(
            "background: #14102a; border: 1px solid #2a1f3d; border-radius: 4px;"
            "padding: 2px 8px; font-size: 10px; color: #5a4870; font-weight: 700; letter-spacing: 1px;"
        )
        lay.addWidget(hotkey_badge)

        return bar

    def _chips(self, items, current, on_click):
        group, btns = QButtonGroup(self), {}
        row = QHBoxLayout()
        row.setSpacing(6)
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

    def _set_status(self, text: str, active: bool = False) -> None:
        self.status_label.setText(text)
        self.status_label.setObjectName("status_text_active" if active else "status_text")
        self.status_label.setStyle(self.status_label.style())
        self.status_dot.setObjectName("status_dot_on" if active else "status_dot_off")
        self.status_dot.setStyle(self.status_dot.style())

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
        self.engine.status.connect(lambda t: self._blocking and self._set_status(t, True))
        self.engine.failed.connect(self._on_fail)
        self._ensure_overlays()
        for overlay in self.overlays.values():
            overlay.set_style(self.settings.style)
            overlay.show()
        self.engine.set_settings(self.settings)
        self.engine.start()
        self._blocking = True
        self.main_toggle.setText("Stop Protection")
        self.main_toggle.setObjectName("stop_btn")
        self.main_toggle.setStyle(self.main_toggle.style())
        self._set_status("Protection active...", True)

    def stop_blocking(self) -> None:
        self._blocking = False
        self.engine.stop()
        if self.engine.isRunning():
            self.engine.wait(1500)
        for overlay in self.overlays.values():
            overlay.clear()
            overlay.hide()
        self.main_toggle.setText("Start Protection")
        self.main_toggle.setObjectName("start_btn")
        self.main_toggle.setStyle(self.main_toggle.style())
        self._set_status("Paused  \u00b7  F8 to start / stop", False)

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
            None, "Beta Censor  18+",
            "This application is intended for adults (18+).\nDo you confirm you are 18 or older?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
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
