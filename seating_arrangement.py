import json
import csv
import math
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import uuid
import os
import random
import logging

# ======================================================
# Configuration
# ======================================================

class Config:
    ROOM_L: float = 30.0
    ROOM_H: float = 15.0
    PIXELS_PER_METER: int = 60
    VIEWPORT_W: int = 950
    VIEWPORT_H: int = 600
    SEATS_WARNING_LIMIT: int = 10
    SEATS_PER_TABLE: int = 10
    SPECIAL_TABLE: str = "Bride & Groom"
    RELATIONSHIPS: list = [
        "Bride", "Groom", "Immediate Family", "Extended Family",
        "Childhood Friends", "UniversityFriends", "Colleagues"
    ]
    TABLE_R_PX: int = 40
    ATT_R_PX: int = 10
    ORBIT_R_PX: int = 85
    SPECIAL_W_PX: int = 220
    SPECIAL_H_PX: int = 70
    CANVAS_BG: str = "#000000"
    CANVAS_BG_RGB: tuple = (0, 0, 0)
    MIN_ALPHA: float = 0.25
    MAX_ALPHA: float = 1.00
    DEFAULT_FOOD_ALLERGY: str = "none"
    DEFAULT_PLUS_ONE_NAME: str = "AnyRandom"

ROOM_L = Config.ROOM_L
ROOM_H = Config.ROOM_H
PIXELS_PER_METER = Config.PIXELS_PER_METER
CANVAS_W = int(ROOM_L * PIXELS_PER_METER)
CANVAS_H = int(ROOM_H * PIXELS_PER_METER)
VIEWPORT_W = Config.VIEWPORT_W
VIEWPORT_H = Config.VIEWPORT_H
SEATS_WARNING_LIMIT = Config.SEATS_WARNING_LIMIT
SEATS_PER_TABLE = Config.SEATS_PER_TABLE
SPECIAL_TABLE = Config.SPECIAL_TABLE
RELATIONSHIPS = Config.RELATIONSHIPS
TABLE_R_PX = Config.TABLE_R_PX
ATT_R_PX = Config.ATT_R_PX
ORBIT_R_PX = Config.ORBIT_R_PX
SPECIAL_W_PX = Config.SPECIAL_W_PX
SPECIAL_H_PX = Config.SPECIAL_H_PX
CANVAS_BG = Config.CANVAS_BG
CANVAS_BG_RGB = Config.CANVAS_BG_RGB
MIN_ALPHA = Config.MIN_ALPHA
MAX_ALPHA = Config.MAX_ALPHA


def normalize_food_allergy_value(raw_value) -> str:
    """Return canonical allergy string from scalar or legacy object shapes."""
    default_value = Config.DEFAULT_FOOD_ALLERGY
    if isinstance(raw_value, dict):
        # Backward compatibility with prior track/override format.
        override = str(raw_value.get("override", "")).strip()
        track = str(raw_value.get("track", default_value)).strip() or default_value
        return override if override else track
    if raw_value is None:
        return default_value
    value = str(raw_value).strip()
    return value or default_value


def normalize_plus_one(attendee: dict) -> list:
    """Normalize plus-one details into a list of guest objects."""
    raw_plus_one = attendee.get("plus_one", [])
    normalized = []

    if isinstance(raw_plus_one, int):
        # Backward compatibility: numeric plus_one means count only.
        raw_plus_one = [{"name": Config.DEFAULT_PLUS_ONE_NAME} for _ in range(max(0, raw_plus_one))]
    elif not isinstance(raw_plus_one, list):
        raw_plus_one = []

    # Backward compatibility: plus_one_count field from previous schema.
    if not raw_plus_one and "plus_one_count" in attendee:
        try:
            count = max(0, int(attendee.get("plus_one_count", 0)))
        except (TypeError, ValueError):
            count = 0
        raw_plus_one = [{"name": Config.DEFAULT_PLUS_ONE_NAME} for _ in range(count)]

    max_plus_ones = max(0, Config.SEATS_PER_TABLE - 1)
    raw_plus_one = raw_plus_one[:max_plus_ones]

    for item in raw_plus_one:
        if isinstance(item, dict):
            name = str(item.get("name", Config.DEFAULT_PLUS_ONE_NAME)).strip() or Config.DEFAULT_PLUS_ONE_NAME
            allergy = normalize_food_allergy_value(item.get("food_allergy", Config.DEFAULT_FOOD_ALLERGY))
            pid = item.get("_id") or uuid.uuid4().hex
        else:
            name = Config.DEFAULT_PLUS_ONE_NAME
            allergy = Config.DEFAULT_FOOD_ALLERGY
            pid = uuid.uuid4().hex
        normalized.append({
            "name": name,
            "food_allergy": allergy,
            "_id": pid,
            "side": attendee.get("side", ""),
            "category": attendee.get("category", 6),
            "relationship": "PlusOne"
        })

    attendee["plus_one"] = normalized
    if "plus_one_count" in attendee:
        del attendee["plus_one_count"]
    return attendee["plus_one"]


