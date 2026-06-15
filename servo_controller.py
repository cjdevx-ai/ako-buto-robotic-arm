import tkinter as tk
from tkinter import ttk, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import json
import os

BG      = "#0d0f14"
SURFACE = "#161920"
CARD    = "#1e2130"
BORDER  = "#2a2d3e"
ACCENT  = "#4f8ef7"
GREEN   = "#22c55e"
DANGER  = "#ef4444"
TEXT    = "#e2e8f0"
MUTED   = "#64748b"
DIM     = "#94a3b8"

FN  = ("Consolas", 9)
FNB = ("Consolas", 9, "bold")
FNL = ("Consolas", 11, "bold")

SAVED_FILE = "saved_positions.json"
CALIBRATION_FILE = "calibration.json"

SERVOS = [
    {"name": "Arm 1",   "pin": 15, "min": 0, "max": 180, "default": 180, "hint": "0=up  180=down"},
    {"name": "Base",    "pin": 18, "min": 0, "max": 180, "default": 90,  "hint": "0=right  180=left"},
    {"name": "Waist",   "pin": 19, "min": 0, "max": 180, "default": 150, "hint": "0=down  180=up"},
    {"name": "Arm 3",   "pin": 21, "min": 0, "max": 180, "default": 40,  "hint": "0=down  180=up"},
    {"name": "Arm 2",   "pin": 22, "min": 0, "max": 180, "default": 90,  "hint": "0=left  180=right"},
    {"name": "Gripper", "pin": 23, "min": 0, "max": 180, "default": 0,   "hint": "0=open  180=close"},
]

START_POS = [180, 90, 150, 40, 90, 0]


class ServoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Servo Controller — ESP32 Robotic Arm")
        self.root.configure(bg=BG)
        self.root.geometry("900x720")
        self.root.minsize(820, 640)

        self.ser = None
        self.connected = False
        self.angles = [s["default"] for s in SERVOS]
        self.sliders = []
        self.min_sliders = []
        self.max_sliders = []
        self.entry_vars = []
        self.saved = []
        self.calib_mode = tk.BooleanVar(value=False)
        self.calib_rows = []
        self._send_after = [None] * len(SERVOS)
        self.load_cb = None
        self.save_name_var = tk.StringVar()

        self._load_calibration()
        self._load_saved()
        self._build_ui()
        self._refresh_ports()

    def _build_ui(self):
        hdr = tk.Frame(self.root, bg=BG)
        hdr.pack(fill="x", padx=20, pady=(16, 0))

        tk.Label(hdr, text="SERVO CONTROLLER", font=("Consolas", 15, "bold"),
                 bg=BG, fg=TEXT).pack(side="left")
        tk.Label(hdr, text="ESP32 · 6-DOF", font=FN, bg=BG,
                 fg=MUTED).pack(side="left", padx=(10, 0), pady=(3, 0))

        self.status_dot = tk.Label(hdr, text="●", font=("Consolas", 13), bg=BG, fg=DANGER)
        self.status_dot.pack(side="right")
        self.status_lbl = tk.Label(hdr, text="Disconnected", font=FNB, bg=BG, fg=MUTED)
        self.status_lbl.pack(side="right", padx=(0, 6))

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x", padx=20, pady=10)

        body = tk.Frame(self.root, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True, padx=(0, 12))

        right = tk.Frame(body, bg=BG)
        right.pack(side="right", fill="both", expand=True)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, parent):
        conn_inner = self._card(parent, "Connection")
        row = tk.Frame(conn_inner, bg=CARD)
        row.pack(fill="x", pady=(0, 4))
        tk.Label(row, text="Port", font=FN, bg=CARD, fg=DIM, width=5, anchor="w").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_cb = ttk.Combobox(row, textvariable=self.port_var, width=12, font=FN, state="readonly")
        self.port_cb.pack(side="left", padx=(4, 10))
        tk.Label(row, text="Baud", font=FN, bg=CARD, fg=DIM).pack(side="left")
        self.baud_var = tk.StringVar(value="115200")
        ttk.Combobox(row, textvariable=self.baud_var, values=["9600", "115200"],
                     width=8, font=FN, state="readonly").pack(side="left", padx=(4, 10))
        self.conn_btn = self._btn(row, "Connect", self._toggle_connect, ACCENT)
        self.conn_btn.pack(side="left", padx=(4, 0))
        self._btn(row, "↻", self._refresh_ports, BORDER).pack(side="left", padx=(6, 0))

        servo_inner = self._card(parent, "Servo Angles")
        for i, s in enumerate(SERVOS):
            self._build_servo_row(servo_inner, i, s)

        act_inner = self._card(parent, "Quick Actions")
        btn_row = tk.Frame(act_inner, bg=CARD)
        btn_row.pack(fill="x")
        self._btn(btn_row, "Start Position", self._send_start, ACCENT).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "Center All", self._center_all, BORDER).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "Send All", self._send_all, BORDER).pack(side="left", padx=(0, 6))
        self.calib_btn = self._btn(btn_row, "Calibration", self._toggle_calib, BORDER)
        self.calib_btn.pack(side="left", padx=(0, 6))

        tk.Frame(act_inner, bg=BORDER, height=1).pack(fill="x", pady=12)
        
        save_row = tk.Frame(act_inner, bg=CARD)
        save_row.pack(fill="x")
        tk.Label(save_row, text="Save As", font=FN, bg=CARD, fg=DIM).pack(side="left")
        self.save_name_var.set(f"Pos {len(self.saved)+1}")
        ent = tk.Entry(save_row, textvariable=self.save_name_var, font=FN,
                       bg=SURFACE, fg=TEXT, insertbackground=TEXT, bd=0)
        ent.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self._btn(save_row, "Save Position", self._save_position, GREEN).pack(side="right", padx=(10, 0))

        tk.Frame(act_inner, bg=BORDER, height=1).pack(fill="x", pady=12)

        load_row = tk.Frame(act_inner, bg=CARD)
        load_row.pack(fill="x")
        tk.Label(load_row, text="Load Select", font=FN, bg=CARD, fg=DIM).pack(side="left")
        self.load_cb = ttk.Combobox(load_row, font=FN, state="readonly")
        self.load_cb.pack(side="left", padx=(10, 0), fill="x", expand=True)
        self.load_cb.bind("<<ComboboxSelected>>", self._on_load_selected)

    def _build_servo_row(self, parent, i, s):
        main_row = tk.Frame(parent, bg=CARD)
        main_row.pack(fill="x", pady=3)

        row = tk.Frame(main_row, bg=CARD)
        row.pack(fill="x")

        tk.Label(row, text=f"S{i}", font=FNB, bg=BORDER, fg=DIM,
                 width=3, anchor="center", padx=4, pady=2).pack(side="left", padx=(0, 8))

        nf = tk.Frame(row, bg=CARD, width=90)
        nf.pack(side="left", padx=(0, 8))
        nf.pack_propagate(False)
        tk.Label(nf, text=s["name"], font=FNB, bg=CARD, fg=TEXT, anchor="w").pack(anchor="w")
        tk.Label(nf, text=s["hint"], font=("Consolas", 7), bg=CARD, fg=MUTED, anchor="w").pack(anchor="w")

        tk.Label(row, text=f"GPIO{s['pin']}", font=("Consolas", 7),
                 bg=CARD, fg=MUTED, width=7, anchor="w").pack(side="right", padx=(0, 4))

        e_var = tk.StringVar(value=str(s["default"]))
        self.entry_vars.append(e_var)
        ent = tk.Entry(row, textvariable=e_var, font=FNL, bg=SURFACE, fg=ACCENT,
                       insertbackground=TEXT, bd=0, width=4, justify="center")
        ent.pack(side="right", padx=(6, 0))
        ent.bind("<Return>", lambda e, idx=i: self._on_entry(idx))
        ent.bind("<FocusOut>", lambda e, idx=i: self._on_entry(idx))

        var = tk.IntVar(value=s["default"])
        sl = tk.Scale(row, from_=s["min"], to=s["max"], orient="horizontal",
                      variable=var, bg=ACCENT, fg=TEXT, troughcolor=SURFACE,
                      activebackground=TEXT, highlightthickness=0,
                      sliderrelief="flat", bd=0, showvalue=False,
                      width=12, sliderlength=25,
                      command=lambda v, idx=i: self._on_slide(idx, int(v)))
        sl.pack(side="left", fill="x", expand=True)
        self.sliders.append(sl)

        # Calibration Row
        calib_row = tk.Frame(main_row, bg=CARD)
        self.calib_rows.append(calib_row)
        # Hidden by default

        cleft = tk.Frame(calib_row, bg=CARD)
        cleft.pack(side="left", fill="x", expand=True, padx=(45, 0))
        
        tk.Label(cleft, text="Min Limit", font=("Consolas", 7), bg=CARD, fg=MUTED).pack(side="left")
        min_var = tk.IntVar(value=s["min"])
        msl = tk.Scale(cleft, from_=0, to=180, orient="horizontal",
                       variable=min_var, bg=MUTED, fg=DIM, troughcolor=SURFACE,
                       activebackground=ACCENT, highlightthickness=0,
                       sliderrelief="flat", bd=0, showvalue=True, font=("Consolas", 7),
                       width=10, sliderlength=15,
                       command=lambda v, idx=i: self._update_calib(idx))
        msl.pack(side="left", fill="x", expand=True, padx=4)
        self.min_sliders.append(msl)

        cright = tk.Frame(calib_row, bg=CARD)
        cright.pack(side="right", fill="x", expand=True)
        tk.Label(cright, text="Max Limit", font=("Consolas", 7), bg=CARD, fg=MUTED).pack(side="left")
        max_var = tk.IntVar(value=s["max"])
        maxsl = tk.Scale(cright, from_=0, to=180, orient="horizontal",
                        variable=max_var, bg=MUTED, fg=DIM, troughcolor=SURFACE,
                        activebackground=ACCENT, highlightthickness=0,
                        sliderrelief="flat", bd=0, showvalue=True, font=("Consolas", 7),
                        width=10, sliderlength=15,
                        command=lambda v, idx=i: self._update_calib(idx))
        maxsl.pack(side="left", fill="x", expand=True, padx=4)
        self.max_sliders.append(maxsl)

    def _build_right(self, parent):
        log_inner = self._card(parent, "Serial Log", expand=False)
        log_frame = tk.Frame(log_inner, bg="#0a0c10",
                             highlightthickness=1, highlightbackground=BORDER)
        log_frame.pack(fill="both", expand=True)
        self.log_text = tk.Text(log_frame, bg="#0a0c10", fg=DIM,
                                font=("Consolas", 8), bd=0, padx=8, pady=6,
                                state="disabled", height=10,
                                insertbackground=TEXT, wrap="word",
                                selectbackground=BORDER)
        self.log_text.pack(fill="both", expand=True)
        self._btn(log_inner, "Clear log", self._clear_log, BORDER).pack(anchor="e", pady=(6, 0))

        saved_inner = self._card(parent, "Saved Positions", expand=True)
        
        # Scrollable container
        self.canvas = tk.Canvas(saved_inner, bg=CARD, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(saved_inner, orient="vertical", command=self.canvas.yview)
        self.saved_frame = tk.Frame(self.canvas, bg=CARD)
        
        self.canvas.create_window((0, 0), window=self.saved_frame, anchor="nw", tags="inner_frame")
        self.canvas.configure(yscrollcommand=scrollbar.set)
        
        scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.saved_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig("inner_frame", width=e.width))

        # Mousewheel binding
        def _on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        
        self.canvas.bind("<Enter>", lambda e: self.canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.canvas.bind("<Leave>", lambda e: self.canvas.unbind_all("<MouseWheel>"))

        self._render_saved()

    def _card(self, parent, title, expand=False):
        outer = tk.Frame(parent, bg=CARD, highlightthickness=1, highlightbackground=BORDER)
        outer.pack(fill="both", expand=expand, pady=(0, 10))
        tk.Label(outer, text=title.upper(), font=("Consolas", 8, "bold"),
                 bg=CARD, fg=MUTED, anchor="w").pack(fill="x", padx=12, pady=(8, 4))
        inner = tk.Frame(outer, bg=CARD)
        inner.pack(fill="both", expand=expand, padx=12, pady=(0, 10))
        return inner

    def _btn(self, parent, text, cmd, color):
        return tk.Button(parent, text=text, command=cmd, font=FNB,
                         bg=color, fg=TEXT, bd=0, padx=10, pady=5,
                         activebackground=BORDER, activeforeground=TEXT,
                         cursor="hand2", relief="flat")

    def _refresh_ports(self):
        ports = [p.device for p in serial.tools.list_ports.comports()]
        self.port_cb["values"] = ports
        if "COM9" in ports:
            self.port_var.set("COM9")
        elif ports:
            self.port_var.set(ports[0])

    def _toggle_connect(self):
        if self.connected:
            self._disconnect()
        else:
            self._connect()

    def _connect(self):
        port = self.port_var.get()
        baud = int(self.baud_var.get())
        if not port:
            messagebox.showerror("No port", "Select a COM port first.")
            return
        try:
            self.ser = serial.Serial(port, baud, timeout=1)
            time.sleep(2)
            self.connected = True
            self.status_dot.config(fg=GREEN)
            self.status_lbl.config(text=f"Connected  {port} @ {baud}", fg=GREEN)
            self.conn_btn.config(text="Disconnect", bg=DANGER)
            self._log(f"Connected to {port} at {baud} baud")
            threading.Thread(target=self._read_loop, daemon=True).start()
        except Exception as e:
            messagebox.showerror("Connection failed", str(e))

    def _disconnect(self):
        self.connected = False
        if self.ser:
            try:
                self.ser.close()
            except:
                pass
            self.ser = None
        self.status_dot.config(fg=DANGER)
        self.status_lbl.config(text="Disconnected", fg=MUTED)
        self.conn_btn.config(text="Connect", bg=ACCENT)
        self._log("Disconnected")

    def _read_loop(self):
        while self.connected and self.ser:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    self.root.after(0, self._log, f"← {line}")
            except:
                break

    def _write(self, cmd):
        if self.ser and self.connected:
            try:
                self.ser.write((cmd + "\n").encode())
            except Exception as e:
                self._log(f"Error: {e}")
                self._disconnect()

    def _on_slide(self, i, v):
        self.angles[i] = v
        self.entry_vars[i].set(str(v))
        if self._send_after[i]:
            self.root.after_cancel(self._send_after[i])
        self._send_after[i] = self.root.after(40, self._send_single, i, v)

    def _on_entry(self, i):
        try:
            v = int(self.entry_vars[i].get())
            mi = int(self.sliders[i].cget("from"))
            ma = int(self.sliders[i].cget("to"))
            
            # Clamp value
            if v < mi: v = mi
            if v > ma: v = ma
            
            self.entry_vars[i].set(str(v))
            self.sliders[i].set(v)
            self._on_slide(i, v)
        except ValueError:
            self.entry_vars[i].set(str(self.angles[i]))

    def _send_single(self, i, v):
        self._log(f"→ {SERVOS[i]['name']} = {v}°")
        self._write(f"{i}:{v}")

    def _send_all(self):
        cmd = ",".join(f"{i}:{v}" for i, v in enumerate(self.angles))
        self._log("→ " + "  ".join(f"S{i}={v}°" for i, v in enumerate(self.angles)))
        self._write(cmd)

    def _center_all(self):
        for i, s in enumerate(SERVOS):
            mid = (s["min"] + s["max"]) // 2
            self.angles[i] = mid
            self.sliders[i].set(mid)
            self.entry_vars[i].set(str(mid))
        self._send_all()

    def _send_start(self):
        for i, v in enumerate(START_POS):
            self.angles[i] = v
            self.sliders[i].set(v)
            self.entry_vars[i].set(str(v))
        self._send_all()
        self._log("→ Start position")

    def _log(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.log_text.config(state="normal")
        self.log_text.insert("end", f"[{ts}] {msg}\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self):
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    def _toggle_calib(self):
        new_val = not self.calib_mode.get()
        self.calib_mode.set(new_val)
        if new_val:
            for row in self.calib_rows:
                row.pack(fill="x", pady=(0, 4))
            self.calib_btn.config(bg=ACCENT)
        else:
            for row in self.calib_rows:
                row.pack_forget()
            self.calib_btn.config(bg=BORDER)
            self._save_calibration()

    def _update_calib(self, i):
        mi = self.min_sliders[i].get()
        ma = self.max_sliders[i].get()
        if mi >= ma:
            mi = ma - 1
            self.min_sliders[i].set(mi)
        
        self.sliders[i].config(from_=mi, to=ma)
        
        # Clamp current value
        curr = self.sliders[i].get()
        if curr < mi:
            self.sliders[i].set(mi)
        elif curr > ma:
            self.sliders[i].set(ma)

    def _save_calibration(self):
        data = []
        for i in range(len(SERVOS)):
            data.append({
                "min": self.min_sliders[i].get(),
                "max": self.max_sliders[i].get()
            })
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(data, f)
        self._log("Calibration saved")

    def _load_calibration(self):
        if os.path.exists(CALIBRATION_FILE):
            try:
                with open(CALIBRATION_FILE) as f:
                    data = json.load(f)
                for i, d in enumerate(data):
                    if i < len(SERVOS):
                        SERVOS[i]["min"] = d["min"]
                        SERVOS[i]["max"] = d["max"]
            except Exception as e:
                print(f"Error loading calibration: {e}")

    def _save_position(self):
        angles = self.angles[:]
        name = self.save_name_var.get().strip()
        if not name:
            name = f"Position {len(self.saved) + 1}"
        
        self.saved.append({"name": name, "angles": angles})
        self._save_to_file()
        self._render_saved()
        self._log(f"Saved: {name}")
        self.save_name_var.set(f"Pos {len(self.saved) + 1}")

    def _load_pos(self, idx):
        angles = self.saved[idx]["angles"]
        for i, v in enumerate(angles):
            self.angles[i] = v
            self.sliders[i].set(v)
            self.entry_vars[i].set(str(v))
        self._send_all()
        self._log(f"Loaded: {self.saved[idx]['name']}")

    def _delete_pos(self, idx):
        name = self.saved[idx]["name"]
        if messagebox.askyesno("Confirm Delete", f"Delete '{name}'?"):
            del self.saved[idx]
            self._save_to_file()
            self._render_saved()
            self._log(f"Deleted: {name}")

    def _edit_pos(self, idx):
        pos = self.saved[idx]
        edit_win = tk.Toplevel(self.root)
        edit_win.title(f"Edit {pos['name']}")
        edit_win.geometry("350x200")
        edit_win.configure(bg=BG)
        edit_win.transient(self.root)
        edit_win.grab_set()

        tk.Label(edit_win, text=f"EDIT POSITION", font=FNB, bg=BG, fg=TEXT).pack(pady=10)

        inner = tk.Frame(edit_win, bg=CARD, padx=15, pady=15)
        inner.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(inner, text="Name", font=FN, bg=CARD, fg=DIM).grid(row=0, column=0, sticky="w")
        name_var = tk.StringVar(value=pos["name"])
        ent = tk.Entry(inner, textvariable=name_var, font=FN, bg=SURFACE, fg=TEXT, bd=0)
        ent.grid(row=0, column=1, padx=10, sticky="ew")
        inner.grid_columnconfigure(1, weight=1)

        def save_edit():
            new_name = name_var.get().strip()
            if not new_name:
                messagebox.showerror("Error", "Name cannot be empty")
                return
            
            # Ask if user wants to update angles too
            update_angles = messagebox.askyesno("Update Angles", 
                f"Update '{new_name}' with current servo positions?")
            
            pos["name"] = new_name
            if update_angles:
                pos["angles"] = self.angles[:]
            
            self._save_to_file()
            self._render_saved()
            self._log(f"Edited: {new_name}")
            edit_win.destroy()

        self._btn(inner, "Save Changes", save_edit, ACCENT).grid(row=1, column=0, columnspan=2, pady=(20, 0))

    def _render_saved(self):
        for w in self.saved_frame.winfo_children():
            w.destroy()
        
        self._update_load_dropdown()

        if not self.saved:
            tk.Label(self.saved_frame, text="No positions saved yet.",
                     font=FN, bg=CARD, fg=MUTED).pack(anchor="w", pady=4)
            return
        for i, pos in enumerate(self.saved):
            row = tk.Frame(self.saved_frame, bg=SURFACE,
                           highlightthickness=1, highlightbackground=BORDER)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=pos["name"], font=FNB, bg=SURFACE,
                     fg=TEXT, anchor="w").pack(side="left", padx=8, pady=4)
            tk.Label(row, text="  ".join(f"{v}°" for v in pos["angles"]),
                     font=("Consolas", 7), bg=SURFACE, fg=MUTED).pack(side="left", padx=4)
            self._btn(row, "✕", lambda idx=i: self._delete_pos(idx),
                      SURFACE).pack(side="right", padx=4, pady=2)
            self._btn(row, "Edit", lambda idx=i: self._edit_pos(idx),
                      BORDER).pack(side="right", padx=(0, 4), pady=2)
            self._btn(row, "Load", lambda idx=i: self._load_pos(idx),
                      ACCENT).pack(side="right", padx=(0, 4), pady=2)

    def _update_load_dropdown(self):
        if hasattr(self, 'load_cb') and self.load_cb:
            names = [pos["name"] for pos in self.saved]
            self.load_cb["values"] = names
            if not names:
                self.load_cb.set("")

    def _on_load_selected(self, event):
        name = self.load_cb.get()
        for i, pos in enumerate(self.saved):
            if pos["name"] == name:
                self._load_pos(i)
                break

    def _save_to_file(self):
        with open(SAVED_FILE, "w") as f:
            json.dump(self.saved, f, indent=2)

    def _load_saved(self):
        if os.path.exists(SAVED_FILE):
            try:
                with open(SAVED_FILE) as f:
                    self.saved = json.load(f)
            except:
                self.saved = []


if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style()
    style.theme_use("clam")
    style.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE,
                    foreground=TEXT, bordercolor=BORDER, arrowcolor=DIM,
                    selectbackground=BORDER, selectforeground=TEXT)
    ServoApp(root)
    root.mainloop()