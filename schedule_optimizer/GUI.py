import sys
import tkinter as tk
from tkinter import ttk, messagebox

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

QUARTERS_PER_DAY = 96

# ----------------------------- Colours ------------------------------- #
BG = "#f4f5f7"
CARD = "#ffffff"
BORDER = "#dfe2e7"
TEXT = "#1f2430"
MUTED = "#6b7280"
ACCENT = "#2f6fde"
PROCESS_COLORS = ["#2f6fde", "#e8833a", "#2e9e6a", "#9b59b6",
                  "#d64545", "#1aa3a3", "#c2a01f", "#7a8899"]
FONT = ("Helvetica", 12)
FONT_SMALL = ("Helvetica", 11)
FONT_BOLD = ("Helvetica", 12, "bold")
FONT_TITLE = ("Helvetica", 16, "bold")
FONT_STAT = ("Helvetica", 18, "bold")


class App(tk.Tk):

    def __init__(self, gui: GUIinstance):
        super().__init__()
        self.gui = gui
        self.title(f"Schedule optimizer – {gui.getCompanyName()}")
        self.geometry("1280x760")
        self.minsize(1000, 620)
        self.configure(bg=BG)
        self.setupStyle()

        self.machineColors: dict[str, str] = {}
        self.previewIndex: int | None = None

        root = ttk.Frame(self, style="Root.TFrame", padding=16)
        root.pack(fill=tk.BOTH, expand=True)

        sidebar = self.buildScrollableSidebar(root)
        main = ttk.Frame(root, style="Root.TFrame")
        main.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(16, 0))

        self.buildMachinePanel(sidebar)
        self.buildProcessPanel(sidebar)
        self.buildChartPanel(main)

        self.status = tk.StringVar(value="Ready")
        ttk.Label(self, textvariable=self.status, style="Status.TLabel",
                  anchor=tk.W, padding=(16, 4)).pack(side=tk.BOTTOM, fill=tk.X)

        self.run(self.loadAreaData)
        self.refreshMachines()
        self.refreshProcesses()
        self.plotIfReady()

    # ----------------------------- Style ----------------------------- #

    def setupStyle(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(".", background=BG, foreground=TEXT, font=FONT)
        style.configure("Root.TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="solid",
                        borderwidth=1, bordercolor=BORDER)
        style.configure("Card.TLabel", background=CARD, foreground=TEXT)
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT,
                        font=FONT_BOLD)
        style.configure("Muted.TLabel", background=CARD, foreground=MUTED,
                        font=FONT_SMALL)
        style.configure("Title.TLabel", background=BG, font=FONT_TITLE)
        style.configure("Status.TLabel", background=CARD, foreground=MUTED,
                        font=FONT_SMALL)
        style.configure("StatValue.TLabel", background=CARD, font=FONT_STAT)
        style.configure("StatName.TLabel", background=CARD, foreground=MUTED,
                        font=FONT_SMALL)
        style.configure("Cursor.TLabel", background=BG, foreground=MUTED,
                        font=FONT_SMALL)

        style.configure("Card.TCheckbutton", background=CARD, foreground=TEXT)
        style.map("Card.TCheckbutton", background=[("active", CARD)])

        style.configure("Vertical.TScrollbar", background=BG, troughcolor=CARD,
                        bordercolor=BORDER, arrowcolor=MUTED, lightcolor=BG,
                        darkcolor=BG, gripcount=0)
        style.map("Vertical.TScrollbar", background=[("active", BORDER)])

        style.configure("TButton", padding=(10, 5), background=CARD,
                        bordercolor=BORDER, focuscolor=CARD)
        style.map("TButton", background=[("active", "#eef1f5")])
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        bordercolor=ACCENT, focuscolor=ACCENT)
        style.map("Accent.TButton", background=[("active", "#285fc0")])

        # insertcolor/insertwidth: clam leaves the text cursor colour empty,
        # so set it explicitly to get a visible, blinking cursor.
        for widget in ("TEntry", "TCombobox", "TSpinbox"):
            style.configure(widget, fieldbackground=CARD, bordercolor=BORDER,
                            padding=4, insertcolor=TEXT, insertwidth=1)
        style.map("TEntry", bordercolor=[("focus", ACCENT)])
        style.map("TSpinbox", bordercolor=[("focus", ACCENT)])
        style.configure("Treeview", background=CARD, fieldbackground=CARD,
                        bordercolor=BORDER, rowheight=26, font=FONT_SMALL)
        style.configure("Treeview.Heading", background=BG, foreground=MUTED,
                        font=FONT_SMALL, relief="flat")
        style.map("Treeview", background=[("selected", "#dbe6fb")],
                  foreground=[("selected", TEXT)])

    def card(self, parent, title: str, expand: bool = False) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=12)
        frame.pack(fill=tk.BOTH if expand else tk.X, expand=expand, pady=(0, 12))
        ttk.Label(frame, text=title, style="CardTitle.TLabel").pack(anchor=tk.W, pady=(0, 8))
        return frame

    def formRow(self, parent, label: str, widget_factory):
        row = ttk.Frame(parent, style="Card.TFrame", padding=0, borderwidth=0)
        row.configure(relief="flat")
        row.pack(fill=tk.X, pady=2)
        ttk.Label(row, text=label, style="Muted.TLabel", width=14).pack(side=tk.LEFT)
        widget = widget_factory(row)
        widget.pack(side=tk.LEFT, fill=tk.X, expand=True)
        return widget

    def scrolledTable(self, parent, expand: bool = False, **options) -> ttk.Treeview:
        """A Treeview with a vertical scrollbar, so it is clear when a list
        holds more rows than it shows."""
        frame = ttk.Frame(parent, style="Card.TFrame", borderwidth=0)
        frame.configure(relief="flat")
        frame.pack(fill=tk.BOTH if expand else tk.X, expand=expand)
        table = ttk.Treeview(frame, **options)
        scrollbar = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=table.yview)
        table.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        return table

    # ----------------------------- Layout ---------------------------- #

    def buildScrollableSidebar(self, parent) -> ttk.Frame:
        """The left column. If it is taller than the window a scrollbar
        appears; if there is room left over the process list grows."""
        outer = ttk.Frame(parent, style="Root.TFrame", width=340)
        outer.pack(side=tk.LEFT, fill=tk.Y)
        outer.pack_propagate(False)

        canvas = tk.Canvas(outer, bg=BG, highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(outer, orient=tk.VERTICAL, command=canvas.yview)
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

        self.machineTable = self.scrolledTable(box, columns=("name", "kW"),
                                               show="headings", height=3)
        self.machineTable.heading("name", text="Name", anchor=tk.W)
        self.machineTable.heading("kW", text="kW", anchor=tk.E)
        self.machineTable.column("name", anchor=tk.W)
        self.machineTable.column("kW", width=70, anchor=tk.E, stretch=False)

        self.machineName = self.formRow(box, "Name", lambda p: ttk.Entry(p))
        self.machineKW = self.formRow(box, "Power (kW)", lambda p: ttk.Entry(p))

        buttons = ttk.Frame(box, style="Card.TFrame", borderwidth=0)
        buttons.configure(relief="flat")
        buttons.pack(fill=tk.X, pady=(8, 0))
        ttk.Button(buttons, text="Add machine", style="Accent.TButton",
                   command=lambda: self.run(self.addMachine)).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Remove",
                   command=lambda: self.run(self.removeMachine)).pack(side=tk.LEFT, padx=6)

    def buildProcessPanel(self, parent):
        # The form comes first so it is always visible. The process list
        # gets whatever height is left and shrinks on small windows.
        form = self.card(parent, "New process")
        self.processMachine = self.formRow(
            form, "Machine", lambda p: ttk.Combobox(p, state="readonly"))
        self.processStart = self.formRow(form, "Start (HH:MM)", lambda p: ttk.Entry(p))
        self.processStart.insert(0, "08:00")
        self.processDuration = self.formRow(
            form, "Quarters", lambda p: ttk.Spinbox(p, from_=1, to=QUARTERS_PER_DAY))
        self.processDuration.set(4)

        ttk.Label(form, text="Click the chart to pick a start time.",
                  style="Muted.TLabel").pack(anchor=tk.W, pady=(4, 0))
        ttk.Button(form, text="Add process", style="Accent.TButton",
                   command=lambda: self.run(self.addProcess)).pack(anchor=tk.W, pady=(8, 0))
        for widget in (self.processStart, self.processDuration):
            widget.bind("<Return>", lambda _: self.run(self.addProcess))

        box = self.card(parent, "Processes", expand=True)
        # Buttons are packed at the bottom before the table so they never
        # get pushed out when space runs short.
        editRow = ttk.Frame(box, style="Card.TFrame", borderwidth=0)
        editRow.configure(relief="flat")
        editRow.pack(side=tk.BOTTOM, fill=tk.X, pady=(6, 0))
        # ◀/▶ move the selected process 15 min
        ttk.Button(editRow, text="◀", width=2,
                   command=lambda: self.run(lambda: self.nudgeSelectedProcess(-1))
                   ).pack(side=tk.LEFT)
        ttk.Button(editRow, text="▶", width=2,
                   command=lambda: self.run(lambda: self.nudgeSelectedProcess(1))
                   ).pack(side=tk.LEFT, padx=(4, 0))
        ttk.Button(editRow, text="Remove",
                   command=lambda: self.run(self.removeSelectedProcess)
                   ).pack(side=tk.RIGHT)
        ttk.Button(editRow, text="Depends on…",
                   command=lambda: self.run(self.editDependencies)
                   ).pack(side=tk.RIGHT, padx=6)

        self.processTable = self.scrolledTable(
            box, expand=True, columns=("nr", "machine", "time", "after"),
            show="headings", height=5, selectmode="browse")
        self.processTable.heading("nr", text="#", anchor=tk.W)
        self.processTable.heading("machine", text="Machine", anchor=tk.W)
        self.processTable.heading("time", text="Time", anchor=tk.W)
        self.processTable.heading("after", text="After", anchor=tk.W)
        self.processTable.column("nr", width=34, anchor=tk.W, stretch=False)
        self.processTable.column("machine", width=70, anchor=tk.W)
        self.processTable.column("time", width=100, anchor=tk.W, stretch=False)
        self.processTable.column("after", width=50, anchor=tk.W)
        self.processTable.bind("<<TreeviewSelect>>", self.onTableSelect)
        for key in ("<Delete>", "<BackSpace>"):
            self.processTable.bind(key, lambda _: self.run(self.removeSelectedProcess))

        # Keep the preview block in sync with the form
        self.processMachine.bind("<<ComboboxSelected>>", lambda _: self.plotIfReady())
        self.processDuration.configure(command=self.plotIfReady)

    def buildChartPanel(self, parent):
        header = ttk.Frame(parent, style="Root.TFrame")
        header.pack(fill=tk.X)
        ttk.Label(header, text="Power over the day", style="Title.TLabel").pack(side=tk.LEFT)

        self.date = ttk.Combobox(header, width=12, state="readonly")
        self.date.pack(side=tk.RIGHT)
        ttk.Label(header, text="Date", background=BG, foreground=MUTED).pack(side=tk.RIGHT, padx=(12, 6))
        self.horizon = ttk.Combobox(header, width=6, state="readonly")
        self.horizon.pack(side=tk.RIGHT)
        ttk.Label(header, text="Horizon", background=BG, foreground=MUTED).pack(side=tk.RIGHT, padx=(0, 6))
        self.horizon.bind("<<ComboboxSelected>>",
                          lambda _: self.run(lambda: (self.refreshDates(), self.plot())))
        self.date.bind("<<ComboboxSelected>>", lambda _: self.run(self.plot))

        # Capacity and optimiser controls
        tools = ttk.Frame(parent, style="Root.TFrame")
        tools.pack(fill=tk.X, pady=(10, 0))
        ttk.Label(tools, text="Max cap. (kW)", background=BG,
                  foreground=MUTED).pack(side=tk.LEFT, padx=(0, 6))
        self.maxCap = ttk.Entry(tools, width=8)
        self.maxCap.pack(side=tk.LEFT)
        self.maxCap.bind("<Return>", lambda _: self.run(self.setMaxCapacity))
        ttk.Button(tools, text="Set", command=lambda: self.run(self.setMaxCapacity)
                   ).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Button(tools, text="Optimize day", style="Accent.TButton",
                   command=lambda: self.run(self.optimizeDay)).pack(side=tk.RIGHT)
        self.optimFlex = ttk.Spinbox(tools, from_=0, to=QUARTERS_PER_DAY, width=4)
        self.optimFlex.set(self.gui.getOptimFlex())
        self.optimFlex.pack(side=tk.RIGHT, padx=(0, 10))
        ttk.Label(tools, text="Max shift (quarters)", background=BG,
                  foreground=MUTED).pack(side=tk.RIGHT, padx=(0, 6))

        # Working hours: processes may only run inside them, not during lunch
        hoursRow = ttk.Frame(parent, style="Root.TFrame")
        hoursRow.pack(fill=tk.X, pady=(8, 0))
        hours = self.gui.getWorkingHours()

        def timeEntry(value, padLeft=0):
            entry = ttk.Entry(hoursRow, width=6)
            entry.insert(0, value or "")
            entry.pack(side=tk.LEFT, padx=(padLeft, 0))
            entry.bind("<Return>", lambda _: self.run(self.setWorkingHours))
            return entry

        def label(text, padLeft=0):
            ttk.Label(hoursRow, text=text, background=BG, foreground=MUTED
                      ).pack(side=tk.LEFT, padx=(padLeft, 6))

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
        ttk.Label(hoursRow, text="Leave lunch empty for no lunch", background=BG,
                  foreground=MUTED, font=FONT_SMALL).pack(side=tk.LEFT, padx=(10, 0))

        stats = ttk.Frame(parent, style="Root.TFrame")
        stats.pack(fill=tk.X, pady=(12, 0))
        self.statValues: dict[str, tk.StringVar] = {}
        for key, name in [("peak", "Peak power"), ("peakTime", "Peak at"),
                          ("own", "Own energy"), ("over", "Quarters over cap.")]:
            tile = ttk.Frame(stats, style="Card.TFrame", padding=(12, 8))
            tile.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 8))
            self.statValues[key] = tk.StringVar(value="–")
            ttk.Label(tile, text=name, style="StatName.TLabel").pack(anchor=tk.W)
            ttk.Label(tile, textvariable=self.statValues[key],
                      style="StatValue.TLabel").pack(anchor=tk.W)

        chartCard = ttk.Frame(parent, style="Card.TFrame", padding=4)
        chartCard.pack(fill=tk.BOTH, expand=True, pady=(12, 0))

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
        self.machineTable.delete(*self.machineTable.get_children())
        machines = self.gui.getMachines()
        for m in machines:
            self.machineTable.insert("", tk.END, iid=m["name"],
                                     values=(m["name"], f"{m['kW']:g}"))
            self.colorFor(m["name"])
        names = [m["name"] for m in machines]
        self.processMachine["values"] = names
        if names and self.processMachine.get() not in names:
            self.processMachine.set(names[0])

    def refreshProcesses(self):
        self.processTable.delete(*self.processTable.get_children())
        for b in self.gui.getProcessBlocks():
            after = ", ".join(f"#{d + 1}" for d in b["dependsOn"]) or "–"
            self.processTable.insert("", tk.END, iid=str(b["id"]), values=(
                f"#{b['id'] + 1}", b["machine"],
                f"{b['startTime']} – {b['endTime']}", after),
                tags=("outside",) if b["outsideHours"] else ())
        self.processTable.tag_configure("outside", foreground="#d64545")

    def addMachine(self):
        name = self.machineName.get().strip()
        if not name:
            raise ValueError("Give the machine a name")
        self.gui.addMachine(name, float(self.machineKW.get()))
        self.machineName.delete(0, tk.END)
        self.machineKW.delete(0, tk.END)
        self.refreshMachines()
        self.status.set(f"Added machine {name}")
        self.plotIfReady()

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
        self.gui.addProcess(machineName, int(self.processDuration.get()), startIndex)
        self.previewIndex = None
        self.refreshProcesses()
        self.status.set(f"Added process on {machineName} at {quarterToLabel(startIndex)}")
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

    def optimizeDay(self):
        date, horizon = self.date.get(), self.horizon.get()
        if not date:
            raise ValueError("Pick a date first")
        if not self.gui.getProcessBlocks():
            raise ValueError("Add a process first")
        self.gui.setOptimFlex(int(self.optimFlex.get()))
        result = self.gui.optimizeSchedule(date, horizon)
        self.previewIndex = None
        self.refreshProcesses()
        self.plot()
        before, after = result["before"], result["after"]
        self.status.set(
            f"Optimized {date}: peak {before['peakTotalKW']:.1f} kW at {before['peakTime']}"
            f" → {after['peakTotalKW']:.1f} kW at {after['peakTime']}")

    def plotIfReady(self):
        if self.date.get():
            self.run(self.plot)

    # ----------------------------- Chart ----------------------------- #

    def colorFor(self, machineName: str) -> str:
        if machineName not in self.machineColors:
            index = len(self.machineColors) % len(PROCESS_COLORS)
            self.machineColors[machineName] = PROCESS_COLORS[index]
        return self.machineColors[machineName]

    def plot(self):
        date, horizon = self.date.get(), self.horizon.get()
        rows = self.gui.getCombinedProfile(date, horizon)
        self.chart.setData(rows, self.gui.getProcessBlocks(),
                           self.gui.getMaxCapacity(), self.previewBlock(),
                           self.colorFor, self.gui.getWorkingHours())
        self.updateStats(date, horizon)
        self.status.set(f"Showing {date} ({horizon})")

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

    def updateStats(self, date: str, horizon: str):
        s = self.gui.getDaySummary(date, horizon)
        self.statValues["peak"].set(f"{s['peakTotalKW']:.1f} kW")
        self.statValues["peakTime"].set(s["peakTime"])
        self.statValues["own"].set(f"{s['privateEnergyKWh']:.0f} kWh")
        self.statValues["over"].set(str(s["violationCount"]))

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


