import json
import csv
import io
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
    # [CHANGEME] Room dimensions in meters -- matched to the venue floor plan
    # (Sala Ricevimenti photo: overall room dimension "13000" mm on the
    # dimensioned edge; room length is not fully dimensioned on the plan, so
    # ROOM_L leaves margin beyond the furnished area shown there).
    ROOM_L: float = 17.0  # [CHANGEME] Room length in meters
    ROOM_H: float = 13.0  # [CHANGEME] Room height in meters (floor plan: 13000 mm)
    PIXELS_PER_METER: int = 60
    VIEWPORT_W: int = 1400  # Expanded for legend on right
    VIEWPORT_H: int = 750   # Expanded for more display area
    SEATS_WARNING_LIMIT: int = 11
    SEATS_PER_TABLE: int = 11
    SPECIAL_TABLE: str = "Noi"
    RELATIONSHIPS: list = [
        "Bride", "Groom", "Immediate Family", "Extended Family",
        "Childhood Friends", "UniversityFriends", "Colleagues"
    ]
    # [CHANGEME] Table dimensions
    TABLE_R_PX: int = 45   # [CHANGEME] Attendee table radius in pixels (converts to ~0.75m at 60px/m)
    ATT_R_PX: int = 10
    ORBIT_R_PX: int = 55
    SPECIAL_W_PX: int = 90  # [CHANGEME] Special table width in pixels (converts to ~1.5m at 60px/m)
    SPECIAL_H_PX: int = 54  # [CHANGEME] Special table height in pixels (converts to ~0.9m at 60px/m)
    CANVAS_BG: str = "#000000"
    CANVAS_BG_RGB: tuple = (0, 0, 0)
    MIN_ALPHA: float = 0.25
    MAX_ALPHA: float = 1.00
    DEFAULT_FOOD_ALLERGY: str = "none"
    DEFAULT_FOOD_PREFERENCE: str = "none"
    DEFAULT_PLUS_ONE_NAME: str = "+1"

    # ------------------------------------------------------------------
    # [CHANGEME] Real-world floor-plan dimensions (millimeters), read off
    # the venue's CAD drawing. These drive both the default table layout
    # and the mechanical-labelling dimensions shown on the Technical
    # Layout tab. Adjust these to match the exact venue drawing if any
    # value looks off -- they were transcribed from a photo of the plan.
    # ------------------------------------------------------------------
    TABLE_TOP_DIAMETER_MM: int = 1200        # [CHANGEME] round table diameter (inner solid circle on the plan)
    TABLE_CLEARANCE_DIAMETER_MM: int = 2000  # [CHANGEME] table + chairs clearance zone (dashed outer circle on the plan)
    TABLE_COL_SPACING_MM: int = 4200         # [CHANGEME] center-to-center spacing between the two table columns (plan shows 4200/4900)
    TABLE_ROW_SPACING_MM: int = 2000         # [CHANGEME] center-to-center vertical spacing between tables in the same column
    TABLE_ROW_STAGGER_MM: int = 1000         # [CHANGEME] vertical offset of the second column relative to the first (staggered/brick layout on the plan)
    TABLE_FIRST_COL_OFFSET_MM: int = 2800    # [CHANGEME] distance from the left wall to the first table column's center
    SPECIAL_TABLE_WALL_OFFSET_MM: int = 1200  # [CHANGEME] distance of the "Sposi" (bride & groom) table from the left wall
    # Fixed service fixtures along the right wall, top to bottom, as shown
    # on the plan. Their footprints aren't dimensioned there, so the
    # width/height values below are reasonable placeholders -- [CHANGEME]
    # to match your actual equipment.
    FIXTURES: list = [
        {"name": "Tableau", "w_mm": 700, "h_mm": 1300},
        {"name": "Bomboniere", "w_mm": 900, "h_mm": 1700},
        {"name": "DJ", "w_mm": 1200, "h_mm": 1700},
        {"name": "PHOTOBOOT", "w_mm": 1200, "h_mm": 2100},
    ]
    FIXTURE_WALL_MARGIN_MM: int = 500  # [CHANGEME] gap between fixtures and the right wall

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
DIST_PLUS_ONE_PX = 20  # Distance offset for plus-one positioning in pixels


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


