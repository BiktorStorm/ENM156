import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:          # without Pillow the GUI keeps square corners
    Image = None

# Rounded corners for the ttk widgets of the GUI. #
#
# Tk cannot round corners itself. Drawing whole widgets as stretched images
# is slow (Tk tiles the image, and on macOS every tile is an expensive draw),
# so instead Tk draws the flat background of a card, button or field as
# usual and only the four corners are tiny images laid on top. Each corner
# is a quarter circle in the widget's colour on the colour behind the widget
# (anti-aliased by drawing 4x larger and scaling down).
#
# Because the colour behind is painted into the corners, a widget on another
# background needs its own style (e.g. Header.TButton on the top bar).
#
# Also here: check and radio box images, the drop-down/spin chevrons and
# the info badge. All images are created once and repainted in place when
# the theme changes. Without Pillow, styles get the same colours with square
# corners.

SUPERSAMPLE = 4
CARD_RADIUS = 10
CONTROL_RADIUS = 6

# Buttons: style -> palette keys (behind, fill, hover fill, text, hover text)
BUTTONS = {
    "TButton": ("card", "control", "controlHover", "text", None),
    "Small.TButton": ("card", "control", "controlHover", "text", None),
    "Proposal.TButton": ("accentSoft", "card", "control", "text", None),
    "Accent.TButton": ("card", "accent", "accentHover", "onAccent", None),
    "Success.TButton": ("accentSoft", "success", "successHover", "onAccent", None),
    "Danger.TButton": ("card", "dangerSoft", "danger", "danger", "onAccent"),
    "Header.TButton": ("header", "headerButton", "headerButtonHover", "headerText", None),
}
# Other rounded surfaces: name -> (radius, behind, fill)
SURFACES = {
    "Card": (CARD_RADIUS, "bg", "card"),
    "Proposal": (CARD_RADIUS, "bg", "accentSoft"),
    "Field": (CONTROL_RADIUS, "card", "input"),
    "HeaderField": (CONTROL_RADIUS, "header", "input"),
}
CORNERS = ("tl", "tr", "bl", "br")


def available() -> bool:
    return Image is not None


# ------------------------------ Images ------------------------------ #

def _canvas(size, background):
    s = SUPERSAMPLE
    img = Image.new("RGB", (size[0] * s, size[1] * s), background)
    return img, ImageDraw.Draw(img)


def _done(img, size):
    return img.resize(size, Image.LANCZOS)


def _corners(radius, behind, fill) -> dict:
    """The four corners (radius x radius) of a rounded shape."""
    size = (2 * radius, 2 * radius)
    img, draw = _canvas(size, behind)
    draw.ellipse([0, 0, size[0] * SUPERSAMPLE - 1, size[1] * SUPERSAMPLE - 1], fill=fill)
    img = _done(img, size)
    r = radius
    return {"tl": img.crop((0, 0, r, r)), "tr": img.crop((r, 0, 2 * r, r)),
            "bl": img.crop((0, r, r, 2 * r)), "br": img.crop((r, r, 2 * r, 2 * r))}


def _check(behind, fill, mark=None):
    """Check box 16x16 plus 7 px of space before the label."""
    size, s = (23, 16), SUPERSAMPLE
    img, draw = _canvas(size, behind)
    draw.rounded_rectangle([0, 0, 16 * s - 1, 16 * s - 1], 4 * s, fill=fill)
    if mark:
        draw.line([(4 * s, 8.2 * s), (6.8 * s, 11 * s), (12 * s, 5 * s)],
                  fill=mark, width=int(2 * s), joint="curve")
    return _done(img, size)


def _radio(behind, fill, dot=None):
    size, s = (23, 16), SUPERSAMPLE
    img, draw = _canvas(size, behind)
    draw.ellipse([0, 0, 16 * s - 1, 16 * s - 1], fill=fill)
    if dot:
        draw.ellipse([5 * s, 5 * s, 11 * s - 1, 11 * s - 1], fill=dot)
    return _done(img, size)


def _chevron(size, behind, color, up=False):
    s = SUPERSAMPLE
    w, h = size
    img, draw = _canvas(size, behind)
    cx, cy, dx, dy = w / 2 - 1, h / 2, 3.5, -2 if up else 2
    draw.line([((cx - dx) * s, (cy - dy) * s), (cx * s, (cy + dy) * s),
               ((cx + dx) * s, (cy - dy) * s)], fill=color, width=int(1.6 * s),
              joint="curve")
    return _done(img, size)


