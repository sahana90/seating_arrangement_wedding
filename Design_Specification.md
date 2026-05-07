# Wedding Seating Planner & Viewer — Final Architecture (Failure‑Resilient, Language‑Agnostic Spec)

## 0) Goal (What the app must do)

Build a desktop GUI tool with **two tabs**:

### 0.1) Global Constraints (Configuration)

- `TABLE_MIN_CAPACITY = 5` (minimum allowed attendees per normal table)
- `TABLE_MAX_CAPACITY = 10` (maximum allowed attendees per normal table)
- These constraints apply to all **normal** tables; the special `"Bride & Groom"` table is exempt unless explicitly stated.

1.  **Planner (interactive)**

*   Visualize a **room** (logical coordinate system in meters).
*   Render **tables** and **attendees** around tables.
*   Allow **dragging tables** (except the special Bride & Groom table) to new positions.
*   Allow **dragging attendees** and **reassigning them to a new table** **only if the attendee circle overlaps the target table circle** (area overlap rule).
*   Always show attendee **names** on the canvas.
*   Provide **scrollbars** (horizontal + vertical).
*   Provide a **Reset Layout** button that re-groups and repositions deterministically with priority rules.

2.  **Viewer (read‑only)**

*   Same rendering as Planner (tables, attendees, names, chairs if implemented).
*   No user interaction (no drag, no drop, no editing).
*   Has **Load seating JSON** action that loads a file in the same format as `seating_arrangement.json` and renders it.
*   Has **scrollbars** (horizontal + vertical) identical to Planner.

On application close, persist the current seating to **JSON + CSV**.

***

## 1) Data Contracts (Robust, Backward Compatible)

### 1.1 `attendees.json` (input for generation/fallback)

Must be valid JSON object with:

```json
{
  "attendees": [
    {
      "name": "string (required)",
      "side": "Bride|Groom|... (optional)",
      "relationship": "optional (see RELATIONSHIPS list below)",
      "category": "optional (int or string parseable to int)",
      "VIP": "optional bool"
    }
  ]
}
```

**Normalization rules (must be applied at load time):**

*   If an attendee is missing `_id`, generate one.
*   If `relationship` is missing, assign it per §3.1.
*   `category` must be overwritten/reassigned to the priority value derived from `relationship` (see §3.2). Treat `category` as integer.
*   `VIP` attendees may optionally be excluded during fallback generation (recommended).

### 1.2 `seating_arrangement.json` (primary load/save)

Must be valid JSON object with:

*   A reserved optional key `_table_positions`
*   All other keys represent tables: `"Table 1"`, `"Table 2"`, … and a special `"Bride & Groom"` table.

```json
{
  "_table_positions": {
    "Bride & Groom": [15.0, 1.5],
    "Table 1": [10.2, 6.1]
  },
  "Bride & Groom": [
    {
      "_id": "string required",
      "name": "string required",
      "relationship": "Bride|Groom",
      "category": 0|1
    }
  ],
  "Table 1": [
    {
      "_id": "string required",
      "name": "string required",
      "relationship": "Immediate Family|Extended Family|... ",
      "category": "int priority derived from relationship"
    }
  ]
}
```

**Backward compatibility:**

*   If `_table_positions` is missing, create deterministic positions via Reset Layout (§6).
*   If attendee objects are missing `_id`, add it.
*   If attendee objects are missing `relationship`, assign it (§3.1).
*   If `category` is missing or inconsistent, recompute it from `relationship` (§3.2).

### 1.3 `seating_arrangement.csv` (export on close)

Columns (header required):

*   `Table, Guest, Relationship, Category`
*   Each row maps one attendee to their table.

***

## 2) Coordinate System & Room Rendering

### 2.1 Room size and scaling

*   Logical room dimensions:
    *   `ROOM_L = 30m` (length)
    *   `ROOM_H = 15m` (height)
*   Canvas pixel size is derived:
    *   `PIXELS_PER_METER` is fixed (e.g., 50–80 px/m), or configurable.
    *   Canvas scroll region must cover full room area:
        *   `CANVAS_W = ROOM_L * PIXELS_PER_METER`
        *   `CANVAS_H = ROOM_H * PIXELS_PER_METER`

