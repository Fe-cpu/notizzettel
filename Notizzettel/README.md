# NotizZettel – Simple Tray Task Manager

**NotizZettel** is a small, lightweight task tool for Windows that lives in the
system tray. It is ideal for work PCs or users who don't want a complex
cloud-based to-do app with accounts and admin rights.

## Features

- 📝 Separate tabs for active and finished tasks
- 📅 Due date per task (format: `DD.MM.YYYY`)
- 🎨 Priorities with colors:
  - Green – not urgent
  - Blue – medium
  - Red – important
- 🔁 Recurring tasks:
  - None / daily / weekly / monthly
- 🔔 Pop-up reminder:
  - shows overdue and due-today tasks
- 🔍 Filtering & search:
  - by priority (including "Overdue")
  - by date (from)
  - by name
  - quick filters: "Today only" & "This week"
- 📂 Finished tasks:
  - stored with all information
  - can be reactivated as active tasks
- 📌 Runs in the system tray
- 💾 Local JSON storage only
  - `C:\Users\<username>\NotizZettel\tasks.json`
  - no cloud, no account

## Installation (Python)

Requirements: Python 3.9+ on Windows.

```bash
git clone https://github.com/YOUR_USERNAME/notizzettel.git
cd notizzettel
pip install -r requirements.txt
python notizzettel_de.py   # German version
# or
python notizzettel_en.py   # English version

