"""Validate that text in the application is actually legible.

Two labels have shipped rendering dark text on the dark shell -- invisible, and
both found by a person looking at a screenshot. A stylesheet cascade is exactly
the kind of thing eyes are bad at auditing: a rule added for one page silently
changes another, and nothing fails.

This does not read the stylesheet. Reading it would mean reimplementing Qt's
cascade and would be wrong in the same places Qt is surprising. Instead it grabs
each widget as the compositor actually draws it and measures the rendered
pixels. If a label's text is the same colour as what is behind it, the grab is a
near-uniform image and the contrast ratio collapses -- whatever combination of
rules produced it.

The threshold is WCAG AA, 4.5:1 for body text. Antialiasing softens glyph edges,
so the measurement takes the extremes of the rendered image, which approach the
true foreground and background.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from PySide6.QtWidgets import QLabel, QPushButton  # noqa: E402

from ui import MainWindow, create_app  # noqa: E402
from ui.app import DEV_UNLOCK_ENV_VAR  # noqa: E402

MINIMUM_RATIO = 4.5
"""WCAG AA for body text."""

LARGE_TEXT_RATIO = 3.0
"""WCAG AA for large or bold text -- headings and primary buttons."""

LARGE_TEXT_OBJECTS = {
    "heading",
    "licensePageTitle",
    "licensePageSubtitle",
    "sidebarBranding",
    "filingRecordGroupLabel",
    "matterAiHeading",
    "dailyReminderHeading",
    "dailyReminderSettingsHeading",
}


def _relative_luminance(red: int, green: int, blue: int) -> float:
    """Per WCAG 2.1, the sRGB relative luminance of a colour."""

    def channel(value: int) -> float:
        srgb = value / 255.0
        return srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def _contrast(first: float, second: float) -> float:
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def rendered_contrast(window_image, widget, window) -> float | None:
    """Contrast between the lightest and darkest pixels where the widget sits.

    Sampled out of an image of the whole window rather than from
    ``widget.grab()``. Grabbing a child renders it in isolation, without the
    surface behind it, so a label with a transparent background comes back as a
    uniform rectangle -- which is precisely the case this test exists to catch,
    and it would report every label as broken. Compositing is the whole point.

    ``None`` when the widget is clipped out of view or too small to sample,
    which is not a failure -- there is just nothing drawn to assert on.
    """
    top_left = widget.mapTo(window, widget.rect().topLeft())
    left, top = top_left.x(), top_left.y()
    right = min(left + widget.width(), window_image.width())
    bottom = min(top + widget.height(), window_image.height())
    if left < 0 or top < 0 or right - left < 4 or bottom - top < 4:
        return None

    luminances: list[float] = []
    for y in range(top, bottom):
        for x in range(left, right):
            colour = window_image.pixelColor(x, y)
            luminances.append(_relative_luminance(colour.red(), colour.green(), colour.blue()))
    if len(luminances) < 16:
        return None
    return _contrast(max(luminances), min(luminances))


def main() -> None:
    os.environ[DEV_UNLOCK_ENV_VAR] = "1"
    failures: list[str] = []
    checked = 0
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            os.environ["APPDATA"] = str(root / "appdata")
            app = create_app(["validate_contrast"])
            window = MainWindow(workspace=root / "workspace")
            window.resize(1280, 860)
            window.show()
            app.processEvents()

            # Every destination has to be visited: a widget on a page that was
            # never shown grabs as empty, and would pass without being drawn.
            for index in range(window.tabs.count()):
                window.tabs.setCurrentIndex(index)
                app.processEvents()
                window_image = window.grab().toImage()

                for widget in window.tabs.widget(index).findChildren(QLabel):
                    if not widget.text().strip() or not widget.isVisible():
                        continue
                    ratio = rendered_contrast(window_image, widget, window)
                    if ratio is None:
                        continue
                    checked += 1
                    required = (
                        LARGE_TEXT_RATIO
                        if widget.objectName() in LARGE_TEXT_OBJECTS
                        else MINIMUM_RATIO
                    )
                    if ratio < required:
                        failures.append(
                            f"{widget.objectName() or type(widget).__name__} on "
                            f"'{window.tabs.tabText(index)}': {ratio:.2f}:1 "
                            f"(needs {required}:1) -- text: {widget.text()[:48]!r}"
                        )

                for button in window.tabs.widget(index).findChildren(QPushButton):
                    if not button.text().strip() or not button.isVisible():
                        continue
                    # A disabled control is deliberately low contrast: that is
                    # how it reads as unavailable.
                    if not button.isEnabled():
                        continue
                    ratio = rendered_contrast(window_image, button, window)
                    if ratio is None:
                        continue
                    checked += 1
                    if ratio < LARGE_TEXT_RATIO:
                        failures.append(
                            f"{button.objectName() or 'QPushButton'} on "
                            f"'{window.tabs.tabText(index)}': {ratio:.2f}:1 "
                            f"(needs {LARGE_TEXT_RATIO}:1) -- text: {button.text()[:48]!r}"
                        )

            window.close()
            app.processEvents()
    finally:
        os.environ.pop(DEV_UNLOCK_ENV_VAR, None)

    assert checked > 40, f"only {checked} controls were measured; the sweep is not reaching the UI"
    if failures:
        raise AssertionError(
            "text is not legible against what is behind it:\n  " + "\n  ".join(sorted(failures))
        )
    print(f"CONTRAST VALIDATION PASS: {checked} controls measured, all >= WCAG AA")


if __name__ == "__main__":
    main()
