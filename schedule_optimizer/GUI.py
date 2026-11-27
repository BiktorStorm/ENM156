import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox

import rounded
import theme
from InterfaceGUI import GUIinstance
from powerChart import PowerChart, quarterToLabel

# A simple GUI. It only talks to the backend through GUIinstance. #
#
# The chart draws one rectangle per quarter. The area forecast is the base
# and every process is stacked on top of it, snapped to the quarter grid.
# Hover the chart to see time, power and process, click it to pick the start
# time of the next process. Drag a process to move it, right-click it (or
# select it and press Delete) to remove it. The chart lives in powerChart.py.
#
# Processes are numbered #1, #2, ... and a process can depend on others
# ("Depends on..." button): it may not start until all of them are done.
# A process can have a deadline ("Deadline..." button) and a machine runs
# one process at a time. Machines ticked "After hours" may run through lunch
# and after closing, but still start within the working hours.
#
# "Optimize day" only proposes new start times: the processes that would
# move are drawn as dashed outlines and nothing changes until the proposal
# is accepted. Rejecting it (or changing the schedule) throws it away.
#
# Colours come from theme.py. Settings (⚙ in the top bar) switch between
# light mode, dark mode and following the system. The info badges open a small
# box with help text, a click anywhere (or Esc) closes it. Rounded corners
# come from rounded.py (needs Pillow, square corners without it).

QUARTERS_PER_DAY = 96
SIDEBAR_WIDTH = 360
NO_DEADLINE = "No deadline"

FONT = theme.font(12)
FONT_SMALL = theme.font(11)
FONT_SMALL_BOLD = theme.font(11, "bold")
FONT_BOLD = theme.font(12, "bold")
FONT_CARD_TITLE = theme.font(13, "bold")
FONT_TITLE = theme.font(17, "bold")
FONT_STAT = theme.font(20, "bold")

# Stat tiles: key, name, palette colour of the stripe
STAT_TILES = [("peak", "Peak power", "accent"),
              ("peakTime", "Peak at", "warning"),
              ("own", "Own energy", "success"),
              ("over", "Quarters over cap.", "danger")]

INFO_AFTER_HOURS = (
    "After-hours machines must start within the working hours, but may then "
    "keep running through lunch and after closing (until 24:00).\n\n"
    "Click the box in the After hours column to change it for a machine "
    "that is already added.")
INFO_NEW_PROCESS = (
    "Click the chart to pick a start time.\n\n"
    "Due by is the latest time the process may finish. The list only shows "
    "times after the chosen start and length.\n\n"
    "A machine runs one process at a time, so overlapping processes on the "
    "same machine are refused.")
INFO_PROCESSES = (
    "Select a process to edit it. Earlier / Later move it 15 minutes, or drag it in the "
    "chart.\n\nBlue rows would be moved by the current optimisation "
    "proposal. Red rows break a rule: outside the working hours, after their "
    "deadline or at the same time as another process on the machine.")
INFO_MAX_SHIFT = (
    "How many quarters (15 min) each process may move from where it is now.\n\n"
    "Optimize day only proposes changes: they are drawn as dashed outlines "
    "and nothing moves until you press Accept. Pressing it again starts from "
    "the real schedule, so the shift never adds up.")
INFO_HOURS = (
    "Processes have to run inside the working hours and not during lunch. "
    "After-hours machines only have to start inside them.\n\n"
    "Leave lunch empty for no lunch.")
INFO_CHART = (
    "Hover to inspect a quarter. Click empty space to pick the start of a new "
    "process, drag a process to move it and right-click it to remove it.\n\n"
    "Dashed outlines show where an optimisation proposal would move "
    "processes. The red dashed line is the deadline of the selected process.")


def peakChangeText(reductionKW: float, proposed: bool) -> tuple[str, str]:
    """Text and label style for the change in peak power on the Peak power
    card (reduction = current peak - optimised peak). Only a reduction that
    shows as at least 0.1 kW is green, no change is neutral and a higher
    peak is red."""
    shown = float(f"{reductionKW:.1f}")
    when = "proposed" if proposed else "optimised"
    if shown > 0:
        return f"−{shown:.1f} kW {when}", "Gain.TLabel"
    if shown < 0:
        return f"+{-shown:.1f} kW {when}", "Loss.TLabel"
    return "No peak reduction", "StatName.TLabel"


def deadlineChoices(firstEnd: int = 1) -> list[str]:
    """The Due by list: 'No deadline' and every quarter from firstEnd
    (the earliest possible end) to 24:00."""
    first = min(max(firstEnd, 1), QUARTERS_PER_DAY)
    return [NO_DEADLINE] + [quarterToLabel(q) for q in range(first, QUARTERS_PER_DAY + 1)]


def parseDeadline(choice: str) -> str | None:
    """'HH:MM' from the Due by list, None for no deadline."""
    choice = choice.strip()
    return None if not choice or choice == NO_DEADLINE else choice


