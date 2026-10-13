from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"

PART_CLASSES = {
    "seins": ("FEMALE_BREAST_EXPOSED", "FEMALE_BREAST_COVERED"),
    "entrejambe": ("FEMALE_GENITALIA_EXPOSED", "FEMALE_GENITALIA_COVERED"),
    "fesses": ("BUTTOCKS_EXPOSED", "BUTTOCKS_COVERED", "ANUS_EXPOSED", "ANUS_COVERED"),
    "ventre": ("BELLY_EXPOSED", "BELLY_COVERED"),
    "aisselles": ("ARMPITS_EXPOSED", "ARMPITS_COVERED"),
    "pieds": ("FEET_EXPOSED", "FEET_COVERED"),
}
PART_LABELS = {
    "seins": "Seins",
    "entrejambe": "Entrejambe",
    "fesses": "Fesses",
    "ventre": "Ventre",
    "aisselles": "Aisselles",
    "pieds": "Pieds",
}
LEVELS = {
    1: ("entrejambe",),
    2: ("entrejambe", "seins"),
    3: ("entrejambe", "seins", "fesses"),
    4: ("entrejambe", "seins", "fesses", "ventre", "aisselles", "pieds"),
}
STYLES = ("flou", "pixel", "barre", "noir", "aucun")
PRESETS = {
    "low": {"grid": (2, 2), "overlay_ms": 33, "tiny": False, "max_refine": 16, "max_skin": 0},
    "medium": {"grid": (3, 2), "overlay_ms": 24, "tiny": True, "max_refine": 24, "max_skin": 12},
    "high": {"grid": (4, 3), "overlay_ms": 16, "tiny": True, "max_refine": 36, "max_skin": 20},
}


def parts_for_level(level: int) -> dict[str, bool]:
    wanted = set(LEVELS.get(max(1, min(4, level)), LEVELS[3]))
    return {key: key in wanted for key in PART_LABELS}


@dataclass
class Settings:
    parts: dict[str, bool] = field(default_factory=lambda: parts_for_level(3))
    parts_on: bool = True
    level: int = 3
    style: str = "flou"
    preset: str = "high"
    aggressiveness: int = 82
    padding: float = 0.34
    bnwo: bool = False
    accepted_18: bool = False

    def apply_level(self, level: int) -> None:
        self.level = max(1, min(4, int(level)))
        self.parts = parts_for_level(self.level)
        self.parts_on = True

    def enabled_classes(self) -> set[str]:
        if not self.parts_on:
            return set()
        names: set[str] = set()
        for key, on in self.parts.items():
            if on:
                names.update(PART_CLASSES.get(key, ()))
        return names

    def _p(self) -> dict:
        return PRESETS.get(self.preset, PRESETS["medium"])

    def grid(self) -> tuple[int, int]:
        return self._p()["grid"]

    def overlay_ms(self) -> int:
        return int(self._p()["overlay_ms"])

    def tiny(self) -> bool:
        return bool(self._p()["tiny"])

    def max_refine(self) -> int:
        return int(self._p()["max_refine"])

    def max_skin(self) -> int:
        return int(self._p()["max_skin"])

    def confidence(self) -> float:
        agg = max(10, min(100, int(self.aggressiveness)))
        return 0.07 + (100 - agg) * 0.0065


def load_settings() -> Settings:
    base = Settings()
    if not CONFIG_PATH.exists():
        return base
    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        parts = dict(base.parts)
        parts.update({k: bool(v) for k, v in raw.get("parts", {}).items() if k in parts})
        style = raw.get("style", base.style)
        preset = raw.get("preset", base.preset)
        return Settings(
            parts=parts,
            parts_on=bool(raw.get("parts_on", True)),
            level=max(1, min(4, int(raw.get("level", 3)))),
            style=style if style in STYLES else base.style,
            preset=preset if preset in PRESETS else base.preset,
            aggressiveness=max(10, min(100, int(raw.get("aggressiveness", 82)))),
            padding=float(raw.get("padding", base.padding)),
            bnwo=bool(raw.get("bnwo", False)),
            accepted_18=bool(raw.get("accepted_18", False)),
        )
    except (OSError, ValueError, TypeError):
        return base


def save_settings(settings: Settings) -> None:
    CONFIG_PATH.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=False), encoding="utf-8")
