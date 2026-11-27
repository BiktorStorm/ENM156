import json
import subprocess
import sys
from pathlib import Path

# Colours, fonts and saved settings for the GUI (GUI.py, powerChart.py). #
#
# There is a light and a dark palette with the same keys. The appearance
# setting is "light", "dark" or "system" (follow the operating system) and is
# remembered between runs in a small JSON file in the home folder.

if sys.platform == "darwin":
    FAMILY = "Helvetica Neue"
elif sys.platform.startswith("win"):
    FAMILY = "Segoe UI"
else:
    FAMILY = "DejaVu Sans"


def font(size: int, weight: str | None = None) -> tuple:
    return (FAMILY, size, weight) if weight else (FAMILY, size)


# Machine colours, bright enough for both palettes
PROCESS_COLORS = ["#6366f1", "#f59e0b", "#10b981", "#ec4899",
                  "#06b6d4", "#8b5cf6", "#84cc16", "#f97316"]

LIGHT = {
    "bg": "#f0f3f8",            # window
    "card": "#ffffff",
    "cardAlt": "#f6f8fb",       # table headings, every other row
    "border": "#e1e6ee",
    "text": "#172033",
    "muted": "#66708a",
    "input": "#f1f3f8",         # input fields, filled instead of outlined
    "select": "#e4e2fd",        # selected table row
    "control": "#e8ebf2",       # secondary buttons, empty check boxes
    "controlHover": "#dddff9",
    "accent": "#5850ec",
    "accentHover": "#4a42d6",
    "accentSoft": "#ebeafd",
    "onAccent": "#ffffff",
    "header": "#3730a3",        # top bar
    "headerText": "#ffffff",
    "headerMuted": "#c7c9f5",
    "headerButton": "#4840b8",
    "headerButtonHover": "#5a52cc",
    "success": "#16a34a",
    "successHover": "#15803d",
    "successSoft": "#e7f6ec",
    "danger": "#e5484d",
    "dangerSoft": "#fdecec",
    "warning": "#f59e0b",
    # chart
    "area": "#c9d3e3",
    "closed": "#eef1f6",
    "blocked": "#e6eaf1",
    "grid": "#edf0f5",
    "overCap": "#fde8e8",
    "tooltipBg": "#172033",
    "tooltipFg": "#ffffff",
    "ghostBase": "#000000",     # ghost outlines are the machine colour blended towards this
}

DARK = {
    "bg": "#0d1117",
    "card": "#161b26",
    "cardAlt": "#1b2130",
    "border": "#273042",
    "text": "#e6e9f2",
    "muted": "#98a2b8",
    "input": "#1f2636",
    "select": "#2d2a5e",
    "control": "#252d3e",
    "controlHover": "#2f2d5c",
    "accent": "#7c74ff",
    "accentHover": "#8f88ff",
    "accentSoft": "#24224a",
    "onAccent": "#ffffff",
    "header": "#1e1b4b",
    "headerText": "#ffffff",
    "headerMuted": "#a5a8e6",
    "headerButton": "#2e2a6b",
    "headerButtonHover": "#3b3684",
    "success": "#34c46e",
    "successHover": "#2aa85c",
    "successSoft": "#132b1d",
    "danger": "#ff5c62",
    "dangerSoft": "#341719",
    "warning": "#fbbf24",
    "area": "#3b475c",
    "closed": "#0a0d14",
    "blocked": "#192030",
    "grid": "#222a3a",
    "overCap": "#3a1c22",
    "tooltipBg": "#e6e9f2",
    "tooltipFg": "#0d1117",
    "ghostBase": "#ffffff",
}

THEMES = {"light": LIGHT, "dark": DARK}
APPEARANCES = [("light", "Light"), ("dark", "Dark"), ("system", "Match system")]


def systemPrefersDark() -> bool:
    """True if the operating system is set to dark mode (macOS, Windows)."""
    try:
        if sys.platform == "darwin":
            result = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"],
                                    capture_output=True, text=True, timeout=2)
            return result.stdout.strip().lower() == "dark"
        if sys.platform.startswith("win"):
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                 r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except Exception:
        pass
    return False


def resolve(appearance: str) -> str:
    """'light' or 'dark' for an appearance setting."""
    if appearance == "system":
        return "dark" if systemPrefersDark() else "light"
    return appearance if appearance in THEMES else "light"


def palette(appearance: str) -> dict:
    return THEMES[resolve(appearance)]


# ---------------------------- Settings ------------------------------ #

SETTINGS_PATH = Path.home() / ".schedule_optimizer.json"
DEFAULT_SETTINGS = {"appearance": "system"}


def loadSettings(path: Path | None = None) -> dict:
    """Saved settings merged over the defaults. A missing or broken file
    gives the defaults."""
    settings = dict(DEFAULT_SETTINGS)
    try:
        saved = json.loads(Path(path or SETTINGS_PATH).read_text(encoding="utf-8"))
        if isinstance(saved, dict):
            settings.update({k: v for k, v in saved.items() if k in DEFAULT_SETTINGS})
    except (OSError, ValueError):
        pass
    if settings["appearance"] not in dict(APPEARANCES):
        settings["appearance"] = DEFAULT_SETTINGS["appearance"]
    return settings


def saveSettings(settings: dict, path: Path | None = None):
    """Best effort: settings are a convenience, not worth an error."""
    try:
        Path(path or SETTINGS_PATH).write_text(json.dumps(settings, indent=2),
                                               encoding="utf-8")
    except OSError:
        pass