class DependencyDialog(tk.Toplevel):
    """Pick which processes the given process has to wait for.
    result is the chosen list of ids, or None if cancelled."""

    def __init__(self, parent: tk.Tk, processId: int, blocks: list[dict]):
        super().__init__(parent)
        self.result: list[int] | None = None
        self.title(f"Dependencies of #{processId + 1}")
        self.configure(bg=CARD)
        self.resizable(False, False)
        self.transient(parent)

        byId = {b["id"]: b for b in blocks}
        current = byId[processId]
        box = ttk.Frame(self, style="Card.TFrame", padding=16, borderwidth=0)
        box.pack(fill=tk.BOTH, expand=True)
        ttk.Label(box, text=f"#{processId + 1} {current['machine']} "
                            f"({current['startTime']}–{current['endTime']})\n"
                            "may only start after these are finished:",
                  style="Card.TLabel", justify=tk.LEFT).pack(anchor=tk.W, pady=(0, 8))

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
                            ).pack(anchor=tk.W, pady=1)
            self.choices[b["id"]] = var

        ttk.Label(box, text="Processes that would start too early are moved later.",
                  style="Muted.TLabel").pack(anchor=tk.W, pady=(8, 0))
        buttons = ttk.Frame(box, style="Card.TFrame", borderwidth=0)
        buttons.pack(fill=tk.X, pady=(12, 0))
        ttk.Button(buttons, text="Save", style="Accent.TButton",
                   command=self.save).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="Cancel", command=self.destroy
                   ).pack(side=tk.RIGHT, padx=6)
        self.bind("<Return>", lambda _: self.save())
        self.bind("<Escape>", lambda _: self.destroy())

        self.update_idletasks()
        self.geometry(f"+{parent.winfo_rootx() + 120}+{parent.winfo_rooty() + 120}")
        self.grab_set()
        self.focus_set()
        self.wait_window()

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


if __name__ == "__main__":
    App(GUIinstance("ABB")).mainloop()
