import math
import tkinter as tk

import theme

# Power chart drawn directly on a Tk Canvas. #
#
# Tk draws canvas shapes and text natively, so the chart stays sharp on
# high-resolution (Retina) screens, unlike an embedded matplotlib image.
#
# One rectangle per quarter: the area forecast is the base and every process
# is stacked on top of it. Hovering shows a crosshair with time, power and the
# process under the mouse.
#
# Mouse:
#   click empty space  -> onClick(quarter)
#   click a process    -> onSelect(processId)
#   drag a process     -> onMove(processId, newStartIndex), snapped to quarters
#   right-click process -> menu with "Remove" -> onRemove(processId)
#
# Dependencies: a dragged process cannot leave the window its dependencies
# allow (block["minStart"]..block["maxStart"]), the blocked time is shaded
# while dragging. The selected process gets arrows from the processes it
# waits for.
#
# Time outside the working hours (and lunch) is shaded, processes may only be
# dragged to valid starts (block["allowedStarts"]: inside the working hours,
# by the deadline and while the machine is free). A selected process with a
# deadline gets a dashed "Due" line.
#
# Optimisation proposal: ghosts are the processes the proposal would move,
# drawn as dashed outlines at their proposed position. Those processes are
# stacked last so the ghosts sit on the same base (area + processes that
# stay) and the top of a ghost is the proposed total load.

QUARTERS_PER_DAY = 96

# Colours come from a theme palette (theme.LIGHT / theme.DARK), see setTheme
FONT = theme.font(11)
FONT_BOLD = theme.font(11, "bold")


def quarterToLabel(index: int) -> str:
    minutes = index * 15
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def blend(color: str, amount: float, base: str = "#ffffff") -> str:
    """Mixes color towards base. amount=0 -> color, amount=1 -> base."""
    c = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(base[i:i + 2], 16) for i in (1, 3, 5)]
    mixed = [round(cv + (bv - cv) * amount) for cv, bv in zip(c, b)]
    return "#" + "".join(f"{v:02x}" for v in mixed)


def niceStep(maxValue: float, targetTicks: int = 6) -> float:
    raw = maxValue / targetTicks
    magnitude = 10 ** math.floor(math.log10(raw))
    for multiple in (1, 2, 2.5, 5, 10):
        if multiple * magnitude >= raw:
            return multiple * magnitude
    return 10 * magnitude


