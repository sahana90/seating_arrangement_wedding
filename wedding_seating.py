import json
import csv
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid
import os
import random


# ======================================================
# Configuration
# ======================================================

ROOM_L = 30.0  # meters
ROOM_H = 15.0  # meters

PIXELS_PER_METER = 60  # scale
CANVAS_W = int(ROOM_L * PIXELS_PER_METER)
CANVAS_H = int(ROOM_H * PIXELS_PER_METER)

VIEWPORT_W = 950
VIEWPORT_H = 600

SEATS_WARNING_LIMIT = 10
SEATS_PER_TABLE = 8

SPECIAL_TABLE = "Bride & Groom"

RELATIONSHIPS = [
    "Bride",
    "Groom",
    "Immediate Family",
    "Extended Family",
    "Childhood Friends",
    "UniversityFriends",
    "Colleagues"
]

# Geometry
TABLE_R_PX = 40
ATT_R_PX = 10
ORBIT_R_PX = 85

SPECIAL_W_PX = 220
SPECIAL_H_PX = 70

# Background (black requested)
CANVAS_BG = "#000000"
CANVAS_BG_RGB = (0, 0, 0)

# "Transparency" simulation by blending with background:
# user request: lower category => lower transparency (i.e., more transparent / dimmer)
MIN_ALPHA = 0.25   # category=0
MAX_ALPHA = 1.00   # category=max


# ======================================================
# Utilities
# ======================================================

def clamp(v, lo, hi):
    return max(lo, min(hi, v))

def blend_rgb(bg, fg, alpha):
    """Return bg*(1-alpha)+fg*alpha (alpha in [0,1])."""
    r = int(bg[0] + alpha * (fg[0] - bg[0]))
    g = int(bg[1] + alpha * (fg[1] - bg[1]))
    b = int(bg[2] + alpha * (fg[2] - bg[2]))
    return (clamp(r, 0, 255), clamp(g, 0, 255), clamp(b, 0, 255))

def rgb_to_hex(rgb):
    return f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"

def ensure_attendee_id(a):
    if "_id" not in a:
        a["_id"] = uuid.uuid4().hex
    return a["_id"]


# ======================================================
# Seating Model
# ======================================================