class App(tk.Tk):

    def __init__(self, gui: GUIinstance, settingsPath: Path | None = None):
        super().__init__()
        self.gui = gui
        self.settingsPath = settingsPath
        self.settings = theme.loadSettings(settingsPath)
        self.c = theme.palette(self.settings["appearance"])
        self.title(f"Schedule optimizer – {gui.getCompanyName()}")
        self.geometry("1320x820")
        self.minsize(1060, 660)
        self.style = ttk.Style(self)
        self.style.theme_use("clam")
        self.rounded = rounded.RoundedStyles(self, self.style)
        self.applyStyles()

        self.machineColors: dict[str, str] = {}
        self.previewIndex: int | None = None
        # Optimisation proposal on show (GUIinstance.getOptimizationPreview)
        self.proposal: dict | None = None
        # Peak reduction of the last accepted proposal, shown while the
        # schedule is still the accepted one
        self.applied: dict | None = None
        # Plain tk widgets that need their background switched with the theme
        self.tkBackgrounds: list[tuple[tk.Widget, str]] = []
        self.comboboxes: list[ttk.Combobox] = []
        self.infoIcons: set = set()
        self.infoPopup: InfoPopup | None = None

        self.status = tk.StringVar(value="Ready")
        self.buildHeader()
        ttk.Label(self, textvariable=self.status, style="Status.TLabel",
                  anchor=tk.W, padding=(20, 6)).pack(side=tk.BOTTOM, fill=tk.X)

        body = ttk.Frame(self, style="Root.TFrame", padding=(16, 14, 16, 10))
        body.pack(fill=tk.BOTH, expand=True)
        sidebar = self.buildScrollableSidebar(body)
        main = ttk.Frame(body, style="Root.TFrame")
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))

        self.buildMachinePanel(sidebar)
        self.buildProcessPanel(sidebar)
        self.buildChartPanel(main)
        self.applyTheme()

        self.bind("<Escape>", self.onEscape)
        self.bind_all("<Button-1>", self.onAnyClick, add="+")
        self.bind("<Configure>", lambda e: e.widget is self and self.closeInfo())

        self.run(self.loadAreaData)
        self.refreshMachines()
        self.refreshProcesses()
        self.plotIfReady()

    # ----------------------------- Theme ----------------------------- #

    def applyStyles(self):
        """(Re)configures every ttk style from the current palette. ttk
        widgets pick the change up at once."""
        c, style = self.c, self.style
        style.configure(".", background=c["bg"], foreground=c["text"], font=FONT,
                        bordercolor=c["border"], lightcolor=c["card"],
                        darkcolor=c["card"], troughcolor=c["cardAlt"],
                        fieldbackground=c["input"], selectbackground=c["select"],
                        selectforeground=c["text"], insertcolor=c["text"],
                        focuscolor=c["accent"])
        style.configure("Root.TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["card"])
        style.configure("Flat.TFrame", background=c["card"], relief="flat", borderwidth=0)
        style.configure("Card.TLabel", background=c["card"], foreground=c["text"])
        style.configure("CardTitle.TLabel", background=c["card"], foreground=c["text"],
                        font=FONT_CARD_TITLE)
        style.configure("TitleBar.TFrame", background=c["accent"])
        style.configure("Muted.TLabel", background=c["card"], foreground=c["muted"],
                        font=FONT_SMALL)
        style.configure("Field.TLabel", background=c["card"], foreground=c["muted"],
                        font=FONT_SMALL)
        style.configure("Info.TLabel", background=c["card"], foreground=c["accent"],
                        font=FONT_SMALL_BOLD)
        style.configure("Status.TLabel", background=c["card"], foreground=c["muted"],
                        font=FONT_SMALL)
        style.configure("Cursor.TLabel", background=c["bg"], foreground=c["muted"],
                        font=FONT_SMALL)

        # Top bar
        style.configure("Header.TFrame", background=c["header"])
        style.configure("Header.TLabel", background=c["header"],
                        foreground=c["headerText"], font=FONT_TITLE)
        style.configure("HeaderMark.TFrame", background=c["warning"])
        style.configure("HeaderMuted.TLabel", background=c["header"],
                        foreground=c["headerMuted"], font=FONT)

        # Stat tiles
        style.configure("StatValue.TLabel", background=c["card"], foreground=c["text"],
                        font=FONT_STAT)
        style.configure("StatName.TLabel", background=c["card"], foreground=c["muted"],
                        font=FONT_SMALL)
        style.configure("Gain.TLabel", background=c["card"], foreground=c["success"],
                        font=FONT_SMALL_BOLD)
        style.configure("Loss.TLabel", background=c["card"], foreground=c["danger"],
                        font=FONT_SMALL_BOLD)
        for key, _, colorKey in STAT_TILES:
            style.configure(f"{key}.Stripe.TFrame", background=c[colorKey])

        # Optimisation proposal bar
        style.configure("Proposal.TFrame", background=c["accentSoft"])
        style.configure("Proposal.TLabel", background=c["accentSoft"],
                        foreground=c["text"], font=FONT_BOLD)

        # Buttons, input fields and cards: colours, padding and rounded
        # corners (see rounded.py)
        self.rounded.apply(c, FONT)

        # Check and radio buttons
        for name in ("Card.TCheckbutton", "Card.TRadiobutton"):
            style.configure(name, background=c["card"], foreground=c["text"],
                            indicatorbackground=c["control"], indicatorforeground=c["onAccent"],
                            indicatormargin=(0, 0, 6, 0), focuscolor=c["card"],
                            bordercolor=c["border"], upperbordercolor=c["border"],
                            lowerbordercolor=c["border"])
            style.map(name, background=[("active", c["card"])],
                      indicatorbackground=[("selected", c["accent"]),
                                           ("pressed", c["accentSoft"])],
                      foreground=[("disabled", c["muted"])])

        # Inputs
        # Inputs: flat filled fields, the fill must not change with the
        # state or it would no longer match the rounded corners
        for widget in ("TEntry", "TCombobox", "Header.TCombobox", "TSpinbox"):
            style.configure(widget, fieldbackground=c["input"], foreground=c["text"],
                            bordercolor=c["input"], lightcolor=c["input"],
                            darkcolor=c["input"], arrowcolor=c["muted"],
                            insertcolor=c["text"], insertwidth=1,
                            selectbackground=c["select"], selectforeground=c["text"])
            style.map(widget, fieldbackground=[("readonly", c["input"])],
                      foreground=[("readonly", c["text"])],
                      selectbackground=[("readonly", c["input"])],
                      selectforeground=[("readonly", c["text"])],
                      arrowcolor=[("active", c["accent"])])
        # Drop-down lists of comboboxes (plain tk listboxes)
        for option, key in (("background", "input"), ("foreground", "text"),
                            ("selectBackground", "accent"), ("selectForeground", "onAccent")):
            self.option_add(f"*TCombobox*Listbox.{option}", c[key])
        self.option_add("*TCombobox*Listbox.font", FONT)

        # Scrollbars: slim and flat, no arrow buttons
        for name, trough in (("Vertical.TScrollbar", c["card"]),
                             ("Root.Vertical.TScrollbar", c["bg"])):
            style.layout(name, [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nsew"})]})])
            style.configure(name, background=c["border"], troughcolor=trough,
                            bordercolor=trough, lightcolor=c["border"],
                            darkcolor=c["border"], gripcount=0, arrowsize=8)
            style.map(name, background=[("pressed", c["muted"]), ("active", c["muted"])],
                      lightcolor=[("pressed", c["muted"]), ("active", c["muted"])],
                      darkcolor=[("pressed", c["muted"]), ("active", c["muted"])])

        # Tables
        style.configure("Treeview", background=c["card"], fieldbackground=c["card"],
                        foreground=c["text"], bordercolor=c["card"],
                        lightcolor=c["card"], darkcolor=c["card"], rowheight=28,
                        font=FONT_SMALL)
        style.configure("Treeview.Heading", background=c["cardAlt"], foreground=c["muted"],
                        font=FONT_SMALL_BOLD, relief="flat", bordercolor=c["border"],
                        lightcolor=c["cardAlt"], darkcolor=c["cardAlt"], padding=(6, 5))
        style.map("Treeview.Heading", background=[("active", c["accentSoft"])])
        style.map("Treeview", background=[("selected", c["select"])],
                  foreground=[("selected", c["text"])])

    def applyTheme(self):
        """Applies the current palette to everything on screen."""
        self.closeInfo()
        self.applyStyles()
        self.configure(bg=self.c["bg"])
        for widget, key in self.tkBackgrounds:
            widget.configure(bg=self.c[key])
        for combobox in self.comboboxes:
            # Drop-down lists that already exist do not read the option
            # database again
            try:
                popdown = self.tk.eval(f"ttk::combobox::PopdownWindow {combobox}")
                self.tk.call(f"{popdown}.f.l", "configure",
                             "-background", self.c["input"], "-foreground", self.c["text"],
                             "-selectbackground", self.c["accent"],
                             "-selectforeground", self.c["onAccent"])
            except tk.TclError:
                pass
        self.chart.setTheme(self.c)
        self.processTable.tag_configure("problem", foreground=self.c["danger"])
        self.processTable.tag_configure("proposed", foreground=self.c["accent"])

    def setAppearance(self, appearance: str):
        self.settings["appearance"] = appearance
        theme.saveSettings(self.settings, self.settingsPath)
        self.c = theme.palette(appearance)
        self.applyTheme()
        self.status.set(f"Appearance: {dict(theme.APPEARANCES)[appearance]}")

    def openSettings(self):
        SettingsDialog(self)

    # -------------------------- Info popups -------------------------- #

    def infoButton(self, parent, text: str, title: str = "") -> ttk.Label:
        """A small info badge that opens a box with text when clicked."""
        image = self.rounded.infoImage()
        icon = (ttk.Label(parent, image=image, style="Info.TLabel", cursor="hand2")
                if image is not None else
                ttk.Label(parent, text="(i)", style="Info.TLabel", cursor="hand2"))
        icon.bind("<Button-1>", lambda _: self.toggleInfo(icon, text, title))
        self.infoIcons.add(icon)
        return icon

    def toggleInfo(self, icon, text: str, title: str = ""):
        same = self.infoPopup is not None and self.infoPopup.icon is icon
        self.closeInfo()
        if not same:
            self.infoPopup = InfoPopup(self, icon, text, title)

    def closeInfo(self, _event=None):
        if self.infoPopup is not None:
            self.infoPopup.destroy()
            self.infoPopup = None

    def onAnyClick(self, event):
        # The icon's own binding opens or closes its box
        if self.infoPopup is not None and event.widget not in self.infoIcons:
            self.closeInfo()

    def onEscape(self, _event=None):
        if self.infoPopup is not None:
            self.closeInfo()
        elif self.proposal is not None:
            self.run(self.rejectOptimization)

    # ---------------------------- Helpers ---------------------------- #

    def card(self, parent, title: str | None = None, info: str | None = None,
             expand: bool = False) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=14)
        frame.pack(fill=tk.BOTH if expand else tk.X, expand=expand, pady=(0, 12))
        if title:
            head = ttk.Frame(frame, style="Flat.TFrame")
            head.pack(fill=tk.X, pady=(0, 10))
            ttk.Frame(head, style="TitleBar.TFrame", width=3).pack(
                side=tk.LEFT, fill=tk.Y, pady=3, padx=(0, 8))
            ttk.Label(head, text=title, style="CardTitle.TLabel").pack(side=tk.LEFT)
            if info:
                self.infoButton(head, info, title).pack(side=tk.RIGHT)
        return frame

    def flatRow(self, parent, pady=(0, 0)) -> ttk.Frame:
        row = ttk.Frame(parent, style="Flat.TFrame")
        row.pack(fill=tk.X, pady=pady)
        return row

    def formRow(self, parent, label: str, widget_factory):
        row = self.flatRow(parent, pady=3)
        ttk.Label(row, text=label, style="Field.TLabel", width=14).pack(side=tk.LEFT)
        widget = widget_factory(row)
        widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
        if isinstance(widget, ttk.Combobox):
            self.comboboxes.append(widget)
        return widget

    def scrolledTable(self, parent, expand: bool = False, **options) -> ttk.Treeview:
        """A Treeview with a vertical scrollbar, so it is clear when a list
        holds more rows than it shows. The scrollbar is packed first so it
        always stays visible; columns marked stretch shrink to fit."""
        frame = ttk.Frame(parent, style="Flat.TFrame")
        frame.pack(fill=tk.BOTH if expand else tk.X, expand=expand)
        table = ttk.Treeview(frame, **options)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return table

    # ----------------------------- Layout ---------------------------- #

    def buildHeader(self):
        bar = ttk.Frame(self, style="Header.TFrame", padding=(20, 12))
        bar.pack(side=tk.TOP, fill=tk.X)
        ttk.Frame(bar, style="HeaderMark.TFrame", width=4).pack(side=tk.LEFT, fill=tk.Y,
                                                                 pady=4)
        ttk.Label(bar, text="Schedule optimizer", style="Header.TLabel").pack(
            side=tk.LEFT, padx=(10, 0))
        ttk.Label(bar, text=self.gui.getCompanyName(), style="HeaderMuted.TLabel").pack(
            side=tk.LEFT, padx=(14, 0), pady=(4, 0))

        ttk.Button(bar, text="Settings", style="Header.TButton",
                   command=self.openSettings).pack(side=tk.RIGHT)
        self.date = ttk.Combobox(bar, width=12, state="readonly", style="Header.TCombobox")
        self.date.pack(side=tk.RIGHT, padx=(0, 18))
        ttk.Label(bar, text="Date", style="HeaderMuted.TLabel").pack(side=tk.RIGHT,
                                                                     padx=(14, 6))
        self.horizon = ttk.Combobox(bar, width=6, state="readonly", style="Header.TCombobox")
        self.horizon.pack(side=tk.RIGHT)
        ttk.Label(bar, text="Horizon", style="HeaderMuted.TLabel").pack(side=tk.RIGHT,
                                                                        padx=(0, 6))
        self.comboboxes += [self.date, self.horizon]
        self.horizon.bind("<<ComboboxSelected>>",
                          lambda _: self.run(lambda: self.changeDay(refreshDates=True)))
        self.date.bind("<<ComboboxSelected>>", lambda _: self.run(self.changeDay))

    def buildScrollableSidebar(self, parent) -> ttk.Frame:
        """The left column. If it is taller than the window a scrollbar
        appears; if there is room left over the process list grows."""
        outer = ttk.Frame(parent, style="Root.TFrame", width=SIDEBAR_WIDTH)
        outer.pack(side=tk.LEFT, fill=tk.Y)
        outer.pack_propagate(False)

        canvas = tk.Canvas(outer, bg=self.c["bg"], highlightthickness=0, borderwidth=0)
        self.tkBackgrounds.append((canvas, "bg"))
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview,
                                  style="Root.Vertical.TScrollbar")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        inner = ttk.Frame(canvas, style="Root.TFrame")
        window = canvas.create_window(0, 0, window=inner, anchor=tk.NW)

        def sync(_event=None):
            natural = inner.winfo_reqheight()
            available = canvas.winfo_height()
            canvas.itemconfigure(window, width=canvas.winfo_width(),
                                 height=max(natural, available))
            canvas.configure(scrollregion=(0, 0, canvas.winfo_width(),
                                           max(natural, available)))
            overflow = natural > available + 1
            if overflow and not scrollbar.winfo_ismapped():
                scrollbar.pack(side=tk.RIGHT, fill=tk.Y, before=canvas, padx=(4, 0))
            elif not overflow and scrollbar.winfo_ismapped():
                scrollbar.pack_forget()
                canvas.yview_moveto(0)

        inner.bind("<Configure>", sync)
        canvas.bind("<Configure>", sync)

        def onWheel(event):
            if not scrollbar.winfo_ismapped():
                return
            # Only when the mouse is over the sidebar, and not over a list
            # (lists scroll themselves)
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget is None or isinstance(widget, ttk.Treeview):
                return
            if str(widget) != str(outer) and not str(widget).startswith(str(outer) + "."):
                return
            if event.num in (4, 5):          # Linux
                step = -1 if event.num == 4 else 1
            elif sys.platform == "darwin":
                step = -event.delta
            else:
                step = -event.delta // 120
            canvas.yview_scroll(step, "units")

        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.bind_all(sequence, onWheel, add="+")
        return inner

    def buildMachinePanel(self, parent):
        box = self.card(parent, "Machines")

        # Column widths add up to less than the sidebar, Name stretches
        self.machineTable = self.scrolledTable(box, columns=("name", "kW", "hours"),
                                               show="headings", height=3)
        self.machineTable.heading("name", text="Name", anchor=tk.W)
        self.machineTable.heading("kW", text="kW", anchor=tk.E)
        self.machineTable.heading("hours", text="After hours", anchor=tk.CENTER)
        self.machineTable.column("name", width=110, minwidth=60, anchor=tk.W, stretch=True)
        self.machineTable.column("kW", width=56, minwidth=40, anchor=tk.E, stretch=False)
        self.machineTable.column("hours", width=92, minwidth=80, anchor=tk.CENTER,
                                 stretch=False)
        # Click the After hours box of a machine to switch it
        self.machineTable.bind("<Button-1>", self.onMachineTableClick)

        ttk.Frame(box, style="Flat.TFrame", height=8).pack(fill=tk.X)
        self.machineName = self.formRow(box, "Name", lambda p: ttk.Entry(p))
        self.machineKW = self.formRow(box, "Power (kW)", lambda p: ttk.Entry(p))

        checkRow = self.flatRow(box, pady=(6, 0))
        self.machineOutsideHours = tk.BooleanVar(value=False)
        ttk.Checkbutton(checkRow, text="May run after hours",
                        variable=self.machineOutsideHours,
                        style="Card.TCheckbutton").pack(side=tk.LEFT)
        self.infoButton(checkRow, INFO_AFTER_HOURS, "After hours").pack(side=tk.LEFT,
                                                                        padx=(6, 0))

        buttons = self.flatRow(box, pady=(12, 0))
        ttk.Button(buttons, text="+  Add machine", style="Accent.TButton",
                   command=lambda: self.run(self.addMachine)).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Remove", style="Danger.TButton",
                   command=lambda: self.run(self.removeMachine)).pack(side=tk.RIGHT)

    def buildProcessPanel(self, parent):
        # The form comes first so it is always visible. The process list
        # gets whatever height is left and shrinks on small windows.
        form = self.card(parent, "New process", info=INFO_NEW_PROCESS)
        self.processMachine = self.formRow(
            form, "Machine", lambda p: ttk.Combobox(p, state="readonly"))
        self.processStart = self.formRow(form, "Start (HH:MM)", lambda p: ttk.Entry(p))
        self.processStart.insert(0, "08:00")
        self.processDuration = self.formRow(
            form, "Quarters", lambda p: ttk.Spinbox(p, from_=1, to=QUARTERS_PER_DAY))
        self.processDuration.set(4)
        self.processDeadline = self.formRow(
            form, "Due by", lambda p: ttk.Combobox(
                p, state="readonly", height=12, values=deadlineChoices(),
                postcommand=self.updateDeadlineChoices))
        self.processDeadline.set(NO_DEADLINE)

        ttk.Button(form, text="+  Add process", style="Accent.TButton",
                   command=lambda: self.run(self.addProcess)).pack(anchor=tk.W, pady=(12, 0))
        for widget in (self.processStart, self.processDuration, self.processDeadline):
            widget.bind("<Return>", lambda _: self.run(self.addProcess))

        box = self.card(parent, "Processes", info=INFO_PROCESSES, expand=True)
        # Buttons are packed at the bottom before the table so they never
        # get pushed out when space runs short.
        ruleRow = ttk.Frame(box, style="Flat.TFrame")
        ruleRow.pack(side=tk.BOTTOM, fill=tk.X, pady=(8, 0))
        ttk.Button(ruleRow, text="Depends on…",
                   command=lambda: self.run(self.editDependencies)
                   ).pack(side=tk.LEFT)
        ttk.Button(ruleRow, text="Deadline…",
                   command=lambda: self.run(self.editDeadline)
                   ).pack(side=tk.LEFT, padx=6)

        editRow = ttk.Frame(box, style="Flat.TFrame")
        editRow.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        # Earlier/Later move the selected process 15 min
        ttk.Button(editRow, text="Earlier", style="Small.TButton",
                   command=lambda: self.run(lambda: self.nudgeSelectedProcess(-1))
                   ).pack(side=tk.LEFT)
        ttk.Button(editRow, text="Later", style="Small.TButton",
                   command=lambda: self.run(lambda: self.nudgeSelectedProcess(1))
                   ).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(editRow, text="Remove", style="Danger.TButton",
                   command=lambda: self.run(self.removeSelectedProcess)
                   ).pack(side=tk.RIGHT)

        self.processTable = self.scrolledTable(
            box, expand=True, columns=("nr", "machine", "time", "due", "after"),
            show="headings", height=5, selectmode="browse")
        for column, text, width, stretch in (("nr", "#", 34, False),
                                             ("machine", "Machine", 70, True),
                                             ("time", "Time", 102, False),
                                             ("due", "Due", 50, False),
                                             ("after", "After", 44, True)):
            self.processTable.heading(column, text=text, anchor=tk.W)
            self.processTable.column(column, width=width, minwidth=min(width, 34),
                                     anchor=tk.W, stretch=stretch)
        self.processTable.bind("<<TreeviewSelect>>", self.onTableSelect)
        for key in ("<Delete>", "<BackSpace>"):
            self.processTable.bind(key, lambda _: self.run(self.removeSelectedProcess))

        # Keep the preview block in sync with the form
        self.processMachine.bind("<<ComboboxSelected>>", lambda _: self.plotIfReady())
        self.processDuration.configure(command=self.plotIfReady)

    def buildChartPanel(self, parent):
        # Capacity, optimiser and working hours controls
        tools = ttk.Frame(parent, style="Card.TFrame", padding=(14, 10))
        tools.pack(fill=tk.X)
        self.toolsRow = tools

        optimRow = self.flatRow(tools)
        ttk.Label(optimRow, text="Max cap. (kW)", style="Field.TLabel").pack(
            side=tk.LEFT, padx=(0, 6))
        self.maxCap = ttk.Entry(optimRow, width=8)
        self.maxCap.pack(side=tk.LEFT)
        self.maxCap.bind("<Return>", lambda _: self.run(self.setMaxCapacity))
        ttk.Button(optimRow, text="Set", command=lambda: self.run(self.setMaxCapacity)
                   ).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Button(optimRow, text="Optimize day", style="Accent.TButton",
                   command=lambda: self.run(self.optimizeDay)).pack(side=tk.RIGHT)
        self.infoButton(optimRow, INFO_MAX_SHIFT, "Max shift").pack(side=tk.RIGHT,
                                                                    padx=(0, 12))
        self.optimFlex = ttk.Spinbox(optimRow, from_=0, to=QUARTERS_PER_DAY, width=4)
        self.optimFlex.set(self.gui.getOptimFlex())
        self.optimFlex.pack(side=tk.RIGHT, padx=(0, 6))
        ttk.Label(optimRow, text="Max shift (quarters)", style="Field.TLabel").pack(
            side=tk.RIGHT, padx=(0, 6))

        # Working hours: processes may only run inside them, not during lunch
        hoursRow = self.flatRow(tools, pady=(8, 0))
        hours = self.gui.getWorkingHours()

        def timeEntry(value, padLeft=0):
            entry = ttk.Entry(hoursRow, width=6)
            entry.insert(0, value or "")
            entry.pack(side=tk.LEFT, padx=(padLeft, 0))
            entry.bind("<Return>", lambda _: self.run(self.setWorkingHours))
            return entry

        def label(text, padLeft=0):
            ttk.Label(hoursRow, text=text, style="Field.TLabel").pack(
                side=tk.LEFT, padx=(padLeft, 6))

        label("Working hours")
        self.workStart = timeEntry(hours["start"])
        label("–", 6)
        self.workEnd = timeEntry(hours["end"])
        label("Lunch", 16)
        self.lunchStart = timeEntry(hours["lunchStart"])
        label("–", 6)
        self.lunchEnd = timeEntry(hours["lunchEnd"])
        ttk.Button(hoursRow, text="Set", command=lambda: self.run(self.setWorkingHours)
                   ).pack(side=tk.LEFT, padx=(6, 0))
        self.infoButton(hoursRow, INFO_HOURS, "Working hours").pack(side=tk.LEFT,
                                                                    padx=(8, 0))

        # Shown below the tools while an optimisation proposal waits for
        # Accept or Reject (see showProposalBar)
        self.proposalBar = ttk.Frame(parent, style="Proposal.TFrame", padding=(12, 8))
        ttk.Button(self.proposalBar, text="Reject", style="Proposal.TButton",
                   command=lambda: self.run(self.rejectOptimization)).pack(side=tk.RIGHT)
        ttk.Button(self.proposalBar, text="Accept", style="Success.TButton",
                   command=lambda: self.run(self.acceptOptimization)
                   ).pack(side=tk.RIGHT, padx=(0, 6))
        self.proposalText = tk.StringVar()
        ttk.Label(self.proposalBar, textvariable=self.proposalText,
                  style="Proposal.TLabel").pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Stat tiles with a coloured stripe
        stats = ttk.Frame(parent, style="Root.TFrame")
        stats.pack(fill=tk.X, pady=(12, 0))
        self.statValues: dict[str, tk.StringVar] = {}
        for index, (key, name, _) in enumerate(STAT_TILES):
            tile = ttk.Frame(stats, style="Card.TFrame", padding=(12, 10))
            # fill BOTH: all tiles as tall as the Peak power tile
            tile.pack(side=tk.LEFT, fill=tk.BOTH, expand=True,
                      padx=(0, 0 if index == len(STAT_TILES) - 1 else 10))
            # Coloured bar inside the tile, clear of the rounded corners
            ttk.Frame(tile, style=f"{key}.Stripe.TFrame", width=4).pack(
                side=tk.LEFT, fill=tk.Y, pady=2)
            inner = ttk.Frame(tile, style="Flat.TFrame", padding=(12, 0, 0, 0))
            inner.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            ttk.Label(inner, text=name, style="StatName.TLabel").pack(anchor=tk.W)
            self.statValues[key] = tk.StringVar(value="–")
            ttk.Label(inner, textvariable=self.statValues[key],
                      style="StatValue.TLabel").pack(anchor=tk.W, pady=(2, 0))
            if key == "peak":
                # Change in peak power of a proposed or accepted optimisation
                self.peakChange = tk.StringVar(value=" ")
                self.peakChangeLabel = ttk.Label(inner, textvariable=self.peakChange,
                                                 style="StatName.TLabel")
                self.peakChangeLabel.pack(anchor=tk.W)

        chartCard = self.card(parent, "Power over the day", info=INFO_CHART,
                              expand=True)
        chartCard.pack_configure(pady=(12, 0))
        self.chart = PowerChart(chartCard, onClick=self.onChartClick,
                                onHover=self.onChartHover,
                                onSelect=self.selectProcess,
                                onMove=lambda pid, start: self.run(
                                    lambda: self.moveProcess(pid, start)),
                                onRemove=lambda pid: self.run(
                                    lambda: self.removeProcess(pid)))
        self.chart.pack(fill=tk.BOTH, expand=True)

        self.cursorText = tk.StringVar(value="Hover the chart to inspect a quarter")
        ttk.Label(parent, textvariable=self.cursorText,
                  style="Cursor.TLabel").pack(anchor=tk.W, pady=(6, 0))

    # ---------------------------- Actions ---------------------------- #

    def run(self, action):
        """Runs a GUI action and shows any backend error instead of crashing."""
        try:
            action()
        except Exception as error:
            self.status.set(f"Error: {error}")
            messagebox.showerror("Error", str(error))

    def loadAreaData(self):
        self.gui.loadAreaData()
        horizons = self.gui.getAvailableHorizons()
        self.horizon["values"] = horizons
        if horizons:
            self.horizon.set(horizons[0])
            self.refreshDates()
        self.status.set("Area data loaded")

    def refreshDates(self):
        dates = self.gui.getAvailableDates(self.horizon.get())
        self.date["values"] = dates
        if dates and self.date.get() not in dates:
            self.date.set(dates[0])

    def refreshMachines(self):
        selected = self.machineTable.selection()
        self.machineTable.delete(*self.machineTable.get_children())
        machines = self.gui.getMachines()
        for m in machines:
            self.machineTable.insert("", tk.END, iid=m["name"], values=(
                m["name"], f"{m['kW']:g}", "Yes" if m["allowOutsideHours"] else "No"))
            self.colorFor(m["name"])
        kept = [name for name in selected if self.machineTable.exists(name)]
        if kept:
            self.machineTable.selection_set(kept)
        names = [m["name"] for m in machines]
        self.processMachine["values"] = names
        if names and self.processMachine.get() not in names:
            self.processMachine.set(names[0])

    def refreshProcesses(self):
        """Fills the process list. While a proposal is shown, processes it
        would move show 'now → proposed' start and are blue. Processes that
        break a rule (hours, deadline, machine busy) are red."""
        proposal = (self.gui.getOptimizationPreview(self.date.get(), self.horizon.get())
                    if self.date.get() else None)
        proposedStart = {b["id"]: b["startTime"] for b in (proposal or {}).get("blocks", [])}
        self.processTable.delete(*self.processTable.get_children())
        for b in self.gui.getProcessBlocks():
            after = ", ".join(f"#{d + 1}" for d in b["dependsOn"]) or "–"
            if b["id"] in proposedStart:
                time, tags = f"{b['startTime']} → {proposedStart[b['id']]}", ("proposed",)
            else:
                time = f"{b['startTime']} – {b['endTime']}"
                tags = ("problem",) if PowerChart.breaksARule(b) else ()
            self.processTable.insert("", tk.END, iid=str(b["id"]), values=(
                f"#{b['id'] + 1}", b["machine"], time, b["deadline"] or "–", after),
                tags=tags)
        self.processTable.tag_configure("problem", foreground=self.c["danger"])
        self.processTable.tag_configure("proposed", foreground=self.c["accent"])

    def updateDeadlineChoices(self):
        """Before the Due by list opens: only offer times after the end of
        the process as it is set in the form."""
        try:
            end = (self.gui.timeToIndex(self.processStart.get())
                   + int(self.processDuration.get()))
        except (ValueError, TypeError):
            end = 1
        self.processDeadline["values"] = deadlineChoices(end)

    def addMachine(self):
        name = self.machineName.get().strip()
        if not name:
            raise ValueError("Give the machine a name")
        allowOutside = self.machineOutsideHours.get()
        self.gui.addMachine(name, float(self.machineKW.get()), allowOutside)
        self.machineName.delete(0, tk.END)
        self.machineKW.delete(0, tk.END)
        self.machineOutsideHours.set(False)
        self.refreshMachines()
        self.status.set(f"Added machine {name}"
                        + (" (may run after hours)" if allowOutside else ""))
        self.plotIfReady()

    def onMachineTableClick(self, event):
        """A click on the After hours box of a machine switches it."""
        table = self.machineTable
        if table.identify_region(event.x, event.y) != "cell":
            return
        if table.identify_column(event.x) != "#3":
            return
        name = table.identify_row(event.y)
        if name:
            self.run(lambda: self.toggleOutsideHours(name))

    def toggleOutsideHours(self, name: str):
        allowed = not self.gui.getMachine(name)["allowOutsideHours"]
        outside = self.gui.setMachineAllowOutsideHours(name, allowed)
        self.refreshMachines()
        self.machineTable.selection_set(name)
        self.refreshProcesses()
        self.plotIfReady()
        if allowed:
            text = (f"{name} may now run through lunch and after closing "
                    "(it still has to start within the working hours)")
        else:
            text = f"{name} now has to stay within the working hours"
        if outside:
            text += ("  ·  Outside the hours: " + ", ".join(f"#{i + 1}" for i in outside)
                     + " (move them or press Optimize day)")
        self.status.set(text)

    def removeMachine(self):
        selected = self.machineTable.selection()
        if not selected:
            raise ValueError("Select a machine first")
        self.gui.removeMachine(selected[0])
        self.refreshMachines()
        self.refreshProcesses()
        self.status.set(f"Removed machine {selected[0]}")
        self.plotIfReady()

    def addProcess(self):
        machineName = self.processMachine.get()
        if not machineName:
            raise ValueError("Add a machine first")
        startIndex = self.gui.timeToIndex(self.processStart.get())
        deadlineText = parseDeadline(self.processDeadline.get())
        deadline = self.gui.timeToIndex(deadlineText) if deadlineText else None
        self.gui.addProcess(machineName, int(self.processDuration.get()), startIndex,
                            deadline)
        self.previewIndex = None
        self.refreshProcesses()
        text = f"Added process on {machineName} at {quarterToLabel(startIndex)}"
        if deadline is not None:
            text += f", due by {quarterToLabel(deadline)}"
        self.status.set(text)
        self.plotIfReady()

    def selectedProcessId(self) -> int:
        selected = self.processTable.selection()
        if not selected:
            raise ValueError("Select a process first")
        return int(selected[0])

    def selectProcess(self, processId: int | None):
        """Selects a process in both the table and the chart."""
        if processId is None:
            self.processTable.selection_remove(self.processTable.selection())
        elif self.processTable.exists(str(processId)):
            self.processTable.selection_set(str(processId))
            self.processTable.see(str(processId))
        self.chart.setSelected(processId)

    def onTableSelect(self, _event):
        selected = self.processTable.selection()
        self.chart.setSelected(int(selected[0]) if selected else None)

    def moveProcess(self, processId: int, newStartIndex: int):
        try:
            block = self.gui.moveProcess(processId, newStartIndex)
        finally:
            self.refreshProcesses()
            self.plotIfReady()
        self.selectProcess(block["id"])
        self.status.set(f"Moved {block['machine']} to {block['startTime']}–{block['endTime']}")

    def nudgeSelectedProcess(self, quarters: int):
        processId = self.selectedProcessId()
        block = next(b for b in self.gui.getProcessBlocks() if b["id"] == processId)
        self.moveProcess(processId, block["startIndex"] + quarters)

    def removeProcess(self, processId: int):
        block = next(b for b in self.gui.getProcessBlocks() if b["id"] == processId)
        self.gui.removeProcess(processId)
        self.refreshProcesses()
        self.plotIfReady()
        self.status.set(f"Removed {block['machine']} ({block['startTime']}–{block['endTime']})")

    def editDependencies(self):
        processId = self.selectedProcessId()
        blocks = self.gui.getProcessBlocks()
        chosen = DependencyDialog(self, processId, blocks).result
        if chosen is None:
            return
        moved = self.gui.setProcessDependencies(processId, chosen)
        self.refreshProcesses()
        self.plotIfReady()
        self.selectProcess(processId)
        text = (f"#{processId + 1} waits for " + ", ".join(f"#{d + 1}" for d in chosen)
                if chosen else f"#{processId + 1} is independent")
        if moved:
            text += ". Pushed later: " + ", ".join(f"#{m + 1}" for m in moved)
        self.status.set(text)

    def editDeadline(self):
        processId = self.selectedProcessId()
        block = next(b for b in self.gui.getProcessBlocks() if b["id"] == processId)
        dialog = DeadlineDialog(self, processId, block)
        if dialog.cancelled:
            return
        block = self.gui.setProcessDeadline(processId, dialog.result)
        self.refreshProcesses()
        self.plotIfReady()
        self.selectProcess(processId)
        if block["deadline"] is None:
            self.status.set(f"#{processId + 1} has no deadline")
        elif block["lateForDeadline"]:
            self.status.set(f"#{processId + 1} is due by {block['deadline']} but ends at "
                            f"{block['endTime']}: move it earlier or press Optimize day")
        else:
            self.status.set(f"#{processId + 1} is due by {block['deadline']}")

    def removeSelectedProcess(self):
        self.removeProcess(self.selectedProcessId())

    def setMaxCapacity(self):
        text = self.maxCap.get().strip()
        self.gui.setMaxCapacity(float(text) if text else None)
        self.status.set("Max capacity set")
        self.plotIfReady()

    def setWorkingHours(self):
        def value(entry):
            return entry.get().strip() or None
        start, end = value(self.workStart), value(self.workEnd)
        if start is None or end is None:
            raise ValueError("Give both a start and an end time")
        outside = self.gui.setWorkingHours(start, end, value(self.lunchStart),
                                           value(self.lunchEnd))
        self.refreshProcesses()
        self.plotIfReady()
        hours = self.gui.getWorkingHours()
        text = f"Working hours {hours['start']}–{hours['end']}"
        if hours["lunchStart"]:
            text += f", lunch {hours['lunchStart']}–{hours['lunchEnd']}"
        if outside:
            text += ("  ·  Outside the hours: " + ", ".join(f"#{i + 1}" for i in outside)
                     + " (move them or press Optimize day)")
        self.status.set(text)

    # --------------------- Optimisation proposal --------------------- #
    # Optimize day -> a proposal (ghosts in the chart, nothing moves)
    #   Accept -> the processes move to the proposal
    #   Reject (or Esc) -> the proposal is thrown away
    # Every proposal is made from the real schedule, so pressing Optimize
    # day again never moves a process further than the max shift.

    def optimizeDay(self):
        try:
            self.proposeOptimization()
        finally:
            self.configure(cursor="")

    def proposeOptimization(self):
        date, horizon = self.date.get(), self.horizon.get()
        if not date:
            raise ValueError("Pick a date first")
        if not self.gui.getProcessBlocks():
            raise ValueError("Add a process first")
        flex = int(self.optimFlex.get())
        self.gui.setOptimFlex(flex)
        self.previewIndex = None
        # Solving takes up to a second: show that something is happening
        self.status.set(f"Optimizing {date}…")
        self.configure(cursor="watch")
        self.update_idletasks()
        try:
            proposal = self.gui.previewOptimization(date, horizon)
        except Exception:
            # Don't leave an older proposal on show next to the error
            self.gui.rejectOptimization()
            self.proposal = None
            self.refreshProcesses()
            self.plot()
            raise
        if not proposal["blocks"]:
            self.gui.rejectOptimization()
            self.proposal = None
            self.refreshProcesses()
            self.plot()
            self.status.set(f"No better schedule for {date} within a shift of {flex} "
                            "quarters, nothing would move")
            return
        self.proposal = proposal
        self.refreshProcesses()
        self.plot()
        self.status.set(f"{self.proposalSummary(proposal)}. Accept to apply it, "
                        "Reject to keep the schedule as it is.")

    def acceptOptimization(self):
        result = self.gui.acceptOptimization()
        self.proposal = None
        self.applied = {"key": self.scheduleKey(self.gui.getProcessBlocks()),
                        "reductionKW": result["peakReductionKW"]}
        self.refreshProcesses()
        self.plot()
        self.status.set(f"Applied: {self.proposalSummary(result)}")

    def rejectOptimization(self):
        self.gui.rejectOptimization()
        self.proposal = None
        self.refreshProcesses()
        self.plot()
        self.status.set("Proposal rejected, the schedule is unchanged")

    @staticmethod
    def proposalSummary(proposal: dict) -> str:
        moved = len(proposal["blocks"])
        before, after = proposal["before"], proposal["after"]
        return (f"{moved} process{'es' if moved != 1 else ''} moved, peak "
                f"{before['peakTotalKW']:.1f} kW at {before['peakTime']} → "
                f"{after['peakTotalKW']:.1f} kW at {after['peakTime']}")

    def showProposalBar(self):
        if self.proposal is None:
            self.proposalBar.pack_forget()
            return
        moved = len(self.proposal["blocks"])
        before = self.proposal["before"]["peakTotalKW"]
        after = self.proposal["after"]["peakTotalKW"]
        self.proposalText.set(
            f"Proposal: {moved} process{'es' if moved != 1 else ''} would move "
            f"(dashed outlines), peak {before:.1f} → {after:.1f} kW")
        if not self.proposalBar.winfo_manager():
            self.proposalBar.pack(fill=tk.X, pady=(10, 0), after=self.toolsRow)

    def scheduleKey(self, blocks: list[dict]) -> tuple:
        """Identifies the day and every start, to tell if the schedule has
        changed since a proposal was accepted."""
        return (self.date.get(), self.horizon.get(),
                tuple((b["id"], b["machine"], b["kW"], b["startIndex"], b["endIndex"])
                      for b in sorted(blocks, key=lambda b: b["id"])))

    def changeDay(self, refreshDates: bool = False):
        """A proposal is made for one day, a new date or horizon drops it."""
        self.gui.rejectOptimization()
        if refreshDates:
            self.refreshDates()
        self.refreshProcesses()
        self.plot()

    def plotIfReady(self):
        if self.date.get():
            self.run(self.plot)

    # ----------------------------- Chart ----------------------------- #

    def colorFor(self, machineName: str) -> str:
        if machineName not in self.machineColors:
            index = len(self.machineColors) % len(theme.PROCESS_COLORS)
            self.machineColors[machineName] = theme.PROCESS_COLORS[index]
        return self.machineColors[machineName]

    def plot(self):
        date, horizon = self.date.get(), self.horizon.get()
        rows = self.gui.getCombinedProfile(date, horizon)
        blocks = self.gui.getProcessBlocks()
        # The backend drops a proposal as soon as the schedule changes
        proposal = self.gui.getOptimizationPreview(date, horizon)
        dropped = self.proposal is not None and proposal is None
        self.proposal = proposal
        self.chart.setData(rows, blocks,
                           self.gui.getMaxCapacity(), self.previewBlock(),
                           self.colorFor, self.gui.getWorkingHours(),
                           ghosts=proposal["blocks"] if proposal else None)
        self.showProposalBar()
        self.updateStats(date, horizon, blocks)
        self.status.set(f"Showing {date} ({horizon})")
        if dropped:
            # after_idle: append to the message the calling action sets
            self.after_idle(lambda: self.status.set(
                self.status.get() + "  ·  Optimisation proposal discarded"))

    def previewBlock(self) -> dict | None:
        """The process that would be added at the clicked quarter."""
        if self.previewIndex is None or not self.processMachine.get():
            return None
        try:
            machine = self.gui.getMachine(self.processMachine.get())
            duration = int(self.processDuration.get())
        except (KeyError, ValueError):
            return None
        return {"name": machine["name"], "kW": machine["kW"],
                "startIndex": self.previewIndex,
                "endIndex": self.previewIndex + duration}

    def updateStats(self, date: str, horizon: str, blocks: list[dict]):
        s = self.gui.getDaySummary(date, horizon)
        self.statValues["peak"].set(f"{s['peakTotalKW']:.1f} kW")
        self.statValues["peakTime"].set(s["peakTime"])
        self.statValues["own"].set(f"{s['privateEnergyKWh']:.0f} kWh")
        self.statValues["over"].set(str(s["violationCount"]))

        # The card always shows the real peak. Below it: the reduction the
        # proposal would give, or the one the accepted proposal gave as long
        # as the schedule is still the accepted one.
        if self.proposal is not None:
            text, style = peakChangeText(self.proposal["peakReductionKW"], proposed=True)
        elif self.applied is not None and self.applied["key"] == self.scheduleKey(blocks):
            text, style = peakChangeText(self.applied["reductionKW"], proposed=False)
        else:
            self.applied = None
            text, style = " ", "StatName.TLabel"
        self.peakChange.set(text)
        self.peakChangeLabel.configure(style=style)

    def onChartHover(self, row: dict | None):
        if row is None:
            self.cursorText.set("Hover the chart to inspect a quarter")
            return
        self.cursorText.set(
            f"{quarterToLabel(row['index'])}–{quarterToLabel(row['index'] + 1)}    "
            f"Area {row['areaKW']:.1f} kW    Own {row['privateKW']:g} kW    "
            f"Total {row['totalKW']:.1f} kW")

    def onChartClick(self, quarter: int):
        """Click a quarter to use it as the start time of the next process."""
        self.selectProcess(None)
        self.previewIndex = quarter
        self.processStart.delete(0, tk.END)
        self.processStart.insert(0, quarterToLabel(quarter))
        self.plotIfReady()