class PowerChart(tk.Canvas):

    MARGIN_LEFT = 64
    MARGIN_RIGHT = 16
    MARGIN_TOP = 44
    MARGIN_BOTTOM = 34

    def __init__(self, parent, onClick=None, onHover=None, onSelect=None,
                 onMove=None, onRemove=None, **kwargs):
        self.c: dict = dict(theme.LIGHT)   # colours of the current theme
        super().__init__(parent, bg=self.c["card"], highlightthickness=0, **kwargs)
        self.onClick = onClick      # called with the clicked quarter index
        self.onHover = onHover      # called with a row dict, or None on leave
        self.onSelect = onSelect    # called with a process id, or None
        self.onMove = onMove        # called with (process id, new start index)
        self.onRemove = onRemove    # called with a process id

        self.selectedId: int | None = None
        self.drag: dict | None = None   # state while a process is dragged

        self.rows: list[dict] = []
        self.blocks: list[dict] = []
        self.maxCap: float | None = None
        self.preview: dict | None = None
        self.colorFor = lambda name: "#2f6fde"
        self.hours: dict | None = None
        self.ghosts: list[dict] = []

        # segments[quarter] = list of (bottomKW, topKW, block) for processes
        self.segments: list[list[tuple]] = []
        # the same for ghosts of the optimisation proposal
        self.ghostSegments: list[list[tuple]] = []
        self.yMax = 1.0

        self.bind("<Configure>", lambda _: self.redraw())
        self.bind("<Motion>", self.handleMotion)
        self.bind("<Leave>", lambda _: self.hideCursor())
        self.bind("<Button-1>", self.handlePress)
        self.bind("<B1-Motion>", self.handleDrag)
        self.bind("<ButtonRelease-1>", self.handleRelease)
        # Right-click is Button-2 on macOS and Button-3 elsewhere
        for sequence in ("<Button-2>", "<Button-3>", "<Control-Button-1>"):
            self.bind(sequence, self.handleRightClick)

    # ----------------------------- Data ------------------------------ #

    def setData(self, rows: list[dict], blocks: list[dict],
                maxCap: float | None, preview: dict | None, colorFor,
                hours: dict | None = None, ghosts: list[dict] | None = None):
        """rows: combined profile, blocks: process blocks,
        preview: {"name", "kW", "startIndex", "endIndex"} or None,
        hours: working hours from GUIinstance.getWorkingHours() or None,
        ghosts: blocks of the optimisation proposal (same ids as blocks)."""
        self.hours = hours
        self.rows = rows
        self.blocks = blocks
        self.maxCap = maxCap
        self.preview = preview
        self.colorFor = colorFor
        self.ghosts = sorted(ghosts or [], key=lambda g: g["startIndex"])
        self.drag = None
        if self.selectedId not in {b["id"] for b in blocks}:
            self.selectedId = None
        self.redraw()

    def setTheme(self, colors: dict):
        """Switches to another palette (theme.LIGHT / theme.DARK)."""
        self.c = dict(colors)
        self.configure(bg=self.c["card"])
        self.redraw()

    def setSelected(self, processId: int | None):
        if processId != self.selectedId:
            self.selectedId = processId
            self.redraw()

    def displayBlocks(self) -> list[dict]:
        """The blocks to draw, with the dragged one at its new position."""
        if self.drag is None:
            return self.blocks
        shown = []
        for block in self.blocks:
            if block["id"] == self.drag["id"]:
                start = self.drag["newStart"]
                end = start + block["endIndex"] - block["startIndex"]
                block = {**block, "startIndex": start, "endIndex": end,
                         "startTime": quarterToLabel(start),
                         "endTime": quarterToLabel(end)}
            shown.append(block)
        return sorted(shown, key=lambda b: b["startIndex"])

    # -------------------------- Coordinates -------------------------- #

    def plotBox(self):
        width, height = self.winfo_width(), self.winfo_height()
        return (self.MARGIN_LEFT, self.MARGIN_TOP,
                width - self.MARGIN_RIGHT, height - self.MARGIN_BOTTOM)

    def xOf(self, quarter: float) -> float:
        left, _, right, _ = self.plotBox()
        return left + (right - left) * quarter / QUARTERS_PER_DAY

    def yOf(self, kW: float) -> float:
        _, top, _, bottom = self.plotBox()
        return bottom - (bottom - top) * kW / self.yMax

    def quarterAt(self, x: float) -> int | None:
        left, _, right, _ = self.plotBox()
        if not left <= x < right:
            return None
        return min(int((x - left) / (right - left) * QUARTERS_PER_DAY),
                   QUARTERS_PER_DAY - 1)

    def kWAt(self, y: float) -> float:
        _, top, _, bottom = self.plotBox()
        return (bottom - y) / (bottom - top) * self.yMax

    # ---------------------------- Drawing ---------------------------- #

    def redraw(self):
        self.delete("all")
        left, top, right, bottom = self.plotBox()
        if right - left < 50 or bottom - top < 50:
            return
        if not self.rows:
            self.create_text((left + right) / 2, (top + bottom) / 2,
                             text="No data", fill=self.c["muted"], font=FONT)
            return

        stackTop = [row["areaKW"] for row in self.rows]
        self.segments = [[] for _ in self.rows]
        ghostIds = {g["id"] for g in self.ghosts}
        # Processes that stay first, processes the proposal moves last
        # (sorted() is stable, so start order is kept within each group)
        ordered = sorted(self.displayBlocks(), key=lambda b: b["id"] in ghostIds)
        ghostBase = None
        for block in ordered:
            if ghostBase is None and block["id"] in ghostIds:
                ghostBase = list(stackTop)
            for q in range(block["startIndex"], min(block["endIndex"], len(self.rows))):
                self.segments[q].append((stackTop[q], stackTop[q] + block["kW"], block))
                stackTop[q] += block["kW"]

        ghostTop = list(stackTop if ghostBase is None else ghostBase)
        self.ghostSegments = [[] for _ in self.rows]
        for ghost in self.ghosts:
            for q in range(ghost["startIndex"], min(ghost["endIndex"], len(self.rows))):
                self.ghostSegments[q].append((ghostTop[q], ghostTop[q] + ghost["kW"], ghost))
                ghostTop[q] += ghost["kW"]

        previewTop = list(stackTop)
        if self.preview:
            for q in range(self.preview["startIndex"],
                           min(self.preview["endIndex"], len(self.rows))):
                previewTop[q] += self.preview["kW"]

        highest = max(previewTop + ghostTop + [self.maxCap or 0])
        step = niceStep(highest * 1.1 or 1)
        self.yMax = math.ceil(highest * 1.1 / step) * step or step

        self.drawClosedTime(top, bottom)
        self.drawBlockedTime(top, bottom)
        self.drawOverCapacity(top, bottom)
        self.drawGrid(step, left, right, top, bottom)
        self.drawBars()
        self.drawGhosts()
        self.drawPreview(stackTop)
        self.drawDeadline(top, bottom)
        self.drawDependencyArrows()
        self.drawCapacity(left, right)
        self.drawXAxis(left, right, bottom)
        self.drawLegend(left, top)

    def bar(self, quarter: int, lowKW: float, highKW: float, color: str, tags=()):
        # 1 px gap between quarters keeps the rectangles readable
        x0, x1 = self.xOf(quarter) + 0.5, self.xOf(quarter + 1) - 0.5
        self.create_rectangle(x0, self.yOf(highKW), x1, self.yOf(lowKW),
                              fill=color, outline="", tags=tags)

    def isWorking(self, quarter: int) -> bool:
        h = self.hours
        if h is None:
            return True
        if not h["startIndex"] <= quarter < h["endIndex"]:
            return False
        return not (h["lunchStartIndex"] is not None
                    and h["lunchStartIndex"] <= quarter < h["lunchEndIndex"])

    def closedRanges(self) -> list[tuple[int, int, str]]:
        """(start, end, label) for every stretch of non-working time."""
        h = self.hours
        if h is None:
            return []
        ranges = [(0, h["startIndex"], "Closed"),
                  (h["endIndex"], QUARTERS_PER_DAY, "Closed")]
        if h["lunchStartIndex"] is not None:
            ranges.append((h["lunchStartIndex"], h["lunchEndIndex"], "Lunch"))
        return [r for r in ranges if r[1] > r[0]]

    def drawClosedTime(self, top, bottom):
        for start, end, label in self.closedRanges():
            x0, x1 = self.xOf(start), self.xOf(end)
            self.create_rectangle(x0, top, x1, bottom, fill=self.c["closed"], outline="")
            textId = self.create_text((x0 + x1) / 2, top + 4, text=label,
                                      anchor=tk.N, fill=self.c["muted"], font=FONT)
            # Hide the label if the stretch is too narrow for it
            x0t, _, x1t, _ = self.bbox(textId)
            if x1t - x0t > x1 - x0 - 4:
                self.delete(textId)

    def drawBlockedTime(self, top, bottom):
        """While dragging, shade the time the dependencies do not allow."""
        if self.drag is None:
            return
        allowedFrom = self.drag["minStart"]
        allowedTo = self.drag["maxStart"] + self.drag["duration"]
        for start, end in ((0, allowedFrom), (allowedTo, QUARTERS_PER_DAY)):
            if end > start:
                self.create_rectangle(self.xOf(start), top, self.xOf(end), bottom,
                                      fill=self.c["blocked"], outline="")

    def blockById(self, blockId: int) -> dict | None:
        return next((b for b in self.displayBlocks() if b["id"] == blockId), None)

    def blockTop(self, blockId: int, quarter: int) -> float:
        """Top (kW) of a process in a given quarter of the stack."""
        for _, high, block in self.segments[quarter]:
            if block["id"] == blockId:
                return high
        return 0.0

    def drawDependencyArrows(self):
        """Arrows from the end of each dependency to the selected process."""
        selected = self.blockById(self.selectedId) if self.selectedId is not None else None
        if selected is None:
            return
        _, top, _, _ = self.plotBox()
        for depId in selected.get("dependsOn", []):
            dep = self.blockById(depId)
            if dep is None:
                continue
            x0 = self.xOf(dep["endIndex"]) - 2
            y0 = self.yOf(self.blockTop(depId, dep["endIndex"] - 1))
            x1 = self.xOf(selected["startIndex"]) + 2
            y1 = self.yOf(self.blockTop(selected["id"], selected["startIndex"]))
            lift = max(18, abs(x1 - x0) * 0.25)
            ym = max(min(y0, y1) - lift, top - 10)
            ok = selected["startIndex"] >= dep["endIndex"]
            self.create_line(x0, y0, (x0 + x1) / 2, ym, x1, y1, smooth=True,
                             arrow=tk.LAST, width=1.5, fill=self.c["text"] if ok else self.c["danger"])

    def drawOverCapacity(self, top, bottom):
        for row in self.rows:
            if row["overCapacity"]:
                self.create_rectangle(self.xOf(row["index"]), top,
                                      self.xOf(row["index"] + 1), bottom,
                                      fill=self.c["overCap"], outline="")

    def drawGrid(self, step, left, right, top, bottom):
        value = 0.0
        while value <= self.yMax + 1e-9:
            y = self.yOf(value)
            self.create_line(left, y, right, y, fill=self.c["grid"] if value else self.c["border"])
            self.create_text(left - 8, y, text=f"{value:g} kW", anchor=tk.E,
                             fill=self.c["muted"], font=FONT)
            value += step

    def drawBars(self):
        for row in self.rows:
            self.bar(row["index"], 0, row["areaKW"], self.c["area"])
        for q, segments in enumerate(self.segments):
            for low, high, block in segments:
                self.bar(q, low, high, self.colorFor(block["machine"]),
                         tags=("process", f"block{block['id']}"))
        self.resetOutlines()

    @staticmethod
    def breaksARule(block: dict) -> bool:
        return bool(block.get("outsideHours") or block.get("lateForDeadline")
                    or block.get("overlapsWith"))

    def resetOutlines(self, hoveredId: int | None = None):
        """Selected process gets a dark outline, hovered one a light one.
        Processes that break a rule get a red one."""
        self.itemconfigure("process", outline="")
        for block in self.blocks:
            if self.breaksARule(block):
                self.itemconfigure(f"block{block['id']}", outline=self.c["danger"], width=2)
        if hoveredId is not None:
            self.itemconfigure(f"block{hoveredId}", outline=self.c["muted"], width=1)
        if self.selectedId is not None:
            selected = self.blockById(self.selectedId)
            for depId in (selected or {}).get("dependsOn", []):
                self.itemconfigure(f"block{depId}", outline=self.c["text"], width=1)
            self.itemconfigure(f"block{self.selectedId}", outline=self.c["text"], width=2)

    def ghostColor(self, color: str) -> str:
        """A darker (light theme) or lighter (dark theme) shade, visible both
        on the background and on the solid block."""
        return blend(color, 0.35, base=self.c["ghostBase"])

    def drawGhosts(self):
        """Dashed outline of every process at its proposed position. One
        polygon per process that follows the stack quarter by quarter."""
        for ghost in self.ghosts:
            spans = [(q, low, high) for q, segments in enumerate(self.ghostSegments)
                     for low, high, g in segments if g is ghost]
            if not spans:
                continue
            topEdge, bottomEdge = [], []
            for q, low, high in spans:
                x0, x1 = self.xOf(q) + 1, self.xOf(q + 1) - 1
                topEdge += [x0, self.yOf(high) + 1, x1, self.yOf(high) + 1]
                bottomEdge = [x1, self.yOf(low) - 1, x0, self.yOf(low) - 1] + bottomEdge
            self.create_polygon(topEdge + bottomEdge, fill="", width=2, dash=(5, 3),
                                outline=self.ghostColor(self.colorFor(ghost["machine"])),
                                tags=("ghost",))

    def drawDeadline(self, top, bottom):
        """Dashed line at the deadline of the selected (or dragged) process."""
        blockId = self.drag["id"] if self.drag else self.selectedId
        block = self.blockById(blockId) if blockId is not None else None
        if block is None or block.get("deadlineIndex") is None:
            return
        x = self.xOf(block["deadlineIndex"])
        self.create_line(x, top, x, bottom, fill=self.c["danger"], width=1.5, dash=(6, 4))
        self.create_text(x - 4, top + 22, text=f"Due {quarterToLabel(block['deadlineIndex'])}",
                         anchor=tk.NE, fill=self.c["danger"], font=FONT_BOLD)

    def drawPreview(self, stackTop):
        if not self.preview:
            return
        color = blend(self.colorFor(self.preview["name"]), 0.6, self.c["card"])
        for q in range(self.preview["startIndex"],
                       min(self.preview["endIndex"], len(self.rows))):
            self.bar(q, stackTop[q], stackTop[q] + self.preview["kW"], color)

    def drawCapacity(self, left, right):
        if self.maxCap is None:
            return
        y = self.yOf(self.maxCap)
        self.create_line(left, y, right, y, fill=self.c["danger"], width=1.5, dash=(6, 4))
        self.create_text(right, y - 4, text=f"Max {self.maxCap:g} kW",
                         anchor=tk.SE, fill=self.c["danger"], font=FONT_BOLD)

    def drawXAxis(self, left, right, bottom):
        for hour in range(0, 25):
            x = self.xOf(hour * 4)
            major = hour % 2 == 0
            self.create_line(x, bottom, x, bottom + (6 if major else 3), fill=self.c["muted"])
            if major:
                self.create_text(x, bottom + 8, text=f"{hour:02d}:00", anchor=tk.N,
                                 fill=self.c["muted"], font=FONT)

    def drawLegend(self, left, top):
        items = [("Area forecast", self.c["area"])]
        if self.closedRanges():
            items.append(("Closed", self.c["closed"]))
        seen = set()
        for block in self.blocks:
            if block["machine"] not in seen:
                seen.add(block["machine"])
                items.append((block["machine"], self.colorFor(block["machine"])))
        if self.preview:
            items.append(("Preview", blend(self.colorFor(self.preview["name"]), 0.6, self.c["card"])))
        if self.ghosts:
            items.append(("Proposed", None))

        x, y = left, top - 24
        for label, color in items:
            if color is None:   # ghost: dashed outline, no fill
                self.create_rectangle(x + 1, y - 5, x + 11, y + 5, fill="",
                                      outline=self.c["text"], width=2, dash=(3, 2))
            else:
                self.create_rectangle(x, y - 6, x + 12, y + 6, fill=color, outline="")
            textId = self.create_text(x + 18, y, text=label, anchor=tk.W,
                                      fill=self.c["text"], font=FONT)
            x = self.bbox(textId)[2] + 18

    # ----------------------------- Cursor ---------------------------- #

    def hideCursor(self):
        self.delete("cursor")
        self.resetOutlines()
        self.configure(cursor="")
        if self.onHover:
            self.onHover(None)

    def handleMotion(self, event):
        self.delete("cursor")
        quarter = self.quarterAt(event.x)
        _, top, _, bottom = self.plotBox()
        if quarter is None or not self.rows or not top <= event.y <= bottom:
            self.hideCursor()
            return

        kW = self.kWAt(event.y)
        left, _, right, _ = self.plotBox()
        x = self.xOf(quarter + 0.5)
        self.create_line(x, top, x, bottom, fill=self.c["text"], dash=(2, 3), tags="cursor")
        self.create_line(left, event.y, right, event.y, fill=self.c["text"], dash=(2, 3),
                         tags="cursor")

        lines = [f"{quarterToLabel(quarter)}–{quarterToLabel(quarter + 1)}   {kW:.1f} kW"]
        if not self.isWorking(quarter):
            lines.append("Outside working hours")
        hovered = self.blockAt(quarter, kW)
        ghost = self.ghostAt(quarter, kW)
        self.resetOutlines(hovered["id"] if hovered else None)
        self.configure(cursor="hand2" if hovered or ghost else "crosshair")
        if hovered:
            lines.append(f"#{hovered['id'] + 1} {hovered['machine']}  ·  "
                         f"{hovered['kW']:g} kW  ·  "
                         f"{hovered['startTime']}–{hovered['endTime']}")
            lines += self.blockNotes(hovered)
            proposed = next((g for g in self.ghosts if g["id"] == hovered["id"]), None)
            if proposed and proposed is not ghost:
                lines.append(f"Proposed: move to {proposed['startTime']}–{proposed['endTime']}")
        elif kW <= self.rows[quarter]["areaKW"]:
            lines.append(f"Area forecast  ·  {self.rows[quarter]['areaKW']:.1f} kW")
        if ghost:
            lines.append(f"Proposed: #{ghost['id'] + 1} {ghost['machine']}  "
                         f"{ghost['fromStartTime']}–{ghost['fromEndTime']} → "
                         f"{ghost['startTime']}–{ghost['endTime']}")
        self.drawTooltip(event.x, event.y, "\n".join(lines))

        if self.onHover:
            self.onHover(self.rows[quarter])

    def blockNotes(self, block: dict) -> list[str]:
        """Tooltip lines about the rules a process has to keep."""
        lines = []
        if block.get("deadline"):
            lines.append(f"Due by {block['deadline']}")
        if block.get("lateForDeadline"):
            lines.append("Ends after its deadline")
        if block.get("outsideHours"):
            lines.append("Runs outside the working hours")
        elif block.get("pastHours"):
            lines.append("Runs past the working hours (allowed for this machine)")
        for otherId in block.get("overlapsWith", []):
            lines.append(f"Runs at the same time as #{otherId + 1} on the same machine")
        deps = [self.blockById(d) for d in block.get("dependsOn", [])]
        if deps:
            lines.append("After " + ", ".join(
                f"#{d['id'] + 1} {d['machine']}" for d in deps if d))
        return lines

    def blockAt(self, quarter: int, kW: float) -> dict | None:
        if quarter >= len(self.segments):
            return None
        for low, high, block in self.segments[quarter]:
            if low <= kW < high:
                return block
        return None

    def ghostAt(self, quarter: int, kW: float) -> dict | None:
        if quarter >= len(self.ghostSegments):
            return None
        for low, high, ghost in self.ghostSegments[quarter]:
            if low <= kW < high:
                return ghost
        return None

    def drawTooltip(self, x, y, text):
        textId = self.create_text(x + 14, y - 14, text=text, anchor=tk.SW,
                                  fill=self.c["tooltipFg"], font=FONT, tags="cursor")
        x0, y0, x1, y1 = self.bbox(textId)
        # Flip to the other side of the mouse if it would leave the chart
        dx = -(x1 - x0) - 28 if x1 + 8 > self.winfo_width() else 0
        dy = (y1 - y0) + 28 if y0 - 8 < 0 else 0
        self.move(textId, dx, dy)
        x0, y0, x1, y1 = self.bbox(textId)
        boxId = self.create_rectangle(x0 - 8, y0 - 5, x1 + 8, y1 + 5,
                                      fill=self.c["tooltipBg"], outline="", tags="cursor")
        self.tag_lower(boxId, textId)

    # ------------------------- Click and drag ----------------------- #

    def processAt(self, event) -> dict | None:
        quarter = self.quarterAt(event.x)
        if quarter is None or not self.rows:
            return None
        return self.blockAt(quarter, self.kWAt(event.y))

    def handlePress(self, event):
        block = self.processAt(event)
        if block is None:
            self.drag = None
            quarter = self.quarterAt(event.x)
            ghost = self.ghostAt(quarter, self.kWAt(event.y)) if quarter is not None else None
            if ghost is not None:
                # A ghost cannot be dragged, clicking it selects its process
                self.setSelected(ghost["id"])
                if self.onSelect:
                    self.onSelect(ghost["id"])
            elif quarter is not None and self.onClick:
                self.onClick(quarter)
            return
        self.drag = {"id": block["id"],
                     "offset": self.quarterAt(event.x) - block["startIndex"],
                     "duration": block["endIndex"] - block["startIndex"],
                     "start": block["startIndex"],
                     "newStart": block["startIndex"],
                     "minStart": block.get("minStart", 0),
                     "maxStart": block.get("maxStart", QUARTERS_PER_DAY
                                           - (block["endIndex"] - block["startIndex"])),
                     "deadline": block.get("deadlineIndex"),
                     "allowed": block.get("allowedStarts")}
        self.setSelected(block["id"])

    def handleDrag(self, event):
        if self.drag is None:
            return
        left, _, right, _ = self.plotBox()
        quarter = self.quarterAt(min(max(event.x, left), right - 1))
        wanted = quarter - self.drag["offset"]
        allowed = self.drag["allowed"]
        if allowed is None:
            newStart = min(max(wanted, self.drag["minStart"]), self.drag["maxStart"])
        elif allowed:
            # Snap to the closest start inside working hours and dependencies
            newStart = min(allowed, key=lambda s: (abs(s - wanted), s))
        else:
            newStart = self.drag["start"]
        if newStart != self.drag["newStart"]:
            self.drag["newStart"] = newStart
            self.redraw()
        self.delete("cursor")
        self.configure(cursor="sb_h_double_arrow")
        end = newStart + self.drag["duration"]
        text = f"Move to {quarterToLabel(newStart)}–{quarterToLabel(end)}"
        lastStart = QUARTERS_PER_DAY - self.drag["duration"]
        deadline = self.drag["deadline"]
        if (newStart == self.drag["maxStart"] < lastStart and deadline is not None
                and end == deadline):
            text += f"\nLimited by the deadline {quarterToLabel(deadline)}"
        elif (newStart == self.drag["minStart"] > 0) or (
                newStart == self.drag["maxStart"] < lastStart):
            text += "\nLimited by dependencies"
        self.drawTooltip(event.x, event.y, text)

    def handleRelease(self, _event):
        if self.drag is None:
            return
        drag, self.drag = self.drag, None
        if drag["newStart"] != drag["start"] and self.onMove:
            self.onMove(drag["id"], drag["newStart"])
        else:
            self.redraw()
            if self.onSelect:
                self.onSelect(drag["id"])

    def handleRightClick(self, event):
        block = self.processAt(event)
        if block is None:
            return
        self.setSelected(block["id"])
        if self.onSelect:
            self.onSelect(block["id"])
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label=f"Remove {block['machine']} ({block['startTime']}–{block['endTime']})",
            command=lambda: self.onRemove and self.onRemove(block["id"]))
        menu.tk_popup(event.x_root, event.y_root)
