import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageDraw, ImageTk
except ImportError:          # without Pillow the GUI keeps square corners
    Image = None

# Rounded corners for the ttk widgets of the GUI. #
#
# Tk cannot round corners itself, so cards, buttons, input fields, check and
# radio boxes and scrollbar thumbs are drawn as small images (anti-aliased by
# drawing them 4x larger and scaling down) and used as ttk image elements.
# Tk stretches the middle of each image and keeps its corners.
#
# Each image has the colour of whatever is behind the widget painted into
# its corners (instead of relying on transparency, which Tk handles
# differently per platform). A widget on another background therefore needs
# its own style, e.g. Header.TButton on the top bar.
#
# The images are created once and repainted in place when the theme changes.

SUPERSAMPLE = 4
CARD_RADIUS = 10
CONTROL_RADIUS = 7


def available() -> bool:
    return Image is not None


def _shape(size, outer, fill, radius, outline=None, box=None):
    """A rounded rectangle (fill, 1 px outline) on outer, as a PIL image."""
    s = SUPERSAMPLE
    w, h = size
    img = Image.new("RGB", (w * s, h * s), outer)
    draw = ImageDraw.Draw(img)
    x0, y0, x1, y1 = box or (0, 0, w, h)
    if outline:
        draw.rounded_rectangle([x0 * s, y0 * s, x1 * s - 1, y1 * s - 1], radius * s,
                               fill=outline)
        x0, y0, x1, y1, radius = x0 + 1, y0 + 1, x1 - 1, y1 - 1, radius - 1
    draw.rounded_rectangle([x0 * s, y0 * s, x1 * s - 1, y1 * s - 1], max(radius, 0) * s,
                           fill=fill)
    return img, draw


def _done(img, size):
    return img.resize(size, Image.LANCZOS)


def _check(outer, fill, outline, mark=None):
    """Check box 16x16 plus 7 px of space before the label."""
    size = (23, 16)
    img, draw = _shape(size, outer, fill, 4, outline, box=(0, 0, 16, 16))
    if mark:
        s = SUPERSAMPLE
        draw.line([(4 * s, 8.2 * s), (6.8 * s, 11 * s), (12 * s, 5 * s)],
                  fill=mark, width=int(2 * s), joint="curve")
    return _done(img, size)


def _radio(outer, fill, outline, dot=None):
    size = (23, 16)
    s = SUPERSAMPLE
    img = Image.new("RGB", (size[0] * s, size[1] * s), outer)
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, 16 * s - 1, 16 * s - 1], fill=outline)
    draw.ellipse([1 * s, 1 * s, 15 * s - 1, 15 * s - 1], fill=fill)
    if dot:
        draw.ellipse([5 * s, 5 * s, 11 * s - 1, 11 * s - 1], fill=dot)
    return _done(img, size)


def _chevron(size, outer, color, up=False):
    s = SUPERSAMPLE
    w, h = size
    img = Image.new("RGB", (w * s, h * s), outer)
    draw = ImageDraw.Draw(img)
    cx, cy, dx, dy = w / 2 - 1, h / 2, 3.5, 2 if not up else -2
    draw.line([((cx - dx) * s, (cy - dy) * s), (cx * s, (cy + dy) * s),
               ((cx + dx) * s, (cy - dy) * s)], fill=color, width=int(1.6 * s),
              joint="curve")
    return _done(img, size)


def _thumb(outer, color):
    """Scrollbar thumb: a 6 px wide pill in a 10 px wide trough."""
    size = (10, 30)
    img, _ = _shape(size, outer, color, 3, box=(2, 1, 8, 29))
    return _done(img, size)


def _box(size, outer, fill, radius, outline=None):
    img, _ = _shape(size, outer, fill, radius, outline)
    return _done(img, size)