class InfoPopup(tk.Toplevel):
    """A small borderless box with help text, shown below its info badge."""

    def __init__(self, app: App, icon: tk.Widget, text: str, title: str = ""):
        super().__init__(app)
        self.icon = icon
        c = app.c
        self.withdraw()
        if sys.platform == "darwin":
            try:   # a borderless help window that stays above the app
                self.tk.call("::tk::unsupported::MacWindowStyle", "style",
                             self._w, "help", "none")
            except tk.TclError:
                self.overrideredirect(True)
        else:
            self.overrideredirect(True)
        self.attributes("-topmost", True)

        # Rounded box drawn on a canvas. Its corners need a see-through
        # window (macOS, Windows); elsewhere the corners show the card colour.
        clear = self.transparentColor()
        canvas = tk.Canvas(self, bg=clear or c["card"], highlightthickness=0,
                           borderwidth=0)
        canvas.pack()
        pad, y = 14, 12
        if title:
            titleId = canvas.create_text(pad, y, text=title, anchor=tk.NW,
                                         fill=c["accent"], font=FONT_BOLD)
            y = canvas.bbox(titleId)[3] + 4
        textId = canvas.create_text(pad, y, text=text, anchor=tk.NW, width=280,
                                    fill=c["text"], font=FONT_SMALL)
        x1, y1 = canvas.bbox(textId)[2:]
        w, h = max(x1, 120) + pad, y1 + 12
        canvas.configure(width=w, height=h)
        shape = self.roundedRect(canvas, 0.5, 0.5, w - 0.5, h - 0.5, 10,
                                 fill=c["card"], outline=c["accent"], width=1)
        canvas.tag_lower(shape)
        canvas.bind("<Button-1>", lambda _: app.closeInfo())
        self.bind("<Button-1>", lambda _: app.closeInfo())

        self.update_idletasks()
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        x = icon.winfo_rootx() + icon.winfo_width() // 2 - 24
        x = max(8, min(x, icon.winfo_screenwidth() - width - 8))
        y = icon.winfo_rooty() + icon.winfo_height() + 6
        if y + height > icon.winfo_screenheight() - 8:
            y = icon.winfo_rooty() - height - 6
        self.geometry(f"+{x}+{y}")
        self.deiconify()
        self.lift()

    def transparentColor(self) -> str | None:
        """Makes the window background see-through, returns the colour to
        paint for 'nothing'. None where that is not supported."""
        try:
            if sys.platform == "darwin":
                self.attributes("-transparent", True)
                self.configure(bg="systemTransparent")
                return "systemTransparent"
            if sys.platform.startswith("win"):
                key = "#010203"
                self.configure(bg=key)
                self.attributes("-transparentcolor", key)
                return key
        except tk.TclError:
            pass
        return None

    @staticmethod
    def roundedRect(canvas, x0, y0, x1, y1, r, **options):
        """A rounded rectangle as a smoothed canvas polygon."""
        points = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
                  x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return canvas.create_polygon(points, smooth=True, splinesteps=24, **options)