class SeatingModel:
    """
    tables: dict[str, list[attendee dict]]
    table_positions: dict[str, (x_m, y_m)]
    """
    def __init__(self):
        self.tables = {}
        self.table_positions = {}

    # -----------------------
    # Load / Save
    # -----------------------

    def load_seating(self, path="seating_arrangement.json"):
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)

            self.table_positions = raw.pop("_table_positions", {})
            self.tables = raw

            # convert list positions to tuples if needed
            for k, v in list(self.table_positions.items()):
                if isinstance(v, list) and len(v) == 2:
                    self.table_positions[k] = (float(v[0]), float(v[1]))

            self._normalize_all_attendees()
            self._ensure_special_table_position()
            self._ensure_non_special_tables_below_special()

            # if positions missing for some tables, re-layout
            missing = [t for t in self.tables.keys() if t not in self.table_positions]
            if missing:
                self.reset_layout()

            return True
        except Exception as e:
            messagebox.showerror("Load error", f"Failed to load seating:\n{e}")
            return False

    def save_json(self, path="seating_arrangement.json"):
        data = dict(self.tables)
        # JSON-friendly positions
        data["_table_positions"] = {k: [float(x), float(y)] for k, (x, y) in self.table_positions.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save_csv(self, path="seating_arrangement.csv"):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Table", "Guest", "Relationship", "Category"])
            for t, guests in self.tables.items():
                for g in guests:
                    w.writerow([t, g.get("name", ""), g.get("relationship", ""), g.get("category", "")])

    # -----------------------
    # Normalization
    # -----------------------

    def _normalize_all_attendees(self):
        attendees = [a for guests in self.tables.values() for a in guests]
        if not attendees:
            return

        # ensure IDs
        for a in attendees:
            ensure_attendee_id(a)

        # Ensure exactly one Bride and one Groom relationship
        bride = next((a for a in attendees if a.get("relationship") == "Bride"), None)
        groom = next((a for a in attendees if a.get("relationship") == "Groom"), None)

        pool = [a for a in attendees if a not in (bride, groom)]

        if not bride and pool:
            bride = random.choice(pool)
            bride["relationship"] = "Bride"
            pool.remove(bride)

        if not groom and pool:
            groom = random.choice(pool)
            groom["relationship"] = "Groom"
            pool.remove(groom)

        for a in pool:
            if "relationship" not in a:
                a["relationship"] = random.choice(RELATIONSHIPS[2:])

        # Reassign category based on relationship priority index
        for a in attendees:
            rel = a.get("relationship", "Colleagues")
            if rel not in RELATIONSHIPS:
                rel = "Colleagues"
                a["relationship"] = rel
            a["category"] = RELATIONSHIPS.index(rel)

        # Ensure SPECIAL_TABLE exists and contains Bride+Groom
        if SPECIAL_TABLE not in self.tables:
            self.tables[SPECIAL_TABLE] = []
        # Move bride and groom into special table (remove from others)
        def remove_from_all(att):
            for t in list(self.tables.keys()):
                if att in self.tables[t]:
                    self.tables[t].remove(att)

        if bride:
            remove_from_all(bride)
        if groom:
            remove_from_all(groom)

        # Keep special table exactly bride+groom if found
        self.tables[SPECIAL_TABLE] = []
        if bride:
            self.tables[SPECIAL_TABLE].append(bride)
        if groom:
            self.tables[SPECIAL_TABLE].append(groom)

    def _ensure_special_table_position(self):
        # Top-center fixed position
        cx = ROOM_L / 2.0
        cy = 1.5
        self.table_positions[SPECIAL_TABLE] = (cx, cy)

    def _special_bottom_y_m(self):
        # bottom edge of special table + margin in meters
        half_h_m = (SPECIAL_H_PX / PIXELS_PER_METER) / 2.0
        margin_m = 0.6
        return self.table_positions[SPECIAL_TABLE][1] + half_h_m + margin_m

    def _ensure_non_special_tables_below_special(self):
        min_y = self._special_bottom_y_m()
        for t in self.tables.keys():
            if t == SPECIAL_TABLE:
                continue
            x, y = self.table_positions.get(t, (ROOM_L/2, min_y + 1.0))
            if y < min_y:
                y = min_y
            self.table_positions[t] = (x, y)

    # -----------------------
    # Generation from attendees.json
    # -----------------------

    def generate_from_attendees(self, path="attendees.json"):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing {path}")

        with open(path, "r", encoding="utf-8") as f:
            root = json.load(f)
        raw = root.get("attendees", [])
        if not isinstance(raw, list) or not raw:
            raise ValueError("attendees.json must contain a non-empty 'attendees' list")

        # Ensure IDs
        for a in raw:
            ensure_attendee_id(a)

        # Select one Bride and one Groom
        random.shuffle(raw)
        bride = raw.pop()
        groom = raw.pop() if raw else random.choice([bride])  # fallback

        bride["relationship"] = "Bride"
        groom["relationship"] = "Groom"

        # Assign remaining relationships randomly (non Bride/Groom)
        for a in raw:
            if a.get("relationship") not in RELATIONSHIPS:
                a["relationship"] = random.choice(RELATIONSHIPS[2:])

        # Assign category as relationship priority
        for a in [bride, groom] + raw:
            a["category"] = RELATIONSHIPS.index(a["relationship"])

        # Group by relationship (except Bride/Groom)
        groups = {}
        for a in raw:
            groups.setdefault(a["relationship"], []).append(a)

        self.tables = {SPECIAL_TABLE: [bride, groom]}
        # Create tables for remaining groups
        idx = 1
        for rel in RELATIONSHIPS[2:]:
            if rel in groups:
                self.tables[f"Table {idx}"] = groups[rel]
                idx += 1

        # Positions
        self._ensure_special_table_position()
        self.reset_layout()  # applies below-special offset and priority ordering

    # -----------------------
    # Reset & Auto-layout
    # -----------------------

    def reset_layout(self):
        """
        Arrange tables below Bride&Groom with an offset so they don't overlap.
        Higher priority tables (lower category index) are placed closer.
        """
        self._normalize_all_attendees()
        self._ensure_special_table_position()

        min_y = self._special_bottom_y_m()

        # Sort tables by min category (lower first => higher priority)
        others = [t for t in self.tables.keys() if t != SPECIAL_TABLE]
        def table_priority(t):
            guests = self.tables[t]
            if not guests:
                return 999
            return min(g.get("category", 999) for g in guests)

        others.sort(key=table_priority)

        # Place in rows below the special table
        cx = ROOM_L / 2.0
        cols = 4
        x_spacing_m = 4.2
        y_spacing_m = 2.6

        for i, t in enumerate(others):
            row = i // cols
            col = i % cols
            x = cx + (col - (cols - 1) / 2) * x_spacing_m
            y = min_y + row * y_spacing_m

            # clamp inside room bounds
            x = clamp(x, 2.0, ROOM_L - 2.0)
            y = clamp(y, min_y, ROOM_H - 2.0)
            self.table_positions[t] = (x, y)

        self._ensure_non_special_tables_below_special()


# ======================================================
# Planner Canvas
# ======================================================

class PlannerCanvas(tk.Canvas):
    def __init__(self, parent, model: SeatingModel):
        super().__init__(
            parent,
            width=VIEWPORT_W,
            height=VIEWPORT_H,
            bg=CANVAS_BG,
            highlightthickness=0,
            scrollregion=(0, 0, CANVAS_W, CANVAS_H)
        )
        self.model = model

        # Drag state
        self.drag = None  # dict with type, ids, table, etc.

        # Maps attendee_id -> (oval_id, text_id)
        self.attendee_items = {}

        # Maps table_name -> table center item IDs (for future extension)
        self.draw()

    # -----------------------
    # Coordinate helpers
    # -----------------------

    def m2px(self, v):
        return v * PIXELS_PER_METER

    # -----------------------
    # Color: red/blue with "transparency" by blending with black
    # lower category => lower transparency (more transparent/dimmer)
    # -----------------------

    def attendee_color(self, attendee):
        cat = int(attendee.get("category", len(RELATIONSHIPS) - 1))
        max_cat = max(1, len(RELATIONSHIPS) - 1)
        alpha = MIN_ALPHA + (cat / max_cat) * (MAX_ALPHA - MIN_ALPHA)
        alpha = clamp(alpha, MIN_ALPHA, MAX_ALPHA)

        rel = attendee.get("relationship", "Colleagues")
        if rel == "Bride":
            fg = (255, 0, 0)
        elif rel == "Groom":
            fg = (0, 110, 255)
        else:
            # side derived from closeness to Bride/Groom: keep family closer to Bride by default
            # (still red/blue themed; no greys)
            if rel in ("Immediate Family", "Extended Family"):
                fg = (255, 40, 40)  # red family
            else:
                fg = (40, 140, 255)  # blue-ish friends/colleagues

        rgb = blend_rgb(CANVAS_BG_RGB, fg, alpha)
        return rgb_to_hex(rgb)

    # -----------------------
    # Drawing
    # -----------------------

    def draw(self):
        self.delete("all")
        self.attendee_items.clear()

        # Optional: draw room border
        self.create_rectangle(
            5, 5, CANVAS_W - 5, CANVAS_H - 5,
            outline="#333333", width=2
        )

        # ----- Legend (dynamic; redraws on every draw/drop) -----
        # Show each table with one representative attendee color.
        # If the table is empty, show a neutral gray.
        legend_x = 12
        legend_y = 12
        legend_w = 220
        line_h = 18

        def parse_rgb_from_hex(hex_color: str):
            # expected format: #rrggbb
            if not isinstance(hex_color, str) or not hex_color.startswith('#') or len(hex_color) != 7:
                return (160, 160, 160)
            try:
                return (int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16))
            except Exception:
                return (160, 160, 160)

        legend_bg = "#111111"
        legend_border = "#333333"
        self.create_rectangle(
            legend_x - 16, legend_y - 16,
            legend_x + legend_w, legend_y + (line_h * (len(self.model.tables) + 1)) + 6,
            fill=legend_bg, outline=legend_border, width=1
        )
        self.create_text(legend_x, legend_y - 2, text="Legend (by table colors)",
                          fill="#ffffff", font=("Arial", 10, "bold"), anchor="nw")

        sorted_tables = sorted(self.model.tables.keys())
        for idx, table in enumerate(sorted_tables):
            guests = self.model.tables.get(table, [])

            base_y = legend_y + (idx*5 + 1) * line_h

            # table header swatch: representative attendee
            rep = guests[0] if guests else None
            header_color = self.attendee_color(rep) if rep else "#666666"

            # color swatch (table header)
            self.create_rectangle(
                legend_x, base_y, legend_x + 14, base_y + 14,
                fill=header_color, outline="#ffffff", width=1
            )
            # table name
            self.create_text(
                legend_x + 22, base_y + 7,
                text=f"{table}",
                fill="#ffffff", font=("Arial", 9), anchor="w"
            )

            # attendee list with their own colors
            # keep it readable: one attendee per line, starting under header
            # (legend box height grows with number of tables; attendees may overflow slightly but redraws correctly)
            for j, a in enumerate(guests[:8]):
                # limit to avoid huge legends; if you want unlimited, remove [:8]
                c = self.attendee_color(a)
                y = base_y + 16 + j * 14
                self.create_rectangle(
                    legend_x + 22, y - 2,
                    legend_x + 34, y + 10,
                    fill=c, outline="#ffffff", width=1
                )
                self.create_text(
                    legend_x + 40, y + 4,
                    text=a.get("name", ""),
                    fill="#ffffff", font=("Arial", 7), anchor="w"
                )


        # ----- Tables -----
        for table, guests in self.model.tables.items():
            tx, ty = self.model.table_positions.get(table, (ROOM_L / 2, ROOM_H / 2))

            px, py = self.m2px(tx), self.m2px(ty)

            group_tag = f"group:{table}"  # everything belonging to a table
            handle_tag = f"handle:{table}"  # only table shape+label (drag handles)

            # ---- draw table shape ----
            if table == SPECIAL_TABLE:
                # rectangular special table
                w, h = SPECIAL_W_PX, SPECIAL_H_PX
                table_item = self.create_rectangle(
                    px - w / 2, py - h / 2, px + w / 2, py + h / 2,
                    fill="#222222", outline="#f5d76e", width=2,
                    tags=(group_tag, handle_tag)
                )
                label_color = "#ffffff"
            else:
                warn = len(guests) > SEATS_WARNING_LIMIT
                fill = "#a40000" if warn else "#111111"
                table_item = self.create_oval(
                    px - TABLE_R_PX, py - TABLE_R_PX, px + TABLE_R_PX, py + TABLE_R_PX,
                    fill=fill, outline="#aaaaaa", width=2,
                    tags=(group_tag, handle_tag)
                )
                label_color = "#ffffff"

            # ---- label includes count ----
            label_text = f"{table} ({len(guests)})"
            label_item = self.create_text(
                px, py,
                text=label_text,
                fill=label_color,
                font=("Arial", 11, "bold"),
                tags=(group_tag, handle_tag)
            )

            # ---- table dragging: bind ONLY on handle_tag (NOT group_tag) ----
            if table != SPECIAL_TABLE:
                self.tag_bind(handle_tag, "<ButtonPress-1>",
                              lambda e, t=table: self.start_table_drag(e, t))
                self.tag_bind(handle_tag, "<B1-Motion>", self.drag_table)
                self.tag_bind(handle_tag, "<ButtonRelease-1>", self.end_table_drag)

            # ---- attendees around table ----
            # Sort deterministic: by category then name
            guests_sorted = sorted(
                guests,
                key=lambda g: (int(g.get("category", 99)), g.get("name", ""))
            )
            n = len(guests_sorted)

            for i, g in enumerate(guests_sorted):
                aid = ensure_attendee_id(g)

                ang = 2 * math.pi * i / max(1, n)
                gx = px + math.cos(ang) * ORBIT_R_PX
                gy = py + math.sin(ang) * ORBIT_R_PX

                color = self.attendee_color(g)

                # circle
                oval_id = self.create_oval(
                    gx - ATT_R_PX, gy - ATT_R_PX, gx + ATT_R_PX, gy + ATT_R_PX,
                    fill=color, outline="#ffffff", width=1,
                    tags=(group_tag, f"attendee:{aid}", "attendee")
                )
                # name (always visible)
                text_id = self.create_text(
                    gx, gy + 18,
                    text=g.get("name", ""),
                    fill="#ffffff",
                    font=("Arial", 8),
                    tags=(group_tag, f"attendee:{aid}", "attendee_label")
                )

                self.attendee_items[aid] = (oval_id, text_id)

                # bind dragging for BOTH circle and label; return 'break' to stop propagation
                self.tag_bind(f"attendee:{aid}", "<ButtonPress-1>",
                              lambda e, t=table, a=g, attendee_id=aid: self.start_attendee_drag(e, t, a, attendee_id))
                self.tag_bind(f"attendee:{aid}", "<B1-Motion>", self.drag_attendee)
                self.tag_bind(f"attendee:{aid}", "<ButtonRelease-1>",
                              lambda e, a=g, attendee_id=aid: self.end_attendee_drag(e, a, attendee_id))

        self.configure(scrollregion=self.bbox("all"))

    # ======================================================
    # Dragging: Tables
    # ======================================================

    def start_table_drag(self, e, table):
        self.drag = {
            "type": "table",
            "table": table,
            "x": self.canvasx(e.x),
            "y": self.canvasy(e.y)
        }
        return "break"

    def drag_table(self, e):
        if not self.drag or self.drag.get("type") != "table":
            return "break"
        x = self.canvasx(e.x)
        y = self.canvasy(e.y)
        dx = x - self.drag["x"]
        dy = y - self.drag["y"]
        self.move(f"group:{self.drag['table']}", dx, dy)
        self.drag["x"], self.drag["y"] = x, y
        return "break"

    def end_table_drag(self, e):
        if not self.drag or self.drag.get("type") != "table":
            self.drag = None
            return "break"

        table = self.drag["table"]
        x = self.canvasx(e.x) / PIXELS_PER_METER
        y = self.canvasy(e.y) / PIXELS_PER_METER

        # Keep tables below the special table
        min_y = self.model._special_bottom_y_m()
        y = max(y, min_y)

        # Keep inside room bounds
        x = clamp(x, 2.0, ROOM_L - 2.0)
        y = clamp(y, min_y, ROOM_H - 2.0)

        self.model.table_positions[table] = (x, y)
        self.drag = None
        return "break"

    # ======================================================
    # Dragging: Attendees (circle + name move together)
    # ======================================================

    def start_attendee_drag(self, e, table, attendee, attendee_id):
        # Store which attendee is being dragged and from which table
        self.drag = {
            "type": "attendee",
            "table": table,
            "attendee": attendee,
            "attendee_id": attendee_id,
            "x": self.canvasx(e.x),
            "y": self.canvasy(e.y)
        }
        return "break"

    def drag_attendee(self, e):
        if not self.drag or self.drag.get("type") != "attendee":
            return "break"

        x = self.canvasx(e.x)
        y = self.canvasy(e.y)
        dx = x - self.drag["x"]
        dy = y - self.drag["y"]

        attendee_id = self.drag["attendee_id"]
        if attendee_id in self.attendee_items:
            oval_id, text_id = self.attendee_items[attendee_id]
            self.move(oval_id, dx, dy)
            self.move(text_id, dx, dy)

        self.drag["x"], self.drag["y"] = x, y
        return "break"

    def end_attendee_drag(self, e, attendee, attendee_id):
        """
        Assign to new table ONLY if attendee circle overlaps the target table circle (area overlap).
        Uses actual attendee circle bbox center (not mouse coords).
        """
        drag_ctx = self.drag
        self.drag = None

        if not drag_ctx or drag_ctx.get("type") != "attendee":
            return "break"

        old_table = drag_ctx["table"]

        # Compute attendee circle center from its current bbox (true position)
        if attendee_id not in self.attendee_items:
            self.draw()
            return "break"

        oval_id, _text_id = self.attendee_items[attendee_id]
        x1, y1, x2, y2 = self.coords(oval_id)
        ax = (x1 + x2) / 2.0
        ay = (y1 + y2) / 2.0

        # Find first table with which attendee circle overlaps (circle-circle intersection)
        # If multiple overlap, choose the one with maximum overlap "depth" (closest center)
        best_table = None
        best_dist = None

        for table, (tx, ty) in self.model.table_positions.items():
            if table in (SPECIAL_TABLE, old_table):
                continue  # do not drop into special table; old table doesn't change assignment

            # only circular tables are valid drop targets
            px, py = self.m2px(tx), self.m2px(ty)

            dist = math.hypot(ax - px, ay - py)
            if dist < (ATT_R_PX + TABLE_R_PX):
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_table = table

        if best_table and best_table != old_table:
            # Remove & add in the model
            try:
                self.model.tables[old_table].remove(attendee)
            except ValueError:
                # In case attendee ordering changed, remove by id
                self.model.tables[old_table] = [g for g in self.model.tables[old_table] if g.get("_id") != attendee_id]

            self.model.tables[best_table].append(attendee)

        # redraw to re-orbit the guests around their tables (legend is redrawn too)
        self.draw()
        return "break"