### 2.2 Background

*   Canvas background must be **black** for high contrast.

### 2.3 Visible viewport

*   Window may show only a portion of the canvas; provide **horizontal and vertical scrollbars**.
*   Scrollbars must work in both Planner and Viewer.

***

## 3) Relationship & Priority Model (Foolproof Rules)

### 3.1 Relationship set (ordered by priority, highest first)

Define a constant ordered list:

*   `RELATIONSHIPS = [`
    *   `"Bride"`,
    *   `"Groom"`,
    *   `"Immediate Family"`,
    *   `"Extended Family"`,
    *   `"Childhood Friends"`,
    *   `"UniversityFriends"`,
    *   `"Colleagues"`
*   `]`

### 3.2 Category assignment (must be deterministic)

*   `category` is always an integer equal to `RELATIONSHIPS.index(relationship)`.
*   Lower category means **higher priority**.

### 3.3 Guaranteed uniqueness for Bride and Groom

When normalizing attendees:

*   Ensure **exactly one** attendee has relationship `"Bride"`.
*   Ensure **exactly one** attendee has relationship `"Groom"`.
*   If missing, render color grey.
*   If multiple exist, keep the first deterministically (e.g., by stable sorting on `_id`), demote others to a non-special relationship.

### 3.4 Stable ID requirement

Each attendee must have a stable `_id`:

*   If absent, generate one (UUID or deterministic hash).
*   `_id` must be persisted in JSON to allow reliable moves/removals even if names duplicate.

***

## 4) Table Types & Layout Constraints

### 4.1 Special table: `"Bride & Groom"`

*   Must exist always.
*   Must contain the two special attendees (relationship `"Bride"` and `"Groom"`).
*   **Fixed at the top center**:
    *   Position `(ROOM_L/2, y_top)` where `y_top ~ 1.5m`
*   Rendered as a **rectangle** (distinct from circular tables).
*   Must be **non-draggable**.
*   No regular attendee should be drop‑assigned into this table (optional but recommended).

### 4.2 Normal tables

*   Named e.g. `"Table 1"`, `"Table 2"`, or may have prefixes in grouping operations.
*   Rendered as **circles** with a fixed visual radius.
*   Must always stay **below** the special table:
    *   `table_y >= special_table_bottom + margin`

### 4.3 Table label must include count (real-time)

For every table, label format:

*   `"Table X (N)"`
*   `"Bride & Groom (2)"`

This updates immediately after moves/reset/load.

***

### 4.4 Table Capacity Constraints (Min/Max)

- Normal tables must respect capacity constraints:
  - Minimum attendees per table: `TABLE_MIN_CAPACITY = 5`
  - Maximum attendees per table: `TABLE_MAX_CAPACITY = 10`
- The special table `"Bride & Groom"` is exempt (fixed at 2 attendees) unless explicitly configured otherwise.
- The UI must provide feedback when a table violates these constraints:
  - If `count > TABLE_MAX_CAPACITY`: table shown in **warning/overflow** style.
  - If `count < TABLE_MIN_CAPACITY`: table shown in **underflow** style (optional but recommended).



## 5) Attendee Rendering & Visual Encoding

### 5.1 Attendee circles

*   Render each attendee as a small circle.
*   Render attendee name text near the circle (always visible, not tooltip-only).
*   Name text must move with the attendee during dragging.

### 5.2 Chair rendering (optional but requested)

*   Render “chair” markers around each table (small dots/rectangles).
*   Chairs are read-only and decorative; they do not affect assignments.

### 5.3 Color rules (final)

*   Base hue by side:
    *   Bride-related attendees: **red**
    *   Groom-related attendees: **blue**
*   Transparency effect by category:
    *   “Lower category” → “lower transparency” (i.e., *more transparent / dimmer*)
    *   “Higher category” → *more opaque / stronger color*
*   If toolkit does not support alpha, simulate transparency by blending with background (black).

**Important:** Colors must never appear as grayscale due to computation; always remain red-family or blue-family.

### 5.4 Side determination (for grouping and color)

Use in priority order:

1.  If attendee has explicit `side` field and it is `"Bride"` or `"Groom"`, use it.
2.  Else infer from `relationship`:
    *   `"Bride"`, `"Immediate Family"`, `"Extended Family"` → Bride side
    *   `"Groom"` and all others → Groom side (or configurable)

***

## 6) Deterministic Placement Algorithms

### 6.1 Table positions

Single source of truth: `_table_positions[table_name] = (x_m, y_m)`

*   If positions exist in JSON, use them (preserve user adjustments).
*   If missing for some tables, generate them deterministically (Reset Layout).

### 6.2 Reset Layout (must be deterministic and non-overlapping)

Triggered by a **Reset Layout** button on Planner tab.

Reset Layout must generate tables that satisfy:

- Each normal table has attendees count within `[TABLE_MIN_CAPACITY, TABLE_MAX_CAPACITY]` where possible.
- If total attendees make it impossible to satisfy both min and max simultaneously:
  - Respect `TABLE_MAX_CAPACITY` as a hard constraint
  - Min constraint becomes best-effort with warnings for underfilled tables
- During grouping operations (e.g., by relationship or by side), if a group exceeds max capacity:
  - Split into multiple tables of the same group (e.g., `Immediate Family 1`, `Immediate Family 2`)
- If a group is below minimum capacity:
  - Either merge with the nearest-priority compatible group (recommended), or allow under-capacity with warning.
1.  Normalize all attendees (§3).
2.  Ensure Bride & Groom table at top center (§4.1).
3.  Group attendees by most common attribute (minimum requirement):
    *   Group by `relationship` (recommended and deterministic).
4.  Ensure all normal tables are placed **below** the special table, starting from:
    *   `base_y = special_table_bottom + margin`
5.  Position tables so that higher priority groups are closer to Bride & Groom:
    *   Example: place tables in rows below special table, ordered by table priority:
        *   `table_priority = min(category in table)`
6.  Ensure no overlaps:
    *   Table centers separated by at least `(2*table_radius + spacing)` in pixel units (or equivalent meters).

***

## 7) Drag & Drop Interaction Model (Planner Tab)

### 7.1 Dragging tables

*   User can drag a table by grabbing table shape/label (drag handle).
*   When table moves, all attendees associated with it move visually (group move).
*   On release, update `_table_positions` in meters.

Constraints:

*   Normal tables cannot be moved above the special table boundary.
*   Tables are clamped within room bounds.

### 7.2 Dragging attendees

*   Attendee drag moves BOTH circle + text.
*   On release:
    *   Determine the attendee circle’s **actual current center** from its rendered geometry (not mouse pointer).
    *   Determine if it overlaps any table circle.

### 7.3 Drop target rule: **Overlap area requirement**

Assign attendee to a new table only if:

*   Distance between centers `< (r_attendee + r_table)`

If multiple tables overlap simultaneously:

*   Choose the table with smallest center distance (closest) or greatest overlap depth (deterministic tie-breaking).

### 7.4 Update model & redraw

When reassignment occurs:

*   Remove attendee from old table list (by `_id`, not by name).
*   Add to new table list.
*   Rebuild the canvas scene from model state (full redraw acceptable).
*   Table labels update counts immediately.

### 7.5 Capacity Enforcement on Reassignment (Planner)

On attendee drop (after overlap target is detected):
- If moving the attendee would cause the destination table to exceed `TABLE_MAX_CAPACITY`, the reassignment must be rejected:
  - Attendee remains in the original table
  - Optional: show a brief notification / highlight the destination table
- (Optional policy) If removing the attendee causes the source table to drop below `TABLE_MIN_CAPACITY`, one of the following must occur:
  - Allow the move but mark the source table as under-capacity (visual warning), OR
  - Reject the move (strict enforcement)
- The chosen policy must be deterministic and documented; default recommendation:
  - **Strict max enforcement**, **soft min enforcement (warn only)**.


### 7.6 Prevent event-binding glitches (foolproof requirement)

Implementations must avoid “drag state lost” bugs:

*   Ensure event handlers do not conflict (e.g., attendee handlers should not trigger table handlers).
*   Use event propagation control (e.g., return/stop propagation).
*   Do not use shared mutable drag state across multiple simultaneous handlers without safeguards.
*   Always compute drop using the actual attendee item position, not mouse position.