class Dialog(tk.Toplevel):
    """A small modal window in the app's colours."""

    def __init__(self, app: App, title: str):
        super().__init__(app)
        self.app = app
        self.title(title)
        self.configure(bg=app.c["card"])
        self.resizable(False, False)
        self.transient(app)
        self.box = ttk.Frame(self, style="Flat.TFrame", padding=20)
        self.box.pack(fill=tk.BOTH, expand=True)

    def addButtons(self, okText: str, onOk):
        buttons = ttk.Frame(self.box, style="Flat.TFrame")
        buttons.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(buttons, text=okText, style="Accent.TButton",
                   command=onOk).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancel", command=self.destroy
                   ).pack(side=tk.RIGHT, padx=6)
        self.bind("<Return>", lambda _: onOk())
        self.bind("<Escape>", lambda _: self.destroy())

    def showModal(self):
        self.update_idletasks()
        self.geometry(f"+{self.app.winfo_rootx() + 140}+{self.app.winfo_rooty() + 120}")
        self.grab_set()
        self.focus_set()
        self.wait_window()


class DependencyDialog(Dialog):
    """Pick which processes the given process has to wait for.
    result is the chosen list of ids, or None if cancelled."""

    def __init__(self, parent: App, processId: int, blocks: list[dict]):
        super().__init__(parent, f"Dependencies of #{processId + 1}")
        self.result: list[int] | None = None
        box = self.box

        byId = {b["id"]: b for b in blocks}
        current = byId[processId]
        ttk.Label(box, text=f"#{processId + 1} {current['machine']} "
                            f"({current['startTime']}–{current['endTime']})",
                  style="CardTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(box, text="may only start after these are finished:",
                  style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 10))

        self.choices: dict[int, tk.BooleanVar] = {}
        others = sorted((b for b in blocks if b["id"] != processId),
                        key=lambda b: b["id"])
        if not others:
            ttk.Label(box, text="There are no other processes.",
                      style="Muted.TLabel").pack(anchor=tk.W)
        for b in others:
            var = tk.BooleanVar(value=b["id"] in current["dependsOn"])
            # b cannot be a dependency if b already waits for this process
            cycle = self.waitsFor(byId, b["id"], processId)
            label = (f"#{b['id'] + 1}  {b['machine']}  "
                     f"{b['startTime']}–{b['endTime']}")
            if cycle:
                label += "  (waits for this one)"
            ttk.Checkbutton(box, text=label, variable=var, style="Card.TCheckbutton",
                            state=tk.DISABLED if cycle else tk.NORMAL
                            ).pack(anchor=tk.W, pady=2)
            self.choices[b["id"]] = var

        ttk.Label(box, text="Processes that would start too early are moved later.",
                  style="Muted.TLabel").pack(anchor=tk.W, pady=(10, 0))
        self.addButtons("Save", self.save)
        self.showModal()

    @staticmethod
    def waitsFor(byId: dict, startId: int, targetId: int) -> bool:
        stack, seen = list(byId[startId]["dependsOn"]), set()
        while stack:
            current = stack.pop()
            if current == targetId:
                return True
            if current not in seen:
                seen.add(current)
                stack.extend(byId[current]["dependsOn"])
        return False

    def save(self):
        self.result = [pid for pid, var in self.choices.items() if var.get()]
        self.destroy()