# ======================================================
# Viewer Tab
# ======================================================

class ViewerTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        ttk.Button(self, text="Load seating JSON", command=self.load).pack(anchor="w", padx=6, pady=6)
        self.text = tk.Text(self, wrap="word", bg="#111111", fg="#ffffff", insertbackground="#ffffff")
        self.text.pack(fill="both", expand=True, padx=6, pady=6)

    def load(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", f.read())


# ======================================================
# Main App
# ======================================================

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Wedding Seating Planner")
        self.geometry("1050x700")

        self.model = SeatingModel()
        if not self.model.load_seating():
            # fallback generation
            try:
                self.model.generate_from_attendees(os.path.join(os.path.dirname(__file__), "attendees.json"))
            except Exception as e:
                messagebox.showerror("Startup error", f"Cannot start:\n{e}")
                raise

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        # Top controls
        top = ttk.Frame(self)
        top.pack(fill="x")

        ttk.Button(top, text="Reset Layout", command=self.on_reset).pack(side="right", padx=8, pady=8)

        # Tabs
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)

        # Planner tab
        planner_frame = ttk.Frame(tabs)
        planner_frame.pack(fill="both", expand=True)

        self.canvas = PlannerCanvas(planner_frame, self.model)

        hbar = ttk.Scrollbar(planner_frame, orient="horizontal", command=self.canvas.xview)
        vbar = ttk.Scrollbar(planner_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")

        planner_frame.rowconfigure(0, weight=1)
        planner_frame.columnconfigure(0, weight=1)

        # Viewer tab
        viewer = ViewerTab(tabs)

        tabs.add(planner_frame, text="Planner")
        tabs.add(viewer, text="Viewer")

    def on_reset(self):
        self.model.reset_layout()
        self.canvas.draw()

    def on_close(self):
        self.model.save_json("seating_arrangement.json")
        self.model.save_csv("seating_arrangement.csv")
        self.destroy()


if __name__ == "__main__":
    App().mainloop()