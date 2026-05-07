#


✔ Scrollable room (horizontal + vertical)
✔ Logical room 30 m × 15 m, scaled to GUI
✔ Drag tables (all attendees move with them)
✔ Drag attendees between tables
✔ Live display: Table Name (count)
✔ Mandatory relationship field (auto‑added if missing)
✔ Deterministic priority mapping from relationship
✔ Dedicated Bride & Groom rectangular table, top center
✔ Table positions persisted in JSON
✔ Reset Layout button:

Groups by relationship
Seats Bride + Groom together
Places higher priority tables closer to Bride & Groom


## Create into Windows exe
- Use a venv to install PyInstaller
``pip install pyinstaller

- Build EXE
``pyinstaller --onefile --windowed wedding_seating.py

- EXE will appear in: 
11dist/wedding_seating.exe