***

## 8) Viewer Tab (Read-Only, Scrollable, File Load)

### 8.1 UI layout

Viewer tab contains:

*   A **Load seating JSON** button.
*   A label showing the loaded file path (optional).
*   A read‑only canvas with H+V scrollbars.

### 8.2 Behavior

*   Loading a file replaces viewer’s internal model state and re-renders.
*   Viewer must support full `seating_arrangement.json` format including `_table_positions`.
*   Viewer must not modify planner model or write files unless explicitly requested.

***

## 9) Optional Side Panel Summary (Planner recommended, Viewer optional)

Provide a right-side panel showing:

*   Table list
*   Per-table counts
*   Bride-side vs Groom-side counts
*   Category range
*   Representative colors used (e.g., swatches)

Controls (recommended):

*   Filter tables: Both / Bride-only / Groom-only
*   Button: **Group by side** (see §10)

***

## 10) Grouping Operation: “Group by side” (Bride-only / Groom-only tables)

When user chooses “Group by side”:

*   Keep `"Bride & Groom"` table intact.
*   Move all non-special attendees into new tables such that each table contains only one side:
    *   Bride-side tables: `B-Table 1`, `B-Table 2`, …
    *   Groom-side tables: `G-Table 1`, `G-Table 2`, …
*   Maintain capacity constraints if desired (e.g., `SEATS_PER_TABLE`).
*   Run Reset Layout after regrouping.

***

## 11) Persistence Rules (Must be failure-resistant)

### 11.1 Save on close

On application close:

*   Write `seating_arrangement.json` (including `_table_positions` and attendee `_id` fields).
*   Write `seating_arrangement.csv`.

### 11.2 Atomic saves (foolproof)

To avoid corrupted files:

*   Write to a temporary file first (`.tmp`)
*   Validate serialization success
*   Rename/replace original atomically

### 11.3 Load precedence

On startup:

1.  Try load `seating_arrangement.json`
2.  If missing/invalid → generate from `attendees.json`
3.  If both invalid → show a clear error and launch with empty/default state

***

## 12) Failure Handling & Diagnostics (Mandatory)

### 12.1 Handle invalid/missing files gracefully

*   Missing `attendees.json`:
    *   show error “File not found” and do not crash
*   Empty or invalid JSON:
    *   show error “Invalid JSON” with filename and line/column if possible
*   Missing required key `"attendees"` or wrong type:
    *   show error and stop generation path

### 12.2 Runtime robustness

*   Never crash on drag/drop:
    *   Guard all access to drag context (it may be null due to event ordering)
*   Removing attendee from old table must be done by `_id` to avoid failures when duplicates exist.

### 12.3 Logging (recommended)

*   Log key actions:
    *   load success/failure
    *   reset grouping applied
    *   move operations (attendee id, from, to)
*   Logs should not block UI.

***

## 13) Functional Requirements Checklist (Final)

Planner:

*   [ ] Load `seating_arrangement.json` else fallback generate from `attendees.json`.
*   [ ] Normalize attendees: ensure `_id`, ensure single Bride & Groom, recompute category.
*   [ ] Render room (black background), tables, attendee circles, attendee names.
*   [ ] Show `(count)` next to each table name.
*   [ ] Scrollbars: horizontal + vertical.
*   [ ] Drag tables (except special); persist updated positions.
*   [ ] Drag attendees; reassign only if attendee circle overlaps table circle.
*   [ ] Reset Layout: deterministic, below special table, no overlap.
*   [ ] Save JSON + CSV on close with atomic save.
*   [ ] Enforce table capacity constraints: normal tables must stay within min=5 and max=10 (max strict; min warn or strict per policy).
*   [ ] Reset Layout produces tables that satisfy min/max where feasible; splits oversized groups; warns/merges undersized groups.

Viewer:

*   [ ] Same rendering as planner.
*   [ ] No interactions.
*   [ ] Load seating JSON file and render exactly that plan.
*   [ ] Scrollbars: horizontal + vertical.

Optional/Recommended:

*   [ ] Side panel summary per table + representative colors.
*   [ ] Group-by-side action and filters.