class RoundedStyles:
    """Creates the image elements and layouts once, repaints them per theme."""

    def __init__(self, root: tk.Misc, style: ttk.Style):
        self.root = root
        self.style = style
        self.photos: dict[str, "ImageTk.PhotoImage"] = {}

    def images(self, c: dict) -> dict:
        card, bg, header, soft = c["card"], c["bg"], c["header"], c["accentSoft"]
        frame = (40, 40)
        control = (28, 28)

        def button(outer, fill, outline, hoverFill, hoverOutline):
            return {"": _box(control, outer, fill, CONTROL_RADIUS, outline),
                    "hover": _box(control, outer, hoverFill, CONTROL_RADIUS, hoverOutline),
                    "disabled": _box(control, outer, c["cardAlt"], CONTROL_RADIUS, c["border"])}

        out = {
            "card": {"": _box(frame, bg, card, CARD_RADIUS, c["border"])},
            "proposal": {"": _box(frame, bg, soft, CARD_RADIUS, c["accent"])},
            "secondary": button(card, c["cardAlt"], c["border"], soft, c["accent"]),
            "secondarySoft": button(soft, c["card"], c["border"], c["cardAlt"], c["accent"]),
            "accent": button(card, c["accent"], None, c["accentHover"], None),
            "success": button(soft, c["success"], None, c["successHover"], None),
            "danger": button(card, c["dangerSoft"], None, c["danger"], None),
            "header": button(header, c["headerButton"], None, c["headerButtonHover"], None),
            "field": {"": _box(control, card, c["input"], CONTROL_RADIUS, c["border"]),
                      "focus": _box(control, card, c["input"], CONTROL_RADIUS, c["accent"])},
            "headerField": {"": _box(control, header, c["input"], CONTROL_RADIUS,
                                     c["headerButton"]),
                            "focus": _box(control, header, c["input"], CONTROL_RADIUS,
                                          c["accent"])},
            "arrow": {"": _chevron((18, 14), c["input"], c["muted"]),
                      "hover": _chevron((18, 14), c["input"], c["accent"])},
            "spinUp": {"": _chevron((16, 9), c["input"], c["muted"], up=True),
                       "hover": _chevron((16, 9), c["input"], c["accent"], up=True)},
            "spinDown": {"": _chevron((16, 9), c["input"], c["muted"]),
                         "hover": _chevron((16, 9), c["input"], c["accent"])},
            "check": {"": _check(card, c["input"], c["border"]),
                      "on": _check(card, c["accent"], None, mark=c["onAccent"]),
                      "disabled": _check(card, c["cardAlt"], c["border"])},
            "radio": {"": _radio(card, c["input"], c["border"]),
                      "on": _radio(card, c["accent"], c["accent"], dot=c["onAccent"])},
            "thumbCard": {"": _thumb(card, c["border"]), "hover": _thumb(card, c["muted"])},
            "thumbRoot": {"": _thumb(bg, c["border"]), "hover": _thumb(bg, c["muted"])},
        }
        return out

    def apply(self, c: dict) -> bool:
        """Paints the elements for palette c. False if Pillow is missing."""
        if not available():
            return False
        images = self.images(c)
        if self.photos:
            for group, variants in images.items():
                for variant, img in variants.items():
                    self.photos[f"{group}:{variant}"].paste(img)
            return True
        for group, variants in images.items():
            for variant, img in variants.items():
                self.photos[f"{group}:{variant}"] = ImageTk.PhotoImage(img, master=self.root)
        self.createElements()
        return True

    def photo(self, name: str) -> str:
        return str(self.photos[name])

    def createElements(self):
        style, p = self.style, self.photo

        def element(name, group, border, padding=0, states=()):
            style.element_create(name, "image", p(f"{group}:"),
                                 *[(state, p(f"{group}:{variant}")) for state, variant in states],
                                 border=border, padding=padding, sticky="nsew")

        # Cards and the proposal bar
        element("Round.card", "card", CARD_RADIUS + 2)
        element("Round.proposal", "proposal", CARD_RADIUS + 2)
        style.layout("Card.TFrame", [("Round.card", {"sticky": "nsew"})])
        style.layout("Proposal.TFrame", [("Round.proposal", {"sticky": "nsew"})])

        # Buttons
        buttonStates = (("disabled", "disabled"), ("pressed", "hover"), ("active", "hover"))
        for group, styles in (("secondary", ("TButton", "Small.TButton")),
                              ("secondarySoft", ("Proposal.TButton",)),
                              ("accent", ("Accent.TButton",)),
                              ("success", ("Success.TButton",)),
                              ("danger", ("Danger.TButton",)),
                              ("header", ("Header.TButton",))):
            name = f"Round{group.capitalize()}.button"
            element(name, group, CONTROL_RADIUS + 2, states=buttonStates)
            for styleName in styles:
                style.layout(styleName, [(name, {"sticky": "nsew", "children": [
                    ("Button.padding", {"sticky": "nsew", "children": [
                        ("Button.label", {"sticky": "nsew"})]})]})])

        # Input fields with chevron arrows
        element("Round.field", "field", CONTROL_RADIUS + 2, padding=2,
                states=(("focus", "focus"),))
        element("RoundHeader.field", "headerField", CONTROL_RADIUS + 2, padding=2,
                states=(("focus", "focus"),))
        style.element_create("Round.downarrow", "image", p("arrow:"),
                             ("active", p("arrow:hover")), ("pressed", p("arrow:hover")),
                             sticky="")
        style.element_create("Round.spinup", "image", p("spinUp:"),
                             ("active", p("spinUp:hover")), sticky="")
        style.element_create("Round.spindown", "image", p("spinDown:"),
                             ("active", p("spinDown:hover")), sticky="")

        style.layout("TEntry", [("Round.field", {"sticky": "nsew", "children": [
            ("Entry.padding", {"sticky": "nsew", "children": [
                ("Entry.textarea", {"sticky": "nsew"})]})]})])
        for styleName, field in (("TCombobox", "Round.field"),
                                 ("Header.TCombobox", "RoundHeader.field")):
            style.layout(styleName, [(field, {"sticky": "nsew", "children": [
                ("Round.downarrow", {"side": "right", "sticky": "ns"}),
                ("Combobox.padding", {"sticky": "nsew", "children": [
                    ("Combobox.textarea", {"sticky": "nsew"})]})]})])
        style.layout("TSpinbox", [("Round.field", {"sticky": "nsew", "children": [
            ("null", {"side": "right", "sticky": "", "children": [
                ("Round.spinup", {"side": "top", "sticky": "e"}),
                ("Round.spindown", {"side": "bottom", "sticky": "e"})]}),
            ("Spinbox.padding", {"sticky": "nsew", "children": [
                ("Spinbox.textarea", {"sticky": "nsew"})]})]})])

        # Check and radio buttons
        style.element_create("Round.checkindicator", "image", p("check:"),
                             ("disabled", p("check:disabled")),
                             ("selected", p("check:on")), sticky="")
        style.element_create("Round.radioindicator", "image", p("radio:"),
                             ("selected", p("radio:on")), sticky="")
        for kind, indicator in (("Checkbutton", "Round.checkindicator"),
                                ("Radiobutton", "Round.radioindicator")):
            style.layout(f"Card.T{kind}", [(f"{kind}.padding", {"sticky": "nsew", "children": [
                (indicator, {"side": "left", "sticky": ""}),
                (f"{kind}.focus", {"side": "left", "sticky": "w", "children": [
                    (f"{kind}.label", {"sticky": "nsew"})]})]})])

        # Slim scrollbars without arrows
        for prefix, group in (("", "thumbCard"), ("Root.", "thumbRoot")):
            name = f"Round{group}.thumb"
            style.element_create(name, "image", p(f"{group}:"),
                                 ("pressed", p(f"{group}:hover")),
                                 ("active", p(f"{group}:hover")),
                                 border=(4, 8), sticky="nsew")
            style.layout(f"{prefix}Vertical.TScrollbar", [
                ("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                    (name, {"expand": "1", "sticky": "nsew"})]})])