def _info(behind, color, mark):
    """A small filled circle with an 'i'."""
    size, s = (16, 16), SUPERSAMPLE
    img, draw = _canvas(size, behind)
    draw.ellipse([0, 0, 16 * s - 1, 16 * s - 1], fill=color)
    draw.ellipse([7 * s, 3.4 * s, 9 * s, 5.4 * s], fill=mark)
    draw.rounded_rectangle([7.1 * s, 6.6 * s, 8.9 * s, 12.4 * s], 0.9 * s, fill=mark)
    return _done(img, size)


def cornerNodes(prefix: str) -> list:
    """Layout nodes that put the four corner elements of prefix in the
    corners of their parent (top and bottom strips, left and right)."""
    return [
        ("null", {"side": "top", "sticky": "ew", "children": [
            (f"{prefix}.tl", {"side": "left", "sticky": "nw"}),
            (f"{prefix}.tr", {"side": "right", "sticky": "ne"})]}),
        ("null", {"side": "bottom", "sticky": "ew", "children": [
            (f"{prefix}.bl", {"side": "left", "sticky": "sw"}),
            (f"{prefix}.br", {"side": "right", "sticky": "se"})]}),
    ]


class RoundedStyles:
    """Creates the image elements and layouts once, repaints them per theme."""

    def __init__(self, root: tk.Misc, style: ttk.Style):
        self.root = root
        self.style = style
        self.photos: dict[str, "ImageTk.PhotoImage"] = {}

    def images(self, c: dict) -> dict:
        """Every image as name -> PIL image, for palette c."""
        out = {}
        for styleName, (behind, fill, hover, _, _) in BUTTONS.items():
            key = self.buttonKey(styleName)
            for variant, color in (("", fill), ("hover", hover), ("disabled", c["cardAlt"])):
                for corner, img in _corners(CONTROL_RADIUS, c[behind], c[color]
                                            if variant != "disabled" else color).items():
                    out[f"{key}:{corner}:{variant}"] = img
        for name, (radius, behind, fill) in SURFACES.items():
            for corner, img in _corners(radius, c[behind], c[fill]).items():
                out[f"Round{name}:{corner}:"] = img
        card, field = c["card"], c["input"]
        out.update({
            "arrow:": _chevron((18, 14), field, c["muted"]),
            "arrow:hover": _chevron((18, 14), field, c["accent"]),
            "spinUp:": _chevron((16, 9), field, c["muted"], up=True),
            "spinUp:hover": _chevron((16, 9), field, c["accent"], up=True),
            "spinDown:": _chevron((16, 9), field, c["muted"]),
            "spinDown:hover": _chevron((16, 9), field, c["accent"]),
            "check:": _check(card, c["control"]),
            "check:on": _check(card, c["accent"], mark=c["onAccent"]),
            "check:disabled": _check(card, c["cardAlt"]),
            "radio:": _radio(card, c["control"]),
            "radio:on": _radio(card, c["accent"], dot=c["onAccent"]),
            "info:": _info(card, c["accent"], c["onAccent"]),
        })
        return out

    @staticmethod
    def buttonKey(styleName: str) -> str:
        return "RoundButton" + styleName.replace(".TButton", "").replace("TButton", "Default")

    def infoImage(self):
        """The info badge, or None without Pillow."""
        return self.photos.get("info:")

    # ---------------------------------------------------------------- #

    def apply(self, c: dict, font) -> bool:
        """Configures the button, field and card styles for palette c.
        Returns False (square corners) if Pillow is missing."""
        rounded = available()
        self.configureColours(c, font, rounded)
        if not rounded:
            return False
        images = self.images(c)
        if self.photos:
            for name, img in images.items():
                self.photos[name].paste(img)
        else:
            for name, img in images.items():
                self.photos[name] = ImageTk.PhotoImage(img, master=self.root)
            self.createElements()
        return True

    def configureColours(self, c: dict, font, rounded: bool):
        style = self.style
        vertical = 1 if rounded else 6     # the corner strips add the rest
        for name, (_, fill, hover, fg, hoverFg) in BUTTONS.items():
            style.configure(name, background=c[fill], foreground=c[fg], borderwidth=0,
                            relief="flat", focuscolor=c[fill], bordercolor=c[fill],
                            lightcolor=c[fill], darkcolor=c[fill], font=font,
                            padding=(8 if name == "Small.TButton" else 14, vertical))
            style.map(name,
                      background=[("disabled", c["cardAlt"]), ("pressed", c[hover]),
                                  ("active", c[hover])],
                      foreground=[("disabled", c["muted"]),
                                  ("pressed", c[hoverFg or fg]), ("active", c[hoverFg or fg])],
                      focuscolor=[("pressed", c[hover]), ("active", c[hover])])
        for name in ("Card.TFrame", "Proposal.TFrame"):
            style.configure(name, borderwidth=0, relief="flat")
        for name in ("TEntry", "TCombobox", "Header.TCombobox", "TSpinbox"):
            style.configure(name, background=c["input"], borderwidth=0, relief="flat",
                            padding=(8, 1) if rounded else 5)

    def createElements(self):
        style = self.style

        def photo(name):
            return str(self.photos[name])

        # Corner elements
        for styleName in BUTTONS:
            key = self.buttonKey(styleName)
            for corner in CORNERS:
                style.element_create(f"{key}.{corner}", "image", photo(f"{key}:{corner}:"),
                                     ("disabled", photo(f"{key}:{corner}:disabled")),
                                     ("pressed", photo(f"{key}:{corner}:hover")),
                                     ("active", photo(f"{key}:{corner}:hover")), sticky="")
        for name in SURFACES:
            for corner in CORNERS:
                style.element_create(f"Round{name}.{corner}", "image",
                                     photo(f"Round{name}:{corner}:"), sticky="")
        style.element_create("Round.downarrow", "image", photo("arrow:"),
                             ("active", photo("arrow:hover")),
                             ("pressed", photo("arrow:hover")), sticky="")
        style.element_create("Round.spinup", "image", photo("spinUp:"),
                             ("active", photo("spinUp:hover")), sticky="")
        style.element_create("Round.spindown", "image", photo("spinDown:"),
                             ("active", photo("spinDown:hover")), sticky="")
        style.element_create("Round.checkindicator", "image", photo("check:"),
                             ("disabled", photo("check:disabled")),
                             ("selected", photo("check:on")), sticky="")
        style.element_create("Round.radioindicator", "image", photo("radio:"),
                             ("selected", photo("radio:on")), sticky="")

        # Cards: flat fill drawn by Tk, corners on top
        for styleName, name in (("Card.TFrame", "Card"), ("Proposal.TFrame", "Proposal")):
            style.layout(styleName, [("Frame.border", {"sticky": "nsew", "children":
                                                       cornerNodes(f"Round{name}")})])

        # Buttons
        for styleName in BUTTONS:
            style.layout(styleName, [("Button.border", {"sticky": "nsew", "children": [
                *cornerNodes(self.buttonKey(styleName)),
                ("Button.padding", {"sticky": "nsew", "children": [
                    ("Button.label", {"sticky": "nsew"})]})]})])

        # Input fields: Button.border paints the flat field background
        style.layout("TEntry", [("Button.border", {"sticky": "nsew", "children": [
            *cornerNodes("RoundField"),
            ("Entry.padding", {"sticky": "nsew", "children": [
                ("Entry.textarea", {"sticky": "nsew"})]})]})])
        for styleName, field in (("TCombobox", "RoundField"),
                                 ("Header.TCombobox", "RoundHeaderField")):
            style.layout(styleName, [("Button.border", {"sticky": "nsew", "children": [
                *cornerNodes(field),
                ("Round.downarrow", {"side": "right", "sticky": "ns"}),
                ("Combobox.padding", {"sticky": "nsew", "children": [
                    ("Combobox.textarea", {"sticky": "nsew"})]})]})])
        style.layout("TSpinbox", [("Button.border", {"sticky": "nsew", "children": [
            *cornerNodes("RoundField"),
            ("null", {"side": "right", "sticky": "", "children": [
                ("Round.spinup", {"side": "top", "sticky": "e"}),
                ("Round.spindown", {"side": "bottom", "sticky": "e"})]}),
            ("Spinbox.padding", {"sticky": "nsew", "children": [
                ("Spinbox.textarea", {"sticky": "nsew"})]})]})])

        # Check and radio buttons
        for kind, indicator in (("Checkbutton", "Round.checkindicator"),
                                ("Radiobutton", "Round.radioindicator")):
            style.layout(f"Card.T{kind}", [(f"{kind}.padding", {"sticky": "nsew", "children": [
                (indicator, {"side": "left", "sticky": ""}),
                (f"{kind}.focus", {"side": "left", "sticky": "w", "children": [
                    (f"{kind}.label", {"sticky": "nsew"})]})]})])