class DeadlineDialog(Dialog):
    """Pick the deadline of a process from a drop-down list.
    cancelled is True if the dialog was closed without saving, otherwise
    result is 'HH:MM' or None for no deadline."""

    def __init__(self, parent: App, processId: int, block: dict):
        super().__init__(parent, f"Deadline of #{processId + 1}")
        self.cancelled = True
        self.result: str | None = None
        box = self.box
        ttk.Label(box, text=f"#{processId + 1} {block['machine']} "
                            f"({block['startTime']}–{block['endTime']})",
                  style="CardTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(box, text="has to be finished by:",
                  style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 10))
        duration = block["endIndex"] - block["startIndex"]
        self.choice = ttk.Combobox(box, state="readonly", height=12, width=16,
                                   values=deadlineChoices(duration))
        self.choice.set(block["deadline"] or NO_DEADLINE)
        self.choice.pack(anchor=tk.W)
        ttk.Label(box, text="A deadline the process already misses is shown in red\n"
                            "until it is moved earlier.",
                  style="Muted.TLabel", justify=tk.LEFT).pack(anchor=tk.W, pady=(10, 0))
        self.addButtons("Save", self.save)
        self.showModal()

    def save(self):
        self.result = parseDeadline(self.choice.get())
        self.cancelled = False
        self.destroy()