def normalize_food_preference_value(raw_value) -> str:
    """Return a canonical food preference string."""
    if raw_value is None:
        return Config.DEFAULT_FOOD_PREFERENCE
    value = str(raw_value).strip()
    return value or Config.DEFAULT_FOOD_PREFERENCE


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
            preference = normalize_food_preference_value(item.get("food_preference", Config.DEFAULT_FOOD_PREFERENCE))
            pid = item.get("_id") or uuid.uuid4().hex
        else:
            name = Config.DEFAULT_PLUS_ONE_NAME
            allergy = Config.DEFAULT_FOOD_ALLERGY
            preference = Config.DEFAULT_FOOD_PREFERENCE
            pid = uuid.uuid4().hex
        normalized.append({
            "name": name,
            "food_allergy": allergy,
            "food_preference": preference,
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


def normalize_food_preference(attendee: dict) -> str:
    """Normalize attendee food preference to a canonical scalar string."""
    attendee["food_preference"] = normalize_food_preference_value(
        attendee.get("food_preference", Config.DEFAULT_FOOD_PREFERENCE)
    )
    return attendee["food_preference"]


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
        self.legend_positions = {}
        self.legend_origin = (12, 12)  # top-left corner of the movable legend panel
        self.last_moved_table = None   # name of the table last dragged on the Planner tab

    def table_headcount(self, guests: list) -> int:
        """Return total seats consumed at a table including +1 seats."""
        return sum(attendee_headcount(g) for g in guests)

    def total_invitees(self) -> int:
        """Return the number of main invitees, excluding plus-ones."""
        return sum(len(guests) for guests in self.tables.values())

    def total_headcount(self) -> int:
        """Return the number of invitees including plus-one seats."""
        return sum(self.table_headcount(guests) for guests in self.tables.values())

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

    def _table_grid_position(self, index: int):
        """Return (x_m, y_m) for the table at `index` (0-based) in the
        staggered 2-column layout read off the venue floor plan: two
        columns TABLE_COL_SPACING_MM apart, tables TABLE_ROW_SPACING_MM
        apart within a column, and the second column offset vertically by
        TABLE_ROW_STAGGER_MM to create the brick/staggered pattern shown
        on the plan."""
        x0_m = Config.TABLE_FIRST_COL_OFFSET_MM / 1000.0
        col_spacing_m = Config.TABLE_COL_SPACING_MM / 1000.0
        row_spacing_m = Config.TABLE_ROW_SPACING_MM / 1000.0
        stagger_m = Config.TABLE_ROW_STAGGER_MM / 1000.0
        top_margin_m = 1.5
        col = index % 2
        row = index // 2
        x = x0_m + col * col_spacing_m
        y = top_margin_m + row * row_spacing_m + (stagger_m if col == 1 else 0.0)
        return x, y

    def fixture_rects(self):
        """Return the fixed room fixtures (Tableau, Bomboniere, DJ,
        Photobooth) as (name, x_m, y_m, w_m, h_m) center-based rectangles
        stacked along the right wall, per the venue floor plan. These are
        fixed room features, not draggable tables."""
        margin_m = Config.FIXTURE_WALL_MARGIN_MM / 1000.0
        n = len(Config.FIXTURES)
        slot_h = ROOM_H / n
        rects = []
        for i, fx in enumerate(Config.FIXTURES):
            w_m = fx["w_mm"] / 1000.0
            h_m = fx["h_mm"] / 1000.0
            x = ROOM_L - margin_m - w_m / 2.0
            y = slot_h * i + slot_h / 2.0
            rects.append((fx["name"], x, y, w_m, h_m))
        return rects

    def _clamp_all_positions(self):
        """Clamp every non-special table position within the current room
        bounds (used after loading a saved layout, in case the room size
        changed since it was saved)."""
        for t, (x, y) in list(self.table_positions.items()):
            if t == SPECIAL_TABLE:
                continue
            x = clamp(x, 2.0, ROOM_L - 2.0)
            y = clamp(y, 2.0, ROOM_H - 2.0)
            self.table_positions[t] = (x, y)

    def _assign_positions_to_missing_tables(self):
        others = [t for t in self.tables.keys() if t != SPECIAL_TABLE and t not in self.table_positions]
        if not others:
            return
        start_index = len([t for t in self.tables.keys() if t != SPECIAL_TABLE and t in self.table_positions])
        for offset, t in enumerate(others):
            x, y = self._table_grid_position(start_index + offset)
            x = clamp(x, 2.0, ROOM_L - 2.0)
            y = clamp(y, 2.0, ROOM_H - 2.0)
            self.table_positions[t] = (x, y)

    def _rebalance_overflow_tables(self) -> bool:
        changed = False
        table_indices = [int(name.split("Table ")[1]) for name in self.tables.keys() if name.startswith("Table ") and name.split("Table ")[1].isdigit()]
        next_index = max(table_indices, default=0) + 1

        for table_name in list(self.tables.keys()):
            if table_name == SPECIAL_TABLE:
                continue
            guests = self.tables[table_name]
            if self.table_headcount(guests) <= SEATS_PER_TABLE:
                continue
            chunks = self.split_group_by_capacity(guests, SEATS_PER_TABLE)
            self.tables[table_name] = chunks[0]
            for overflow_chunk in chunks[1:]:
                while f"Table {next_index}" in self.tables:
                    next_index += 1
                self.tables[f"Table {next_index}"] = overflow_chunk
                next_index += 1
                changed = True
        if changed:
            self._assign_positions_to_missing_tables()
        return changed

    def load_seating(self, path="seating_arrangement.json"):
        if not os.path.exists(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self.table_positions = raw.pop("_table_positions", {})
            self.legend_positions = raw.pop("_legend_positions", {})
            legend_origin_raw = raw.pop("_legend_origin", [12, 12])
            self.tables = raw
            for k, v in list(self.table_positions.items()):
                if isinstance(v, list) and len(v) == 2:
                    self.table_positions[k] = (float(v[0]), float(v[1]))
            for k, v in list(self.legend_positions.items()):
                if isinstance(v, list) and len(v) == 2:
                    self.legend_positions[k] = (float(v[0]), float(v[1]))
            if isinstance(legend_origin_raw, list) and len(legend_origin_raw) == 2:
                self.legend_origin = (float(legend_origin_raw[0]), float(legend_origin_raw[1]))
            self._normalize_all_attendees()
            self._ensure_special_table_position()
            self._clamp_all_positions()
            missing = [t for t in self.tables.keys() if t not in self.table_positions]
            if missing:
                self.reset_layout()
            if self._rebalance_overflow_tables():
                logging.info("Rebalanced overflowed tables from '%s' by creating new tables.", path)
            if not self.enforce_table_capacity(show_dialog=False):
                logging.error("Loaded seating file '%s' still has tables over capacity after rebalancing.", path)
                return False
            return True
        except Exception as e:
            messagebox.showerror("Load error", f"Failed to load seating:\n{e}")
            return False

    def save_json(self, path="seating_arrangement.json"):
        data = dict(self.tables)
        data["_table_positions"] = {k: [float(x), float(y)] for k, (x, y) in self.table_positions.items()}
        data["_legend_positions"] = {k: [float(x), float(y)] for k, (x, y) in self.legend_positions.items()}
        data["_legend_origin"] = [float(self.legend_origin[0]), float(self.legend_origin[1])]
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

    def save_pdf(self, path="seating_arrangement.pdf", extra_images=None):
        """Export invitees and their food requirements to a PDF report.

        extra_images: optional list of (title, image_bytes) tuples. Each is
        appended as its own page (title + the image scaled to fit) after the
        main food-requirements table -- used for the "UI images" pages.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import landscape, A4
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.lib.utils import ImageReader
            from reportlab.platypus import (
                SimpleDocTemplate, Spacer, Table, TableStyle, Paragraph, PageBreak, Image,
            )
        except ImportError as exc:
            raise RuntimeError("PDF export requires the reportlab package.") from exc

        styles = getSampleStyleSheet()
        body_style = styles["BodyText"]
        body_style.fontSize = 8
        body_style.leading = 10
        rows = [["Table", "Guest", "Food allergy", "Food preference"]]
        for table, guests in self.tables.items():
            for guest in guests:
                rows.append([
                    table,
                    guest.get("name", ""),
                    effective_food_allergy(guest),
                    normalize_food_preference(guest),
                ])
                for plus_one in normalize_plus_one(guest):
                    rows.append([
                        table,
                        plus_one.get("name", Config.DEFAULT_PLUS_ONE_NAME),
                        plus_one.get("food_allergy", Config.DEFAULT_FOOD_ALLERGY),
                        plus_one.get("food_preference", Config.DEFAULT_FOOD_PREFERENCE),
                    ])

        pdf = SimpleDocTemplate(
            path,
            pagesize=landscape(A4),
            rightMargin=12 * mm,
            leftMargin=12 * mm,
            topMargin=12 * mm,
            bottomMargin=12 * mm,
        )
        table = Table(
            [[Paragraph(str(value), body_style) for value in row] for row in rows],
            repeatRows=1,
            colWidths=[32 * mm, 65 * mm, 78 * mm, 95 * mm],
        )
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#333333")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eeeeee")]),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story = [
            Paragraph("Wedding Seating Food Requirements", styles["Title"]),
            Spacer(1, 6 * mm),
            table,
        ]

        if extra_images:
            page_w, page_h = landscape(A4)
            avail_w = page_w - 24 * mm
            avail_h = page_h - 30 * mm  # leave room for the page title
            for title, image_bytes in extra_images:
                if not image_bytes:
                    continue
                buf = io.BytesIO(image_bytes)
                try:
                    reader = ImageReader(buf)
                    iw, ih = reader.getSize()
                except Exception:
                    continue
                scale = min(avail_w / iw, avail_h / ih, 1.0)
                draw_w, draw_h = iw * scale, ih * scale
                buf.seek(0)
                story.append(PageBreak())
                story.append(Paragraph(str(title), styles["Title"]))
                story.append(Spacer(1, 4 * mm))
                story.append(Image(buf, width=draw_w, height=draw_h))

        pdf.build(story)

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
            a.setdefault("food_preference", Config.DEFAULT_FOOD_PREFERENCE)
            ensure_attendee_id(a)
            normalize_plus_one(a)
            normalize_food_allergy(a)
            normalize_food_preference(a)
        # Guard against corrupted data where a plus-one (or main invitee)
        # ended up with a duplicate _id -- e.g. from copy-pasting one
        # attendee's JSON as a template for another and forgetting to
        # change the id. A duplicate silently hides the affected guest
        # from their table (the app mistakes them for a plus-one already
        # accounted for) or misdirects drag/edit to the wrong person, so
        # any collision found here is repaired with a fresh unique id.
        seen_ids = set()
        for a in attendees:
            aid = a.get("_id")
            if not aid or aid in seen_ids:
                aid = uuid.uuid4().hex
                a["_id"] = aid
            seen_ids.add(aid)
            for p in a.get("plus_one", []):
                pid = p.get("_id")
                if not pid or pid in seen_ids:
                    pid = uuid.uuid4().hex
                    p["_id"] = pid
                seen_ids.add(pid)
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
        # Placed on the left wall at the room's vertical center, matching
        # the "Sposi" (bride & groom) table position on the venue floor plan.
        cx = Config.SPECIAL_TABLE_WALL_OFFSET_MM / 1000.0
        cy = ROOM_H / 2.0
        self.table_positions[SPECIAL_TABLE] = (cx, cy)

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
            normalize_food_preference(a)
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
            normalize_food_preference(a)
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
        others = [t for t in self.tables.keys() if t != SPECIAL_TABLE]
        def table_priority(t):
            guests = self.tables[t]
            if not guests:
                return 999
            return min(g.get("category", 999) for g in guests)
        others.sort(key=table_priority)
        for i, t in enumerate(others):
            x, y = self._table_grid_position(i)
            x = clamp(x, 2.0, ROOM_L - 2.0)
            y = clamp(y, 2.0, ROOM_H - 2.0)
            self.table_positions[t] = (x, y)

    def enforce_table_capacity(self, show_dialog=True):
        for t, guests in self.tables.items():
            if t != Config.SPECIAL_TABLE and self.table_headcount(guests) > Config.SEATS_PER_TABLE:
                logging.error(f"Table '{t}' exceeds the maximum of {Config.SEATS_PER_TABLE} seats (including +1s).")
                if show_dialog:
                    messagebox.showerror(
                        "Table Capacity Exceeded",
                        f"Table '{t}' has more than {Config.SEATS_PER_TABLE} seats when +1s are included.\n"
                        "Please delete or fix 'seating_arrangement.json' and restart the application."
                    )
                    raise RuntimeError("Table capacity exceeded.")
                return False
        return True

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
        self.legend_positions = model.legend_positions
        # Callbacks invoked whenever table positions may have changed, so
        # other views (e.g. the read-only Technical Layout tab) can refresh
        # to reflect the tables' latest positions.
        self.on_change_callbacks = []
        # Bounding box of the movable legend panel (background box), set on
        # every draw() -- used to keep dragged legend entries inside it.
        self.legend_panel_bounds = (0, 0, 0, 0)
        # Keep the room centered in the visible viewport: whenever this
        # widget is resized, recompute the centering offset and redraw. The
        # room, tables, fixtures and grid lines all share this one offset,
        # so they always move together as a single rigid scene.
        self.bind("<Configure>", self._on_resize)
        self.draw()

    def m2px(self, v):
        """Convert a real-world length (radius, width, ...) to pixels -- no
        centering offset, since a length isn't tied to a screen position."""
        return v * PIXELS_PER_METER

    def room_offset(self):
        """Pixel offset that centers the room (and everything anchored to
        it: tables, fixtures, grid lines) within the widget's current
        visible size. The legend is intentionally NOT affected -- it has
        its own independent, user-movable position."""
        vw = self.winfo_width() or VIEWPORT_W
        vh = self.winfo_height() or VIEWPORT_H
        ox = max(0, (vw - CANVAS_W) / 2)
        oy = max(0, (vh - CANVAS_H) / 2)
        return ox, oy

    def m2px_pos(self, x_m, y_m):
        """Convert a real-world (x, y) position in meters to a centered
        canvas pixel position."""
        ox, oy = self.room_offset()
        return x_m * PIXELS_PER_METER + ox, y_m * PIXELS_PER_METER + oy

    def _on_resize(self, event):
        # Only react to actual size changes of this widget (not every
        # Configure event, e.g. ones bubbling from child items).
        if event.width != getattr(self, "_last_width", None) or event.height != getattr(self, "_last_height", None):
            self._last_width, self._last_height = event.width, event.height
            self.draw()

    def _notify_change(self):
        for cb in self.on_change_callbacks:
            cb()

    def _find_attendee(self, attendee_id: str):
        """Locate attendee and its table using attendee id."""
        for table_name, guests in self.model.tables.items():
            for guest in guests:
                if guest.get("_id") == attendee_id:
                    return table_name, guest
                for plus_one in guest.get("plus_one", []):
                    if plus_one.get("_id") == attendee_id:
                        return table_name, plus_one
        return None, None

    def _open_attendee_editor(self, attendee_id: str):
        """Open popup editor for attendee food allergy and plus-one entries."""
        table_name, attendee = self._find_attendee(attendee_id)
        if not attendee:
            messagebox.showerror("Edit attendee", "Attendee not found.")
            return

        normalize_food_allergy(attendee)
        normalize_food_preference(attendee)
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

        ttk.Label(frame, text="Food preference:").grid(row=2, column=0, sticky="w")
        attendee_preference_var = tk.StringVar(
            value=attendee.get("food_preference", Config.DEFAULT_FOOD_PREFERENCE)
        )
        ttk.Entry(frame, textvariable=attendee_preference_var, width=30).grid(
            row=2, column=1, columnspan=2, sticky="ew", padx=(6, 0)
        )

        ttk.Label(frame, text="Plus-ones").grid(row=3, column=0, sticky="w", pady=(10, 4))
        plus_list = tk.Listbox(frame, height=6, width=48)
        plus_list.grid(row=4, column=0, columnspan=3, sticky="ew")

        ttk.Label(frame, text="Name").grid(row=5, column=0, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="Food allergy").grid(row=5, column=1, sticky="w", pady=(8, 0))
        ttk.Label(frame, text="Food preference").grid(row=5, column=2, sticky="w", pady=(8, 0))

        plus_name_var = tk.StringVar(value=Config.DEFAULT_PLUS_ONE_NAME)
        plus_food_var = tk.StringVar(value=Config.DEFAULT_FOOD_ALLERGY)
        plus_preference_var = tk.StringVar(value=Config.DEFAULT_FOOD_PREFERENCE)
        ttk.Entry(frame, textvariable=plus_name_var, width=20).grid(row=6, column=0, sticky="ew", padx=(0, 6))
        ttk.Entry(frame, textvariable=plus_food_var, width=20).grid(row=6, column=1, sticky="ew", padx=(0, 6))
        ttk.Entry(frame, textvariable=plus_preference_var, width=20).grid(row=6, column=2, sticky="ew")

        working_plus_ones = [dict(p) for p in attendee.get("plus_one", [])]

        def refresh_plus_ones():
            plus_list.delete(0, tk.END)
            for index, plus_one in enumerate(working_plus_ones, start=1):
                plus_list.insert(
                    tk.END,
                    f"{index}. {plus_one.get('name', Config.DEFAULT_PLUS_ONE_NAME)} | "
                    f"{plus_one.get('food_allergy', Config.DEFAULT_FOOD_ALLERGY)} | "
                    f"{plus_one.get('food_preference', Config.DEFAULT_FOOD_PREFERENCE)}"
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
            plus_preference_var.set(item.get("food_preference", Config.DEFAULT_FOOD_PREFERENCE))

        def add_or_update_plus_one():
            plus_one_item = {
                "name": plus_name_var.get().strip() or Config.DEFAULT_PLUS_ONE_NAME,
                "food_allergy": plus_food_var.get().strip() or Config.DEFAULT_FOOD_ALLERGY,
                "food_preference": plus_preference_var.get().strip() or Config.DEFAULT_FOOD_PREFERENCE,
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
            plus_preference_var.set(Config.DEFAULT_FOOD_PREFERENCE)

        button_frame = ttk.Frame(frame)
        button_frame.grid(row=7, column=0, columnspan=3, sticky="e", pady=(6, 0))
        ttk.Button(button_frame, text="Add/Update", command=add_or_update_plus_one).pack(side="left", padx=(0, 6))
        ttk.Button(button_frame, text="Remove", command=remove_plus_one).pack(side="left")

        plus_list.bind("<<ListboxSelect>>", load_selected)

        def save_changes():
            original_allergy = attendee.get("food_allergy", Config.DEFAULT_FOOD_ALLERGY)
            original_preference = attendee.get("food_preference", Config.DEFAULT_FOOD_PREFERENCE)
            original_plus_one = [dict(p) for p in attendee.get("plus_one", [])]

            attendee["food_allergy"] = attendee_allergy_var.get().strip() or Config.DEFAULT_FOOD_ALLERGY
            attendee["food_preference"] = attendee_preference_var.get().strip() or Config.DEFAULT_FOOD_PREFERENCE
            attendee["plus_one"] = working_plus_ones[:max(0, Config.SEATS_PER_TABLE - 1)]
            normalize_food_allergy(attendee)
            normalize_food_preference(attendee)
            normalize_plus_one(attendee)

            if table_name != SPECIAL_TABLE and self.model.table_headcount(self.model.tables.get(table_name, [])) > SEATS_PER_TABLE:
                attendee["food_allergy"] = original_allergy
                attendee["food_preference"] = original_preference
                attendee["plus_one"] = original_plus_one
                messagebox.showwarning(
                    "Table Capacity",
                    f"Saving this change would exceed {SEATS_PER_TABLE} seats for '{table_name}'."
                )
                return

            popup.destroy()
            self.draw()

        actions = ttk.Frame(frame)
        actions.grid(row=8, column=0, columnspan=3, sticky="e", pady=(12, 0))
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
        side = str(attendee.get("side", "")).strip().lower()
        if side == "bride":
            fg = (255, 0, 0)
        elif side == "groom":
            fg = (0, 110, 255)
        else:
            rel = attendee.get("relationship", "Colleagues")
            if rel == "Bride":
                fg = (255, 0, 0)
            elif rel == "Groom":
                fg = (0, 110, 255)
            elif rel in ("Immediate Family", "Extended Family"):
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
        self.winfo_toplevel().title(
            f"Wedding Seating Planner - Invitees: {self.model.total_invitees()} "
            f"(including +1s: {self.model.total_headcount()})"
        )
        # The room outline, fixtures, grid lines and tables are all placed
        # using this one offset, so the room is centered in the visible
        # viewport and everything anchored to it moves together as a single
        # rigid scene if the viewport is resized. The legend is deliberately
        # excluded -- it has its own independent, user-movable position.
        room_ox, room_oy = self.room_offset()
        self.create_rectangle(
            room_ox + 5, room_oy + 5, room_ox + CANVAS_W - 5, room_oy + CANVAS_H - 5,
            outline="#333333", width=2
        )
        # Fixed room fixtures (Tableau, Bomboniere, DJ, Photobooth) along the
        # right wall, per the venue floor plan. These are reference-only:
        # no tag_bind is attached, so they cannot be dragged.
        for name, x_m, y_m, w_m, h_m in self.model.fixture_rects():
            fpx, fpy = self.m2px_pos(x_m, y_m)
            fw, fh = self.m2px(w_m), self.m2px(h_m)
            self.create_rectangle(
                fpx - fw / 2, fpy - fh / 2, fpx + fw / 2, fpy + fh / 2,
                outline="#f5d76e", width=2, tags=("fixture",)
            )
            self.create_text(
                fpx, fpy, text=name, fill="#f5d76e",
                font=("Arial", 9, "bold"), tags=("fixture",)
            )
        # Alignment grid: a full-width/height guide line through the center
        # of every table (including "Sposi"), so rows and columns are easy
        # to eyeball while dragging tables around.
        grid_color = "#262626"
        for _table, (gx_m, gy_m) in self.model.table_positions.items():
            gpx, gpy = self.m2px_pos(gx_m, gy_m)
            self.create_line(gpx, room_oy + 5, gpx, room_oy + CANVAS_H - 5, fill=grid_color,
                              dash=(2, 4), tags=("gridline",))
            self.create_line(room_ox + 5, gpy, room_ox + CANVAS_W - 5, gpy, fill=grid_color,
                              dash=(2, 4), tags=("gridline",))
        legend_x, legend_y = self.model.legend_origin
        legend_col_w = 230
        legend_w = legend_col_w * 2
        line_h = 18
        legend_bg = "#111111"
        legend_border = "#333333"

        def table_line_count(table):
            """Number of legend list rows this table needs: one per shown
            main invitee (capped at 8, matching guests[:8] below) plus one
            more for each of their plus-ones -- plus-ones are listed as
            their own row, just like a main invitee."""
            guests = self.model.tables.get(table, [])
            return sum(1 + len(g.get("plus_one", [])) for g in guests[:8])

        total_lines = 1 + sum(table_line_count(t) for t in self.model.tables.keys())
        legend_tables = list(self.model.tables.keys())
        legend_rows = []
        for row_index in range((len(legend_tables) + 1) // 2):
            row_tables = legend_tables[row_index * 2:row_index * 2 + 2]
            row_lines = max(1 + table_line_count(table) for table in row_tables)
            legend_rows.append(row_lines)
        legend_height = legend_y - 16 + line_h + sum(row_lines * line_h + 6 for row_lines in legend_rows) + 6
        # Remember the panel's border so dragged legend entries can be
        # clamped to stay inside it (see drag_legend_table).
        self.legend_panel_bounds = (legend_x - 16, legend_y - 16, legend_x + legend_w, legend_height)
        # The background box and title are the drag handle for the whole
        # legend panel (tag "legend_panel"); every item tagged
        # "legend_panel_group" moves together with them. Per-table entries
        # the user has individually dragged elsewhere (present in
        # self.legend_positions) are left out of that group so they stay
        # exactly where the user put them.
        self.create_rectangle(
            legend_x - 16, legend_y - 16,
            legend_x + legend_w, legend_height,
            fill=legend_bg, outline=legend_border, width=1,
            tags=("legend_panel", "legend_panel_group")
        )
        self.create_text(legend_x, legend_y - 2, text="Legend (by table colors) - drag to move",
                          fill="#ffffff", font=("Arial", 10, "bold"), anchor="nw",
                          tags=("legend_panel", "legend_panel_group"))
        self.tag_bind("legend_panel", "<ButtonPress-1>", self.start_legend_panel_drag)
        self.tag_bind("legend_panel", "<B1-Motion>", self.drag_legend_panel)
        self.tag_bind("legend_panel", "<ButtonRelease-1>", self.end_legend_panel_drag)
        for idx, table in enumerate(legend_tables):
            guests = self.model.tables.get(table, [])
            row_index, column_index = divmod(idx, 2)
            default_x = legend_x + column_index * legend_col_w
            default_y = legend_y + line_h + sum(row_lines * line_h + 6 for row_lines in legend_rows[:row_index])
            is_default_pos = table not in self.legend_positions
            base_x, base_y = self.legend_positions.get(table, (default_x, default_y))
            panel_tags = ("legend_panel_group",) if is_default_pos else ()
            rep = guests[0] if guests else None
            header_color = self.attendee_color(rep) if rep else "#666666"
            rect_id = self.create_rectangle(
                base_x, base_y, base_x + 14, base_y + 14,
                fill=header_color, outline="#ffffff", width=1,
                tags=(f"legend_group:{table}", f"legend_table:{table}") + panel_tags
            )
            self.create_text(
                base_x + 22, base_y + 7,
                text=f"{table}",
                fill="#ffffff", font=("Arial", 9), anchor="w",
                tags=(f"legend_group:{table}",) + panel_tags
            )
            line_offset = 0
            for j, a in enumerate(guests[:8]):
                c = self.attendee_color(a)
                y = base_y + 16 + line_offset * 14
                oval_id = self.create_rectangle(
                    base_x + 22, y - 2,
                    base_x + 34, y + 10,
                    fill=c, outline="#ffffff", width=1,
                    tags=(f"legend_group:{table}", f"legend_attendee:{table}:{ensure_attendee_id(a)}") + panel_tags
                )
                self.create_text(
                    base_x + 40, y + 4,
                    text=a.get("name", ""),
                    fill="#ffffff", font=("Arial", 7), anchor="w",
                    tags=(f"legend_group:{table}",) + panel_tags
                )
                # Bind drag for legend attendee
                self.tag_bind(f"legend_attendee:{table}:{ensure_attendee_id(a)}", "<ButtonPress-1>",
                              lambda e, t=table, aid=ensure_attendee_id(a): self.start_legend_attendee_drag(e, t, aid))
                self.tag_bind(f"legend_attendee:{table}:{ensure_attendee_id(a)}", "<B1-Motion>", self.drag_legend_attendee)
                self.tag_bind(f"legend_attendee:{table}:{ensure_attendee_id(a)}", "<ButtonRelease-1>", self.end_legend_attendee_drag)
                line_offset += 1
                # List each plus-one as its own row, right below their main
                # invitee, in the same style (color swatch + name) -- just
                # display-only, no drag/reassign binding on these rows.
                for p in a.get("plus_one", []):
                    py_line = base_y + 16 + line_offset * 14
                    pc = self.attendee_color(p)
                    self.create_rectangle(
                        base_x + 22, py_line - 2,
                        base_x + 34, py_line + 10,
                        fill=pc, outline="#ffffff", width=1,
                        tags=(f"legend_group:{table}",) + panel_tags
                    )
                    self.create_text(
                        base_x + 40, py_line + 4,
                        text=p.get("name", ""),
                        fill="#ffffff", font=("Arial", 7), anchor="w",
                        tags=(f"legend_group:{table}",) + panel_tags
                    )
                    line_offset += 1
            # Bind drag for legend table
            self.tag_bind(f"legend_table:{table}", "<ButtonPress-1>",
                          lambda e, t=table: self.start_legend_table_drag(e, t))
            self.tag_bind(f"legend_table:{table}", "<B1-Motion>", self.drag_legend_table)
            self.tag_bind(f"legend_table:{table}", "<ButtonRelease-1>", self.end_legend_table_drag)
        for table, guests in self.model.tables.items():
            tx, ty = self.model.table_positions.get(table, (ROOM_L / 2, ROOM_H / 2))
            px, py = self.m2px_pos(tx, ty)
            group_tag = f"group:{table}"
            handle_tag = f"handle:{table}"
            if table == SPECIAL_TABLE:
                h, w = SPECIAL_W_PX, SPECIAL_H_PX
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
            # label_text = f"{table} ({len(guests)} guests/{self.model.table_headcount(guests)} heads)"
            label_text = f"{table} ({self.model.table_headcount(guests)})"
            # Split label_text into lines if too long
            max_label_len = 10
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
                    px, py - 0 + idx*20,
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
            # For the Sposi (bride & groom) table: seat both of them
            # together on the side of their table that faces AWAY from the
            # other guest tables, instead of the generic all-round orbit
            # used for regular tables.
            seat_positions = None
            special_ang = None
            if table == SPECIAL_TABLE:
                other_positions = [p for t2, p in self.model.table_positions.items() if t2 != SPECIAL_TABLE]
                if other_positions:
                    cx_other = sum(p[0] for p in other_positions) / len(other_positions)
                    cy_other = sum(p[1] for p in other_positions) / len(other_positions)
                    dvx, dvy = cx_other - tx, cy_other - ty
                else:
                    dvx, dvy = 1.0, 0.0
                mag = math.hypot(dvx, dvy) or 1.0
                away_x, away_y = -dvx / mag, -dvy / mag  # points away from the other tables
                perp_x, perp_y = -away_y, away_x
                special_ang = math.atan2(away_y, away_x)
                spacing_px = ATT_R_PX * 2 + 6
                seat_positions = []
                for i2 in range(n):
                    side_offset = (i2 - (n - 1) / 2) * spacing_px
                    seat_positions.append((
                        px + away_x * ORBIT_R_PX + perp_x * side_offset,
                        py + away_y * ORBIT_R_PX + perp_y * side_offset,
                    ))
            # --- Render main invitees and plus-ones visually ---
            for i, g in enumerate(guests_sorted):
                aid = ensure_attendee_id(g)
                if seat_positions is not None:
                    gx, gy = seat_positions[i]
                    ang = special_ang
                else:
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
                    gx-len(aid)/2, gy + 18,
                    g.get("name", "").split(" ", 1)[0],
                    #g.get("name", ""),
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
                    # Draw plus-ones for this main invitee
                    pid = ensure_attendee_id(p)

                    # Offset perpendicular to attendee orbit direction
                    side_offset = (j - (n_plus - 1) / 2) * DIST_PLUS_ONE_PX

                    # Perpendicular vector
                    perp_x = -math.sin(ang)
                    perp_y = math.cos(ang)

                    # Position close to main attendee circle
                    pgx = gx + perp_x * side_offset + math.cos(ang) * (ATT_R_PX * 0.9)
                    pgy = gy + perp_y * side_offset + math.sin(ang) * (ATT_R_PX * 0.9)

                    # Draw line from main to plus-one
                    self.create_line(
                        gx, gy, pgx, pgy,
                        fill="#bbbbbb",
                        width=1,
                        tags=(group_tag, f"attendee:{aid}")
                    )

                    # Draw plus-one circle
                    oval_id_p = self.create_oval(
                        pgx - ATT_R_PX//2, pgy - ATT_R_PX//2,
                        pgx + ATT_R_PX//2, pgy + ATT_R_PX//2,
                        fill=self.attendee_color(p),
                        outline="#ffffff",
                        width=1,
                        tags=(group_tag, f"attendee:{pid}", "attendee", "plusone")
                    )
                    self.tag_bind(f"attendee:{pid}", "<Double-Button-3>", self.open_attendee_editor_from_event)
                    
                    
                    """pid = ensure_attendee_id(p)
                    pang = ang + (j - (n_plus-1)/2) * (math.pi/8)
                    pr = ORBIT_R_PX + DIST_PLUS_ONE_PX
                    pgx = px + math.cos(pang) * pr
                    pgy = py + math.sin(pang) * pr
                    # Draw line from main to plus-one
                    self.create_line(
                        gx, gy, pgx, pgy,
                        fill="#bbbbbb",
                        width=1,
                        tags=(group_tag, f"attendee:{aid}")
                    )
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
                    self.tag_bind(f"attendee:{pid}", "<Button-3>", self.open_attendee_editor_from_event)"""
                # Bindings for main invitee
                self.tag_bind(f"attendee:{aid}", "<ButtonPress-1>",
                              lambda e, t=table, a=g, attendee_id=aid: self.start_attendee_drag(e, t, a, attendee_id))
                self.tag_bind(f"attendee:{aid}", "<B1-Motion>", self.drag_attendee)
                self.tag_bind(f"attendee:{aid}", "<ButtonRelease-1>",
                              lambda e, a=g, attendee_id=aid: self.end_attendee_drag(e, a, attendee_id))
                self.tag_bind(f"attendee:{aid}", "<Double-Button-3>", self.open_attendee_editor_from_event)
        self.configure(scrollregion=self.bbox("all"))
        self._notify_change()

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
        # Bug fix: table positions are stored in room-relative meters, but
        # the room is drawn with a centering offset (room_offset). The
        # drop point must have that same offset subtracted before
        # converting to meters, or the table snaps away from where it was
        # actually dropped as soon as draw() re-renders it.
        ox, oy = self.room_offset()
        x = (self.canvasx(e.x) - ox) / PIXELS_PER_METER
        y = (self.canvasy(e.y) - oy) / PIXELS_PER_METER
        x = clamp(x, 2.0, ROOM_L - 2.0)
        y = clamp(y, 2.0, ROOM_H - 2.0)
        self.model.table_positions[table] = (x, y)
        self.model.last_moved_table = table
        self.drag = None
        # Full redraw so the grid lines (which pass through each table's
        # center) and the Technical Layout tab's distances line up exactly
        # with the clamped drop position, not the raw mouse position.
        self.draw()
        return "break"

    def start_legend_panel_drag(self, e):
        """Grab the legend panel (its background box or title) to move the
        whole panel -- and every entry still at its default position -- as
        one unit."""
        self.drag = {
            "type": "legend_panel",
            "x": self.canvasx(e.x),
            "y": self.canvasy(e.y),
            "start_x": self.canvasx(e.x),
            "start_y": self.canvasy(e.y),
        }
        return "break"

    def drag_legend_panel(self, e):
        if not self.drag or self.drag.get("type") != "legend_panel":
            return "break"
        x = self.canvasx(e.x)
        y = self.canvasy(e.y)
        dx = x - self.drag["x"]
        dy = y - self.drag["y"]
        self.move("legend_panel_group", dx, dy)
        self.drag["x"], self.drag["y"] = x, y
        return "break"

    def end_legend_panel_drag(self, e):
        if not self.drag or self.drag.get("type") != "legend_panel":
            self.drag = None
            return "break"
        x = self.canvasx(e.x)
        y = self.canvasy(e.y)
        dx = x - self.drag["start_x"]
        dy = y - self.drag["start_y"]
        ox, oy = self.model.legend_origin
        self.model.legend_origin = (ox + dx, oy + dy)
        self.drag = None
        self.draw()
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
            px, py = self.m2px_pos(tx, ty)
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
        table = self.drag["table"]
        group_tag = f"legend_group:{table}"
        # Keep the legend grouped: clamp the move so this table's entire
        # entry (header + its attendee rows) never leaves the legend
        # panel's border.
        bbox = self.bbox(group_tag)
        lx1, ly1, lx2, ly2 = self.legend_panel_bounds
        if bbox:
            bx1, by1, bx2, by2 = bbox
            new_x1, new_x2 = bx1 + dx, bx2 + dx
            new_y1, new_y2 = by1 + dy, by2 + dy
            if new_x1 < lx1:
                dx += (lx1 - new_x1)
            elif new_x2 > lx2:
                dx -= (new_x2 - lx2)
            if new_y1 < ly1:
                dy += (ly1 - new_y1)
            elif new_y2 > ly2:
                dy -= (new_y2 - ly2)
        self.move(group_tag, dx, dy)
        self.drag["x"], self.drag["y"] = x, y
        return "break"

    def end_legend_table_drag(self, e):
        if not self.drag or self.drag.get("type") != "legend_table":
            self.drag = None
            return "break"
        table = self.drag["table"]
        # Read back the entry's actual (possibly border-clamped) header
        # position rather than the raw mouse position, so it's stored
        # exactly where it visually ended up.
        rect_bbox = self.bbox(f"legend_table:{table}")
        if rect_bbox:
            bx1, by1, _, _ = rect_bbox
            self.model.legend_positions[table] = (bx1, by1)
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
            px, py = self.m2px_pos(tx, ty)
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
# Technical Layout Tab (read-only mechanical labelling)
# ======================================================

class TechnicalTab(ttk.Frame):
    """Read-only technical/mechanical floor-plan view.

    Shows the room outline, the fixed fixtures (Tableau, Bomboniere, DJ,
    Photobooth) and the round tables at their *current* positions, each
    annotated with millimeter dimensions -- mirroring the style of the
    venue's CAD floor plan. This tab has no drag/click bindings of any
    kind: it is purely for reference and hand-off (e.g. to the venue or
    installers), and it is refreshed automatically whenever a table is
    moved on the Planner tab (see App.__init__ / PlannerCanvas.on_change_callbacks).

    The "Show distance to closest table (all tables)" checkbox toggles
    between a decluttered default (only the most recently moved table's
    distance to its nearest neighbor) and showing every table's distance
    to its own closest neighbor. Room, fixture and table size labels are
    always shown either way.
    """
    def __init__(self, parent, model: SeatingModel):
        super().__init__(parent)
        self.model = model
        self.show_all_var = tk.BooleanVar(value=False)
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Checkbutton(
            toolbar, text="Show distance to closest table (all tables)",
            variable=self.show_all_var, command=self.refresh
        ).pack(side="left", padx=6, pady=4)
        self.canvas = tk.Canvas(
            self, width=VIEWPORT_W, height=VIEWPORT_H, bg=CANVAS_BG,
            highlightthickness=0, scrollregion=(0, 0, CANVAS_W, CANVAS_H)
        )
        hbar = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        vbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=1, column=0, sticky="nsew")
        vbar.grid(row=1, column=1, sticky="ns")
        hbar.grid(row=2, column=0, sticky="ew")
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        # Keep the room centered in this tab's viewport too, and redraw on
        # resize -- see PlannerCanvas.room_offset for the rationale.
        self.canvas.bind("<Configure>", self._on_resize)
        # NOTE: intentionally no other tag_bind/bind calls anywhere in this
        # class -- this view is display-only and never mutates the model.
        self.refresh()

    def _on_resize(self, event):
        if event.width != getattr(self, "_last_width", None) or event.height != getattr(self, "_last_height", None):
            self._last_width, self._last_height = event.width, event.height
            self.refresh()

    def m2px(self, v):
        """Convert a real-world length (radius, width, ...) to pixels -- no
        centering offset, since a length isn't tied to a screen position."""
        return v * PIXELS_PER_METER

    def room_offset(self):
        """Pixel offset that centers the room within this tab's current
        visible size (mirrors PlannerCanvas.room_offset)."""
        vw = self.canvas.winfo_width() or VIEWPORT_W
        vh = self.canvas.winfo_height() or VIEWPORT_H
        ox = max(0, (vw - CANVAS_W) / 2)
        oy = max(0, (vh - CANVAS_H) / 2)
        return ox, oy

    def m2px_pos(self, x_m, y_m):
        ox, oy = self.room_offset()
        return x_m * PIXELS_PER_METER + ox, y_m * PIXELS_PER_METER + oy

    def _dim_line(self, x1, y1, x2, y2, text, offset=16, vertical=False):
        """Draw a CAD-style dimension line with arrowheads and a millimeter label."""
        c = self.canvas
        c.create_line(x1, y1, x2, y2, fill="#66ccff", width=1,
                       arrow=tk.BOTH, arrowshape=(8, 10, 3))
        if vertical:
            c.create_text(x1 + offset, (y1 + y2) / 2, text=text,
                           fill="#66ccff", font=("Arial", 8), angle=90)
        else:
            c.create_text((x1 + x2) / 2, y1 - offset, text=text,
                           fill="#66ccff", font=("Arial", 8))

    def _draw_nearest_neighbor(self, table_items):
        """Highlight the live distance from the table most recently
        dragged on the Planner tab to whichever other table (including
        "Sposi") is currently closest to it. Recomputed from the model's
        live positions on every refresh, so it always reflects wherever
        the table was just dropped."""
        target = self.model.last_moved_table
        if not target:
            return
        positions = dict(table_items)
        if target not in positions:
            return
        candidates = dict(table_items)
        if SPECIAL_TABLE in self.model.table_positions:
            candidates[SPECIAL_TABLE] = self.model.table_positions[SPECIAL_TABLE]
        x1, y1 = positions[target]
        best = None
        for t2, (x2, y2) in candidates.items():
            if t2 == target:
                continue
            dist = math.hypot(x2 - x1, y2 - y1)
            if best is None or dist < best[0]:
                best = (dist, t2, x2, y2)
        if not best:
            return
        dist, t2, x2, y2 = best
        c = self.canvas
        px1, py1 = self.m2px_pos(x1, y1)
        px2, py2 = self.m2px_pos(x2, y2)
        mm = round(dist * 1000)
        c.create_line(px1, py1, px2, py2, fill="#ffcc00", width=2,
                       arrow=tk.BOTH, arrowshape=(8, 10, 3))
        c.create_text(
            (px1 + px2) / 2, (py1 + py2) / 2 - 10,
            text=f"{target} → {t2}: {mm} mm (nearest)",
            fill="#ffcc00", font=("Arial", 8, "bold")
        )

    def _draw_all_measurements(self, table_items):
        """'Show distance to closest table' mode: for EVERY table
        (including "Sposi"), draw a line + mm label to whichever other
        table is currently closest to it -- not a full pairwise mesh, just
        each table's own nearest neighbor. Recomputed live from the
        model's current positions. Room/fixture/table size labels are
        drawn regardless of this toggle -- see refresh(). The most
        recently moved table's line is additionally highlighted on top."""
        c = self.canvas
        all_items = list(table_items)
        if SPECIAL_TABLE in self.model.table_positions:
            all_items.append((SPECIAL_TABLE, self.model.table_positions[SPECIAL_TABLE]))
        drawn_pairs = set()
        for t1, (x1, y1) in all_items:
            best = None
            for t2, (x2, y2) in all_items:
                if t2 == t1:
                    continue
                dist = math.hypot(x2 - x1, y2 - y1)
                if best is None or dist < best[0]:
                    best = (dist, t2, x2, y2)
            if not best:
                continue
            dist, t2, x2, y2 = best
            pair = tuple(sorted((t1, t2)))
            if pair in drawn_pairs:
                continue
            drawn_pairs.add(pair)
            mm = round(dist * 1000)
            px1, py1 = self.m2px_pos(x1, y1)
            px2, py2 = self.m2px_pos(x2, y2)
            c.create_line(px1, py1, px2, py2, fill="#3a5a75", width=1, dash=(2, 3))
            c.create_text((px1 + px2) / 2, (py1 + py2) / 2, text=f"{mm} mm",
                           fill="#7fb2d9", font=("Arial", 6))
        # Still highlight the most recently moved table's nearest neighbor
        # on top, in a brighter color, so it's easy to spot among the rest.
        self._draw_nearest_neighbor(table_items)

    def refresh(self):
        """Redraw this tab from the model's current state. Safe to call at
        any time -- e.g. after a table is dragged on the Planner tab."""
        c = self.canvas
        c.delete("all")
        room_ox, room_oy = self.room_offset()
        c.create_rectangle(room_ox + 5, room_oy + 5, room_ox + CANVAS_W - 5, room_oy + CANVAS_H - 5,
                            outline="#333333", width=2)
        c.create_text(
            room_ox + 12, room_oy + 12, text=f"Room: {ROOM_L * 1000:.0f} x {ROOM_H * 1000:.0f} mm (read-only)",
            fill="#ffffff", font=("Arial", 10, "bold"), anchor="nw"
        )
        self._dim_line(room_ox + 5, room_oy + CANVAS_H - 5, room_ox + CANVAS_W - 5, room_oy + CANVAS_H - 5,
                        f"{ROOM_L * 1000:.0f} mm", offset=18)
        self._dim_line(room_ox + CANVAS_W - 5, room_oy + 5, room_ox + CANVAS_W - 5, room_oy + CANVAS_H - 5,
                        f"{ROOM_H * 1000:.0f} mm", offset=18, vertical=True)

        # Fixed fixtures
        for name, x_m, y_m, w_m, h_m in self.model.fixture_rects():
            px, py = self.m2px_pos(x_m, y_m)
            w, h = self.m2px(w_m), self.m2px(h_m)
            c.create_rectangle(px - w / 2, py - h / 2, px + w / 2, py + h / 2,
                                outline="#f5d76e", width=2)
            c.create_text(px, py, text=name, fill="#ffffff", font=("Arial", 9, "bold"))
            c.create_text(px, py + h / 2 + 10, text=f"{w_m * 1000:.0f} x {h_m * 1000:.0f} mm",
                          fill="#66ccff", font=("Arial", 7))

        # Special ("Sposi") table
        sx, sy = self.model.table_positions.get(SPECIAL_TABLE, (1.2, ROOM_H / 2))
        spx, spy = self.m2px_pos(sx, sy)
        c.create_rectangle(
            spx - SPECIAL_W_PX / 2, spy - SPECIAL_H_PX / 2,
            spx + SPECIAL_W_PX / 2, spy + SPECIAL_H_PX / 2,
            outline="#f5d76e", width=2
        )
        c.create_text(spx, spy, text=SPECIAL_TABLE, fill="#ffffff", font=("Arial", 9, "bold"))

        # Round guest tables at their current (live) positions
        clearance_r_px = self.m2px(Config.TABLE_CLEARANCE_DIAMETER_MM / 2000.0)
        table_r_px = self.m2px(Config.TABLE_TOP_DIAMETER_MM / 2000.0)
        table_items = [
            (t, self.model.table_positions[t])
            for t in self.model.tables
            if t != SPECIAL_TABLE and t in self.model.table_positions
        ]
        for t, (x_m, y_m) in table_items:
            px, py = self.m2px_pos(x_m, y_m)
            c.create_oval(px - clearance_r_px, py - clearance_r_px,
                          px + clearance_r_px, py + clearance_r_px,
                          outline="#888888", dash=(4, 3))
            c.create_oval(px - table_r_px, py - table_r_px,
                          px + table_r_px, py + table_r_px,
                          outline="#ffffff", width=2)
            c.create_text(px, py, text=t, fill="#ffffff", font=("Arial", 8, "bold"))
            c.create_text(
                px, py + clearance_r_px + 10,
                text=f"⌀{Config.TABLE_TOP_DIAMETER_MM}/{Config.TABLE_CLEARANCE_DIAMETER_MM} mm",
                fill="#66ccff", font=("Arial", 7)
            )

        if self.show_all_var.get():
            self._draw_all_measurements(table_items)
        else:
            self._draw_nearest_neighbor(table_items)
        c.configure(scrollregion=c.bbox("all"))

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
        ttk.Button(top, text="Export PDF", command=self.export_pdf).pack(side="right", padx=8, pady=8)
        ttk.Button(top, text="Reset Layout", command=self.on_reset).pack(side="right", padx=8, pady=8)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True)
        self.planner_frame = ttk.Frame(self.tabs)
        self.planner_frame.pack(fill="both", expand=True)
        self.canvas = PlannerCanvas(self.planner_frame, self.model)
        hbar = ttk.Scrollbar(self.planner_frame, orient="horizontal", command=self.canvas.xview)
        vbar = ttk.Scrollbar(self.planner_frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vbar.grid(row=0, column=1, sticky="ns")
        hbar.grid(row=1, column=0, sticky="ew")
        self.planner_frame.rowconfigure(0, weight=1)
        self.planner_frame.columnconfigure(0, weight=1)
        self.viewer = ViewerTab(self.tabs)
        self.technical_tab = TechnicalTab(self.tabs, self.model)
        # Keep the read-only Technical Layout tab in sync with the Planner:
        # it redraws every time the Planner canvas redraws (search, reset,
        # editor save) and, importantly, right after a table is dragged.
        self.canvas.on_change_callbacks.append(self.technical_tab.refresh)
        self.tabs.add(self.planner_frame, text="Planner")
        self.tabs.add(self.viewer, text="Viewer")
        self.tabs.add(self.technical_tab, text="Technical Layout")
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self.technical_tab.refresh())

    def on_search_change(self, *args):
        self.canvas.search_string = self.search_var.get().strip()
        self.canvas.draw()

    def on_reset(self):
        self.model.reset_layout()
        self.model.enforce_table_capacity()
        self.canvas.draw()

    def _capture_widget_image(self, widget):
        """Capture the given widget's contents as PNG bytes.

        Two strategies are tried, in order:
          1. An OS-level screen grab (PIL.ImageGrab) -- best fidelity, but
             needs a real, directly-accessible display and can fail under
             some X11/WSL setups (e.g. remote/forwarded displays that
             refuse the low-level XGetImage screen-capture call).
          2. For a Canvas widget, Tk's own PostScript export -- rendered
             from the canvas's draw list rather than the screen, so it
             works regardless of the display setup, at the cost of needing
             Ghostscript installed to rasterize the PostScript to PNG.
        Returns None (never raises) if neither works, so PDF export still
        succeeds -- just without that particular UI-image page.
        """
        self.update_idletasks()
        self.update()

        try:
            from PIL import ImageGrab
            x = widget.winfo_rootx()
            y = widget.winfo_rooty()
            w = widget.winfo_width()
            h = widget.winfo_height()
            if w > 0 and h > 0:
                img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                return buf.getvalue()
        except Exception:
            logging.info(
                "Screen grab unavailable for PDF export screenshot; "
                "trying the canvas's own PostScript export instead.",
                exc_info=True,
            )

        if isinstance(widget, tk.Canvas):
            try:
                from PIL import Image
                ps = widget.postscript(colormode="color")
                img = Image.open(io.BytesIO(ps.encode("utf-8")))
                img.load()
                buf = io.BytesIO()
                img.convert("RGB").save(buf, format="PNG")
                return buf.getvalue()
            except Exception:
                logging.exception(
                    "Canvas PostScript export also failed for PDF export screenshot "
                    "(this fallback needs Ghostscript installed on PATH)."
                )

        return None

    def export_pdf(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF files", "*.pdf")],
            initialfile="seating_arrangement.pdf",
        )
        if not path:
            return

        # Best-effort: capture a screenshot of the Planner and Technical
        # Layout tabs to embed as extra pages after the food-requirements
        # table. Switching tabs briefly changes what's on screen, then the
        # originally-selected tab is restored. If screenshots can't be taken
        # (e.g. ImageGrab unavailable), export still proceeds without them.
        extra_images = []
        previously_selected = None
        try:
            previously_selected = self.tabs.select()
            self.tabs.select(self.planner_frame)
            self.lift()
            planner_shot = self._capture_widget_image(self.canvas)
            if planner_shot:
                extra_images.append(("Planner Layout", planner_shot))

            self.tabs.select(self.technical_tab)
            self.lift()
            technical_shot = self._capture_widget_image(self.technical_tab.canvas)
            if technical_shot:
                extra_images.append(("Technical Layout", technical_shot))
        except Exception:
            logging.exception("Failed while capturing UI screenshots for PDF export")
        finally:
            if previously_selected:
                try:
                    self.tabs.select(previously_selected)
                except Exception:
                    pass

        try:
            self.model.save_pdf(path, extra_images=extra_images)
        except Exception as exc:
            messagebox.showerror("PDF export error", f"Failed to export PDF:\n{exc}")
            return
        if extra_images:
            messagebox.showinfo(
                "PDF exported",
                f"PDF saved to:\n{path}\n\n(Includes {len(extra_images)} UI image page(s).)",
            )
        else:
            messagebox.showinfo("PDF exported", f"PDF saved to:\n{path}")

    def on_close(self):
        self.model.save_json("seating_arrangement.json")
        self.model.save_csv("seating_arrangement.csv")
        self.destroy()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
    App().mainloop()