def normalize_food_allergy(attendee: dict) -> str:
    """Normalize attendee allergy to canonical scalar string."""
    attendee["food_allergy"] = normalize_food_allergy_value(attendee.get("food_allergy", Config.DEFAULT_FOOD_ALLERGY))
    if "food_allergy_override" in attendee:
        del attendee["food_allergy_override"]
    return attendee["food_allergy"]


def attendee_headcount(attendee: dict) -> int:
    """Return attendee seats needed: one attendee seat plus declared +1 seats."""
    return 1 + len(normalize_plus_one(attendee))


def effective_food_allergy(attendee: dict) -> str:
    """Return normalized allergy string for attendee."""
    return normalize_food_allergy(attendee)

# ======================================================
# Utilities
# ======================================================

def clamp(v: float, lo: float, hi: float) -> float:
    """Clamp value v between lo and hi."""
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

def atomic_write_csv(path: str, rows: list):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        for row in rows:
            w.writerow(row)
    os.replace(tmp, path)

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

    def table_headcount(self, guests: list) -> int:
        """Return total seats consumed at a table including +1 seats."""
        return sum(attendee_headcount(g) for g in guests)

    def split_group_by_capacity(self, attendees: list, max_heads: int) -> list:
        """Split attendees into sequential chunks that fit table headcount capacity."""
        chunks = []
        current = []
        current_heads = 0

        for attendee in attendees:
            heads = attendee_headcount(attendee)
            if current and current_heads + heads > max_heads:
                chunks.append(current)
                current = [attendee]
                current_heads = heads
            else:
                current.append(attendee)
                current_heads += heads

        if current:
            chunks.append(current)
        return chunks

    def load_seating(self, path="seating_arrangement.json"):
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.table_positions = raw.pop("_table_positions", {})
            self.tables = raw
            for k, v in list(self.table_positions.items()):
                if isinstance(v, list) and len(v) == 2:
                    self.table_positions[k] = (float(v[0]), float(v[1]))
            self._normalize_all_attendees()
            self._ensure_special_table_position()
            self._ensure_non_special_tables_below_special()
            missing = [t for t in self.tables.keys() if t not in self.table_positions]
            if missing:
                self.reset_layout()
            self.enforce_table_capacity()
            return True
        except Exception as e:
            messagebox.showerror("Load error", f"Failed to load seating:\n{e}")
            return False

    def save_json(self, path="seating_arrangement.json"):
        data = dict(self.tables)
        data["_table_positions"] = {k: [float(x), float(y)] for k, (x, y) in self.table_positions.items()}
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def save_csv(self, path="seating_arrangement.csv"):
        rows = [["Table", "Guest", "Relationship", "Category", "PlusOneCount", "FoodAllergy", "PlusOneNames"]]
        for t, guests in self.tables.items():
            for g in guests:
                plus_ones = normalize_plus_one(g)
                rows.append([
                    t,
                    g.get("name", ""),
                    g.get("relationship", ""),
                    g.get("category", ""),
                    len(plus_ones),
                    effective_food_allergy(g),
                    "|".join(p.get("name", "") for p in plus_ones),
                ])
        atomic_write_csv(path, rows)

    def _normalize_all_attendees(self):
        attendees = [a for guests in self.tables.values() for a in guests]
        if not attendees:
            return
        for a in attendees:
            # Ensure all required fields
            a.setdefault("name", "Guest")
            a.setdefault("side", "")
            a.setdefault("category", 6)
            a.setdefault("relationship", "Colleagues")
            a.setdefault("plus_one", [])
            a.setdefault("food_allergy", Config.DEFAULT_FOOD_ALLERGY)
            ensure_attendee_id(a)
            normalize_plus_one(a)
            normalize_food_allergy(a)
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
        for a in attendees:
            rel = a.get("relationship", "Colleagues")
            if rel not in RELATIONSHIPS:
                rel = "Colleagues"
                a["relationship"] = rel
            a["category"] = RELATIONSHIPS.index(rel)
        if SPECIAL_TABLE not in self.tables:
            self.tables[SPECIAL_TABLE] = []
        def remove_from_all(att):
            for t in list(self.tables.keys()):
                if att in self.tables[t]:
                    self.tables[t].remove(att)
        if bride:
            remove_from_all(bride)
        if groom:
            remove_from_all(groom)
        self.tables[SPECIAL_TABLE] = []
        if bride:
            self.tables[SPECIAL_TABLE].append(bride)
        if groom:
            self.tables[SPECIAL_TABLE].append(groom)

    def _ensure_special_table_position(self):
        cx = ROOM_L / 2.0
        cy = 1.5
        self.table_positions[SPECIAL_TABLE] = (cx, cy)

    def _special_bottom_y_m(self):
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

    def generate_from_attendees(self, path="attendees.json"):
        if not os.path.exists(path):
            raise FileNotFoundError(f"Missing {path}")
        with open(path, "r", encoding="utf-8") as f:
            root = json.load(f)
        raw = root.get("attendees", [])
        if not isinstance(raw, list) or not raw:
            raise ValueError("attendees.json must contain a non-empty 'attendees' list")
        for a in raw:
            ensure_attendee_id(a)
            normalize_plus_one(a)
            normalize_food_allergy(a)
        # Find bride and groom based on category 1
        category_1_attendees = [a for a in raw if a.get("category") == 1]
        if len(category_1_attendees) < 2:
            raise ValueError("attendees.json must contain at least 2 attendees with category 1 for bride and groom")
        bride = category_1_attendees[0]
        groom = category_1_attendees[1]
        bride["relationship"] = "Bride"
        groom["relationship"] = "Groom"
        # Remove bride and groom from raw list
        raw = [a for a in raw if a not in category_1_attendees]
        for a in raw:
            if a.get("relationship") not in RELATIONSHIPS:
                a["relationship"] = random.choice(RELATIONSHIPS[2:])
        for a in [bride, groom] + raw:
            a["category"] = 1 if a["relationship"] in ("Bride", "Groom") else RELATIONSHIPS.index(a["relationship"])
            normalize_plus_one(a)
            normalize_food_allergy(a)
        # Group by relationship (except Bride/Groom)
        groups = {}
        for a in raw:
            groups.setdefault(a["relationship"], []).append(a)
        self.tables = {SPECIAL_TABLE: [bride, groom]}
        idx = 1
        for rel in RELATIONSHIPS[2:]:
            if rel in groups:
                attendees = groups[rel]
                # Split by total headcount so +1 attendees can spill into additional tables.
                chunks = self.split_group_by_capacity(attendees, SEATS_PER_TABLE)
                for chunk in chunks:
                    self.tables[f"Table {idx}"] = chunk
                    idx += 1
        self._ensure_special_table_position()
        self.reset_layout()
        # Do NOT call enforce_table_capacity here!

    def reset_layout(self):
        self._normalize_all_attendees()
        self._ensure_special_table_position()
        min_y = self._special_bottom_y_m()
        others = [t for t in self.tables.keys() if t != SPECIAL_TABLE]
        def table_priority(t):
            guests = self.tables[t]
            if not guests:
                return 999
            return min(g.get("category", 999) for g in guests)
        others.sort(key=table_priority)
        cx = ROOM_L / 2.0
        cols = 4
        x_spacing_m = 4.2
        y_spacing_m = 2.6
        for i, t in enumerate(others):
            row = i // cols
            col = i % cols
            x = cx + (col - (cols - 1) / 2) * x_spacing_m
            y = min_y + row * y_spacing_m
            x = clamp(x, 2.0, ROOM_L - 2.0)
            y = clamp(y, min_y, ROOM_H - 2.0)
            self.table_positions[t] = (x, y)
        self._ensure_non_special_tables_below_special()

    def enforce_table_capacity(self):
        for t, guests in self.tables.items():
            if t != Config.SPECIAL_TABLE and self.table_headcount(guests) > Config.SEATS_PER_TABLE:
                logging.error(f"Table '{t}' exceeds the maximum of {Config.SEATS_PER_TABLE} seats (including +1s).")
                messagebox.showerror(
                    "Table Capacity Exceeded",
                    f"Table '{t}' has more than {Config.SEATS_PER_TABLE} seats when +1s are included.\n"
                    "Please delete 'seating_arrangement.json' and restart the application."
                )
                raise RuntimeError("Table capacity exceeded.")

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
        self.drag = None
        self.attendee_items = {}
        self.search_string = ""
        self.legend_positions = {}  # table -> (x, y)
        self.draw()

    def m2px(self, v):
        return v * PIXELS_PER_METER

    def _find_attendee(self, attendee_id: str):
        """Locate attendee and its table using attendee id."""
        for table_name, guests in self.model.tables.items():
            for guest in guests:
                if guest.get("_id") == attendee_id:
                    return table_name, guest
        return None, None

    def _open_attendee_editor(self, attendee_id: str):
        """Open popup editor for attendee food allergy and plus-one entries."""
        table_name, attendee = self._find_attendee(attendee_id)
        if not attendee:
            messagebox.showerror("Edit attendee", "Attendee not found.")
            return

        normalize_food_allergy(attendee)
        normalize_plus_one(attendee)

        popup = tk.Toplevel(self)
        popup.title("Edit Attendee")
        popup.transient(self.winfo_toplevel())
        popup.resizable(False, False)
        # Fix: wait for visibility before grab_set
        popup.update_idletasks()
        popup.wait_visibility()
        popup.grab_set()

        frame = ttk.Frame(popup, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"Guest: {attendee.get('name', '')}", font=("Arial", 10, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8)
        )

        ttk.Label(frame, text="Food allergy:").grid(row=1, column=0, sticky="w")
        attendee_allergy_var = tk.StringVar(value=attendee.get("food_allergy", Config.DEFAULT_FOOD_ALLERGY))
        ttk.Entry(frame, textvariable=attendee_allergy_var, width=30).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=(6, 0)
        )

        ttk.Label(frame, text="Plus-ones").grid(row=2, column=0, sticky="w", pady=(10, 4))
        plus_list = tk.Listbox(frame, height=6, width=48)
        plus_list.grid(row=3, column=0, columnspan=3, sticky="ew")

        ttk.Label(frame, text="Name").grid(row=4, column=0, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="Food allergy").grid(row=4, column=1, sticky="w", pady=(8, 0))

        plus_name_var = tk.StringVar(value=Config.DEFAULT_PLUS_ONE_NAME)
        plus_food_var = tk.StringVar(value=Config.DEFAULT_FOOD_ALLERGY)
        ttk.Entry(frame, textvariable=plus_name_var, width=20).grid(row=5, column=0, sticky="ew", padx=(0, 6))
        ttk.Entry(frame, textvariable=plus_food_var, width=20).grid(row=5, column=1, sticky="ew", padx=(0, 6))

        working_plus_ones = [dict(p) for p in attendee.get("plus_one", [])]

        def refresh_plus_ones():
            plus_list.delete(0, tk.END)
            for index, plus_one in enumerate(working_plus_ones, start=1):
                plus_list.insert(
                    tk.END,
                    f"{index}. {plus_one.get('name', Config.DEFAULT_PLUS_ONE_NAME)} | {plus_one.get('food_allergy', Config.DEFAULT_FOOD_ALLERGY)}"
                )

        def selected_index():
            selection = plus_list.curselection()
            return selection[0] if selection else None

        def load_selected(_event=None):
            idx = selected_index()
            if idx is None:
                return
            item = working_plus_ones[idx]
            plus_name_var.set(item.get("name", Config.DEFAULT_PLUS_ONE_NAME))
            plus_food_var.set(item.get("food_allergy", Config.DEFAULT_FOOD_ALLERGY))

        def add_or_update_plus_one():
            plus_one_item = {
                "name": plus_name_var.get().strip() or Config.DEFAULT_PLUS_ONE_NAME,
                "food_allergy": plus_food_var.get().strip() or Config.DEFAULT_FOOD_ALLERGY,
            }
            idx = selected_index()
            if idx is None:
                working_plus_ones.append(plus_one_item)
            else:
                working_plus_ones[idx] = plus_one_item
            refresh_plus_ones()

        def remove_plus_one():
            idx = selected_index()
            if idx is None:
                return
            del working_plus_ones[idx]
            refresh_plus_ones()
            plus_name_var.set(Config.DEFAULT_PLUS_ONE_NAME)
            plus_food_var.set(Config.DEFAULT_FOOD_ALLERGY)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=5, column=2, sticky="e")
        ttk.Button(button_frame, text="Add/Update", command=add_or_update_plus_one).pack(side="left", padx=(0, 6))
        ttk.Button(button_frame, text="Remove", command=remove_plus_one).pack(side="left")

        plus_list.bind("<<ListboxSelect>>", load_selected)

        def save_changes():
            original_allergy = attendee.get("food_allergy", Config.DEFAULT_FOOD_ALLERGY)
            original_plus_one = [dict(p) for p in attendee.get("plus_one", [])]

            attendee["food_allergy"] = attendee_allergy_var.get().strip() or Config.DEFAULT_FOOD_ALLERGY
            attendee["plus_one"] = working_plus_ones[:max(0, Config.SEATS_PER_TABLE - 1)]
            normalize_food_allergy(attendee)
            normalize_plus_one(attendee)

            if table_name != SPECIAL_TABLE and self.model.table_headcount(self.model.tables.get(table_name, [])) > SEATS_PER_TABLE:
                attendee["food_allergy"] = original_allergy
                attendee["plus_one"] = original_plus_one
                messagebox.showwarning(
                    "Table Capacity",
                    f"Saving this change would exceed {SEATS_PER_TABLE} seats for '{table_name}'."
                )
                return

            popup.destroy()
            self.draw()

        actions = ttk.Frame(frame)
        actions.grid(row=6, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(actions, text="Cancel", command=popup.destroy).pack(side="right")
        ttk.Button(actions, text="Save", command=save_changes).pack(side="right", padx=(0, 6))

        refresh_plus_ones()

    def open_attendee_editor_from_event(self, event):
        """Open editor when attendee circle is right-clicked (Button-3)."""
        current = self.find_withtag("current")
        if not current:
            return "break"
        tags = self.gettags(current[0])
        attendee_tag = next((tag for tag in tags if tag.startswith("attendee:")), None)
        if not attendee_tag:
            return "break"
        attendee_id = attendee_tag.split(":", 1)[1]
        self._open_attendee_editor(attendee_id)
        return "break"

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
            if rel in ("Immediate Family", "Extended Family"):
                fg = (255, 40, 40)
            else:
                fg = (40, 140, 255)
        rgb = blend_rgb(CANVAS_BG_RGB, fg, alpha)
        return rgb_to_hex(rgb)

    def draw_highlighted_text(self, x, y, text, font, fill, highlight_fill, tags):
        """Draw text with highlighting for search string. Returns list of text ids."""
        ids = []
        if not self.search_string:
            id_ = self.create_text(x, y, text=text, fill=fill, font=font, tags=tags, anchor="w")
            ids.append(id_)
            return ids
        search_lower = self.search_string.lower()
        text_lower = text.lower()
        start = text_lower.find(search_lower)
        if start == -1:
            id_ = self.create_text(x, y, text=text, fill=fill, font=font, tags=tags, anchor="w")
            ids.append(id_)
            return ids
        end = start + len(self.search_string)
        # Draw parts
        current_x = x
        # Before match
        if start > 0:
            before = text[:start]
            id_ = self.create_text(current_x, y, text=before, fill=fill, font=font, tags=tags, anchor="w")
            ids.append(id_)
            current_x += self.font_measure(before, font)
        # Match
        match = text[start:end]
        id_ = self.create_text(current_x, y, text=match, fill=highlight_fill, font=font, tags=tags, anchor="w")
        ids.append(id_)
        current_x += self.font_measure(match, font)
        # After match
        if end < len(text):
            after = text[end:]
            id_ = self.create_text(current_x, y, text=after, fill=fill, font=font, tags=tags, anchor="w")
            ids.append(id_)
        return ids

    def font_measure(self, text, font):
        """Approximate width of text in pixels. Since canvas doesn't have measure, use len * 8 as rough estimate."""
        # For Arial 8, approx 6-7 px per char
        return len(text) * 7

    def draw(self):
        self.delete("all")
        self.attendee_items.clear()
        self.create_rectangle(
            5, 5, CANVAS_W - 5, CANVAS_H - 5,
            outline="#333333", width=2
        )
        legend_x = 12
        legend_y = 12
        legend_w = 220
        line_h = 18
        legend_bg = "#111111"
        legend_border = "#333333"
        total_lines = 1 + sum(1 + min(len(guests), 8) for guests in self.model.tables.values())
        legend_height = legend_y - 16 + total_lines * line_h + 6
        self.create_rectangle(
            legend_x - 16, legend_y - 16,
            legend_x + legend_w, legend_height,
            fill=legend_bg, outline=legend_border, width=1
        )
        self.create_text(legend_x, legend_y - 2, text="Legend (by table colors)",
                          fill="#ffffff", font=("Arial", 10, "bold"), anchor="nw")
        sorted_tables = sorted(self.model.tables.keys())
        for idx, table in enumerate(sorted_tables):
            guests = self.model.tables.get(table, [])
            default_x = legend_x
            default_y = legend_y + (idx*5 + 1) * line_h
            base_x, base_y = self.legend_positions.get(table, (default_x, default_y))
            rep = guests[0] if guests else None
            header_color = self.attendee_color(rep) if rep else "#666666"
            rect_id = self.create_rectangle(
                base_x, base_y, base_x + 14, base_y + 14,
                fill=header_color, outline="#ffffff", width=1,
                tags=(f"legend_group:{table}", f"legend_table:{table}")
            )
            self.create_text(
                base_x + 22, base_y + 7,
                text=f"{table}",
                fill="#ffffff", font=("Arial", 9), anchor="w",
                tags=(f"legend_group:{table}",)
            )
            for j, a in enumerate(guests[:8]):
                c = self.attendee_color(a)
                y = base_y + 16 + j * 14
                oval_id = self.create_rectangle(
                    base_x + 22, y - 2,
                    base_x + 34, y + 10,
                    fill=c, outline="#ffffff", width=1,
                    tags=(f"legend_group:{table}", f"legend_attendee:{table}:{ensure_attendee_id(a)}")
                )
                self.create_text(
                    base_x + 40, y + 4,
                    text=a.get("name", ""),
                    fill="#ffffff", font=("Arial", 7), anchor="w",
                    tags=(f"legend_group:{table}",)
                )
                # Bind drag for legend attendee
                self.tag_bind(f"legend_attendee:{table}:{ensure_attendee_id(a)}", "<ButtonPress-1>",
                              lambda e, t=table, aid=ensure_attendee_id(a): self.start_legend_attendee_drag(e, t, aid))
                self.tag_bind(f"legend_attendee:{table}:{ensure_attendee_id(a)}", "<B1-Motion>", self.drag_legend_attendee)
                self.tag_bind(f"legend_attendee:{table}:{ensure_attendee_id(a)}", "<ButtonRelease-1>", self.end_legend_attendee_drag)
            # Bind drag for legend table
            self.tag_bind(f"legend_table:{table}", "<ButtonPress-1>",
                          lambda e, t=table: self.start_legend_table_drag(e, t))
            self.tag_bind(f"legend_table:{table}", "<B1-Motion>", self.drag_legend_table)
            self.tag_bind(f"legend_table:{table}", "<ButtonRelease-1>", self.end_legend_table_drag)
        for table, guests in self.model.tables.items():
            tx, ty = self.model.table_positions.get(table, (ROOM_L / 2, ROOM_H / 2))
            px, py = self.m2px(tx), self.m2px(ty)
            group_tag = f"group:{table}"
            handle_tag = f"handle:{table}"
            if table == SPECIAL_TABLE:
                w, h = SPECIAL_W_PX, SPECIAL_H_PX
                self.create_rectangle(
                    px - w / 2, py - h / 2, px + w / 2, py + h / 2,
                    fill="#222222", outline="#f5d76e", width=2,
                    tags=(group_tag, handle_tag)
                )
                label_color = "#ffffff"
            else:
                warn = self.model.table_headcount(guests) > SEATS_WARNING_LIMIT
                fill = "#a40000" if warn else "#111111"
                self.create_oval(
                    px - TABLE_R_PX, py - TABLE_R_PX, px + TABLE_R_PX, py + TABLE_R_PX,
                    fill=fill, outline="#aaaaaa", width=2,
                    tags=(group_tag, handle_tag)
                )
                label_color = "#ffffff"
            # --- WRAP TABLE LABEL TEXT ---
            label_text = f"{table} ({len(guests)} guests/{self.model.table_headcount(guests)} heads)"
            # Split label_text into lines if too long
            max_label_len = 22
            label_lines = []
            while len(label_text) > max_label_len:
                split_at = label_text.rfind(' ', 0, max_label_len)
                if split_at == -1:
                    split_at = max_label_len
                label_lines.append(label_text[:split_at])
                label_text = label_text[split_at:].lstrip()
            label_lines.append(label_text)
            for idx, line in enumerate(label_lines):
                self.create_text(
                    px, py - 10 + idx*16,
                    text=line,
                    fill=label_color,
                    font=("Arial", 11, "bold"),
                    tags=(group_tag, handle_tag)
                )
            if table != SPECIAL_TABLE:
                self.tag_bind(handle_tag, "<ButtonPress-1>",
                              lambda e, t=table: self.start_table_drag(e, t))
                self.tag_bind(handle_tag, "<B1-Motion>", self.drag_table)
                self.tag_bind(handle_tag, "<ButtonRelease-1>", self.end_table_drag)
            # Only render main invitees (not plus-ones) as table guests
            # Build set of all plus-one IDs for this table
            plusone_ids = set()
            for g in guests:
                for p in g.get("plus_one", []):
                    if "_id" not in p:
                        p["_id"] = uuid.uuid4().hex
                    plusone_ids.add(p["_id"])
            # Filter guests_sorted to only main invitees
            guests_sorted = [g for g in sorted(guests, key=lambda g: (int(g.get("category", 99)), g.get("name", ""))) if g.get("_id") not in plusone_ids]
            n = len(guests_sorted)
            # --- Render main invitees and plus-ones visually ---
            for i, g in enumerate(guests_sorted):
                aid = ensure_attendee_id(g)
                ang = 2 * math.pi * i / max(1, n)
                gx = px + math.cos(ang) * ORBIT_R_PX
                gy = py + math.sin(ang) * ORBIT_R_PX
                color = self.attendee_color(g)
                r = ATT_R_PX
                oval_id = self.create_oval(
                    gx - r, gy - r, gx + r, gy + r,
                    fill=color, outline="#ffffff", width=1,
                    tags=(group_tag, f"attendee:{aid}", "attendee")
                )
                text_ids = self.draw_highlighted_text(
                    gx, gy + 18,
                    g.get("name", ""),
                    ("Arial", 8),
                    "#ffffff",
                    "#ffff00",
                    (group_tag, f"attendee:{aid}", "attendee_label")
                )
                self.attendee_items[aid] = (oval_id, text_ids)
                # Draw plus-ones for this main invitee
                plus_ones = g.get("plus_one", [])
                n_plus = len(plus_ones)
                for j, p in enumerate(plus_ones):
                    pid = ensure_attendee_id(p)
                    pang = ang + (j - (n_plus-1)/2) * (math.pi/8)
                    pr = ORBIT_R_PX + 35
                    pgx = px + math.cos(pang) * pr
                    pgy = py + math.sin(pang) * pr
                    # Draw line from main to plus-one
                    self.create_line(gx, gy, pgx, pgy, fill="#bbbbbb", width=1)
                    # Draw plus-one circle
                    oval_id_p = self.create_oval(
                        pgx - ATT_R_PX//2, pgy - ATT_R_PX//2, pgx + ATT_R_PX//2, pgy + ATT_R_PX//2,
                        fill=self.attendee_color(p), outline="#ffffff", width=1,
                        tags=(group_tag, f"attendee:{pid}", "attendee", "plusone")
                    )
                    text_ids_p = self.draw_highlighted_text(
                        pgx, pgy + 10,
                        p.get("name", ""),
                        ("Arial", 7),
                        "#ffffff",
                        "#ffff00",
                        (group_tag, f"attendee:{pid}", "attendee_label", "plusone_label")
                    )
                    self.attendee_items[pid] = (oval_id_p, text_ids_p)
                    # Bind right-click for editing
                    self.tag_bind(f"attendee:{pid}", "<Button-3>", self.open_attendee_editor_from_event)
                # Bindings for main invitee
                self.tag_bind(f"attendee:{aid}", "<ButtonPress-1>",
                              lambda e, t=table, a=g, attendee_id=aid: self.start_attendee_drag(e, t, a, attendee_id))
                self.tag_bind(f"attendee:{aid}", "<B1-Motion>", self.drag_attendee)
                self.tag_bind(f"attendee:{aid}", "<ButtonRelease-1>",
                              lambda e, a=g, attendee_id=aid: self.end_attendee_drag(e, a, attendee_id))
                self.tag_bind(f"attendee:{aid}", "<Button-3>", self.open_attendee_editor_from_event)
        self.configure(scrollregion=self.bbox("all"))

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
        min_y = self.model._special_bottom_y_m()
        y = max(y, min_y)
        x = clamp(x, 2.0, ROOM_L - 2.0)
        y = clamp(y, min_y, ROOM_H - 2.0)
        self.model.table_positions[table] = (x, y)
        self.drag = None
        return "break"

    def start_legend_table_drag(self, e, table):
        self.drag = {
            "type": "legend_table",
            "table": table,
            "x": self.canvasx(e.x),
            "y": self.canvasy(e.y)
        }
        return "break"

    def drag_legend_table(self, e):
        if not self.drag or self.drag.get("type") != "legend_table":
            return "break"
        x = self.canvasx(e.x)
        y = self.canvasy(e.y)
        dx = x - self.drag["x"]
        dy = y - self.drag["y"]
        # Removed: self.move(f"group:{self.drag['table']}", dx, dy)
        self.drag["x"], self.drag["y"] = x, y
        return "break"

    def start_legend_attendee_drag(self, e, table, attendee_id):
        self.drag = {
            "type": "legend_attendee",
            "table": table,
            "attendee_id": attendee_id,
            "x": self.canvasx(e.x),
            "y": self.canvasy(e.y)
        }
        return "break"

    def drag_legend_attendee(self, e):
        if not self.drag or self.drag.get("type") != "legend_attendee":
            return "break"
        # Do nothing for visual feedback, since legend redraws
        return "break"

    def end_legend_attendee_drag(self, e):
        drag_ctx = self.drag
        self.drag = None
        if not drag_ctx or drag_ctx.get("type") != "legend_attendee":
            return "break"
        old_table = drag_ctx["table"]
        attendee_id = drag_ctx["attendee_id"]
        # Find the attendee
        attendee = None
        for g in self.model.tables.get(old_table, []):
            if g.get("_id") == attendee_id:
                attendee = g
                break
        if not attendee:
            return "break"
        # Check if dropped on a table
        x = self.canvasx(e.x)
        y = self.canvasy(e.y)
        best_table = None
        best_dist = None
        for table, (tx, ty) in self.model.table_positions.items():
            if table == old_table:
                continue
            px, py = self.m2px(tx), self.m2px(ty)
            dist = math.hypot(x - px, y - py)
            if dist < (ATT_R_PX + TABLE_R_PX):
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_table = table
        if best_table:
            # Move attendee to best_table
            try:
                self.model.tables[old_table].remove(attendee)
            except ValueError:
                self.model.tables[old_table] = [g for g in self.model.tables[old_table] if g.get("_id") != attendee_id]
            projected = self.model.table_headcount(self.model.tables[best_table]) + attendee_headcount(attendee)
            if projected <= SEATS_PER_TABLE:
                self.model.tables[best_table].append(attendee)
            else:
                messagebox.showwarning(
                    "Table Full",
                    f"Cannot move attendee: '{best_table}' would exceed {SEATS_PER_TABLE} seats with +1s."
                )
                self.model.tables[old_table].append(attendee)
        self.draw()
        return "break"

    def start_legend_table_drag(self, e, table):
        self.drag = {
            "type": "legend_table",
            "table": table,
            "x": self.canvasx(e.x),
            "y": self.canvasy(e.y)
        }
        return "break"

    def drag_legend_table(self, e):
        if not self.drag or self.drag.get("type") != "legend_table":
            return "break"
        x = self.canvasx(e.x)
        y = self.canvasy(e.y)
        dx = x - self.drag["x"]
        dy = y - self.drag["y"]
        self.move(f"legend_group:{self.drag['table']}", dx, dy)
        self.drag["x"], self.drag["y"] = x, y
        return "break"

    def end_legend_table_drag(self, e):
        if not self.drag or self.drag.get("type") != "legend_table":
            self.drag = None
            return "break"
        table = self.drag["table"]
        x = self.canvasx(e.x)
        y = self.canvasy(e.y)
        # Update position
        self.legend_positions[table] = (x - 7, y - 7)  # Adjust for the rect center
        self.drag = None
        return "break"

    def start_attendee_drag(self, e, table, attendee, attendee_id):
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
            oval_id, text_ids = self.attendee_items[attendee_id]
            self.move(oval_id, dx, dy)
            for tid in text_ids:
                self.move(tid, dx, dy)
        self.drag["x"], self.drag["y"] = x, y
        return "break"

    def end_attendee_drag(self, e, attendee, attendee_id):
        drag_ctx = self.drag
        self.drag = None
        if not drag_ctx or drag_ctx.get("type") != "attendee":
            return "break"
        old_table = drag_ctx["table"]
        if attendee_id not in self.attendee_items:
            self.draw()
            return "break"
        oval_id, _text_id = self.attendee_items[attendee_id]
        x1, y1, x2, y2 = self.coords(oval_id)
        ax = (x1 + x2) / 2.0
        ay = (y1 + y2) / 2.0
        best_table = None
        best_dist = None
        for table, (tx, ty) in self.model.table_positions.items():
            if table in (SPECIAL_TABLE, old_table):
                continue
            px, py = self.m2px(tx), self.m2px(ty)
            dist = math.hypot(ax - px, ay - py)
            if dist < (ATT_R_PX + TABLE_R_PX):
                if best_dist is None or dist < best_dist:
                    best_dist = dist
                    best_table = table
        # --- PLUS-ONE CO-LOCATION RULE ---
        # Check if attendee is a plus-one (find main invitee in all tables)
        is_plus_one = False
        main_invitee = None
        for t, guests in self.model.tables.items():
            for g in guests:
                for p in g.get("plus_one", []):
                    if p.get("_id", None) == attendee_id:
                        is_plus_one = True
                        main_invitee = g
                        break
                if is_plus_one:
                    break
            if is_plus_one:
                break
        # If moving a plus-one, prevent moving to a different table than main invitee
        if is_plus_one and best_table and best_table != old_table:
            # Find which table main_invitee is in
            main_table = None
            for t, guests in self.model.tables.items():
                if main_invitee in guests:
                    main_table = t
                    break
            if main_table and best_table != main_table:
                messagebox.showwarning(
                    "Plus-One Rule",
                    "Cannot move a plus-one to a different table than their main invitee."
                )
                self.draw()
                return "break"
        # If moving a main invitee, move all their plus-ones with them
        if not is_plus_one and best_table and best_table != old_table:
            # Remove main invitee from old_table
            try:
                self.model.tables[old_table].remove(attendee)
            except ValueError:
                self.model.tables[old_table] = [g for g in self.model.tables[old_table] if g.get("_id") != attendee_id]
            projected = self.model.table_headcount(self.model.tables[best_table]) + attendee_headcount(attendee)
            if projected <= SEATS_PER_TABLE:
                self.model.tables[best_table].append(attendee)
            else:
                messagebox.showwarning(
                    "Table Full",
                    f"Cannot move attendee: '{best_table}' would exceed {SEATS_PER_TABLE} seats with +1s."
                )
                self.model.tables[old_table].append(attendee)
            self.draw()
            return "break"
        # Default: move single attendee (not plus-one/main)
        if best_table and best_table != old_table:
            try:
                self.model.tables[old_table].remove(attendee)
            except ValueError:
                self.model.tables[old_table] = [g for g in self.model.tables[old_table] if g.get("_id") != attendee_id]
            projected = self.model.table_headcount(self.model.tables[best_table]) + attendee_headcount(attendee)
            if projected <= SEATS_PER_TABLE:
                self.model.tables[best_table].append(attendee)
            else:
                messagebox.showwarning(
                    "Table Full",
                    f"Cannot move attendee: '{best_table}' would exceed {SEATS_PER_TABLE} seats with +1s."
                )
                self.model.tables[old_table].append(attendee)
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
        loaded = self.model.load_seating()
        if not loaded:
            try:
                self.model.generate_from_attendees(os.path.join(os.path.dirname(__file__), "attendees.json"))
            except Exception as e:
                messagebox.showerror("Startup error", f"Cannot start:\n{e}")
                raise
        else:
            self.model.enforce_table_capacity()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Search Attendees:").pack(side="left", padx=8, pady=8)
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(top, textvariable=self.search_var, width=20)
        self.search_entry.pack(side="left", padx=8, pady=8)
        self.search_var.trace("w", self.on_search_change)
        ttk.Button(top, text="Reset Layout", command=self.on_reset).pack(side="right", padx=8, pady=8)
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
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
        viewer = ViewerTab(tabs)
        tabs.add(planner_frame, text="Planner")
        tabs.add(viewer, text="Viewer")

    def on_search_change(self, *args):
        self.canvas.search_string = self.search_var.get().strip()
        self.canvas.draw()

    def on_reset(self):
        self.model.reset_layout()
        self.model.enforce_table_capacity()
        self.canvas.draw()

    def on_close(self):
        self.model.save_json("seating_arrangement.json")
        self.model.save_csv("seating_arrangement.csv")
        self.destroy()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    App().mainloop()