class SettingsDialog(Dialog):
    """Appearance: light, dark or follow the system. Applied at once."""

    def __init__(self, parent: App):
        super().__init__(parent, "Settings")
        box = self.box
        ttk.Label(box, text="Appearance", style="CardTitle.TLabel").pack(anchor=tk.W)
        ttk.Label(box, text="Light or dark mode, or follow the system setting.",
                  style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 10))
        self.appearance = tk.StringVar(value=parent.settings["appearance"])
        for value, label in theme.APPEARANCES:
            ttk.Radiobutton(box, text=label, value=value, variable=self.appearance,
                            style="Card.TRadiobutton", command=self.apply
                            ).pack(anchor=tk.W, pady=3)
        buttons = ttk.Frame(box, style="Flat.TFrame")
        buttons.pack(fill=tk.X, pady=(16, 0))
        ttk.Button(buttons, text="Close", style="Accent.TButton",
                   command=self.destroy).pack(side=tk.RIGHT)
        self.bind("<Return>", lambda _: self.destroy())
        self.bind("<Escape>", lambda _: self.destroy())
        self.showModal()

    def apply(self):
        self.app.setAppearance(self.appearance.get())
        self.configure(bg=self.app.c["card"])


if __name__ == "__main__":
    App(GUIinstance("ABB")).mainloop()
