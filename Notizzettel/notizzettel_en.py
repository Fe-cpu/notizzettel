import tkinter as tk
from tkinter import ttk, messagebox
import json
import os
from datetime import datetime, timedelta
import threading
import calendar

import pystray
from PIL import Image, ImageDraw

# --- Configuration / constants -----------------------------------------

BG_COLOR = "#fff9c4"  # light yellow, sticky-note style

# label in filter -> internal priority
PRIORITY_VALUE_BY_LABEL = {
    "Red": "red",
    "Yellow": "blue",   # "Yellow" in UI, internally blue
    "Green": "green",
}

# internal priority -> color
PRIORITY_COLOR = {
    "red": "#ff4040",
    "blue": "#01B3FA",
    "green": "#28a745",
    "yellow": "#01B3FA",  # handle old data where priority == "yellow"
}

# recurring tasks
RECURRING_OPTIONS = ["None", "Daily", "Weekly", "Monthly"]
RECUR_LABEL_TO_VALUE = {
    "None": None,
    "Daily": "daily",
    "Weekly": "weekly",
    "Monthly": "monthly",
}
RECUR_VALUE_TO_LABEL = {
    None: "None",
    "daily": "Daily",
    "weekly": "Weekly",
    "monthly": "Monthly",
}


def parse_date(date_str: str):
    """Parse date in DD.MM.YYYY or YYYY-MM-DD; return datetime or None."""
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    return None


def add_months(dt: datetime, months: int = 1) -> datetime:
    """Add full months in a safe way (for monthly recurring tasks)."""
    month = dt.month - 1 + months
    year = dt.year + month // 12
    month = month % 12 + 1
    last_day = calendar.monthrange(year, month)[1]
    day = min(dt.day, last_day)
    return datetime(year, month, day)


APP_DIR = os.path.join(os.path.expanduser("~"), "NotizZettel")
os.makedirs(APP_DIR, exist_ok=True)
FILE = os.path.join(APP_DIR, "tasks.json")


def load_data():
    if os.path.exists(FILE):
        with open(FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                data = {}
    else:
        data = {}
    data.setdefault("active", [])
    data.setdefault("finished", [])
    return data


def save_data(data):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


class TaskApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NotizZettel")

        # place window top-right
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        width, height = 380, 520
        x = screen_w - width - 20
        y = 20
        self.root.geometry(f"{width}x{height}+{x}+{y}")

        # background
        self.root.configure(bg=BG_COLOR)
        style = ttk.Style(self.root)
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR)
        style.configure("TLabelframe", background=BG_COLOR)
        style.configure("TLabelframe.Label", background=BG_COLOR)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.data = load_data()
        self.sorted_active_tasks = []
        self.sorted_finished_tasks = []

        # quick filter: None / "today" / "week"
        self.active_quick_filter = None

        tab_control = ttk.Notebook(root)
        self.tab_new = ttk.Frame(tab_control)
        self.tab_active = ttk.Frame(tab_control)
        self.tab_finished = ttk.Frame(tab_control)

        tab_control.add(self.tab_new, text="New Task")
        tab_control.add(self.tab_active, text="Active Tasks")
        tab_control.add(self.tab_finished, text="Finished Tasks")
        tab_control.pack(expand=1, fill="both")

        self.build_new_tab()
        self.build_active_tab()
        self.build_finished_tab()

        self.tray_icon = None

        # start reminder after small delay
        self.root.after(800, self.check_reminders)

    # --- Tray handling --------------------------------------------------

    def on_close(self):
        self.root.withdraw()

    def show_window(self):
        self.root.deiconify()
        self.root.lift()
        self.root.focus_force()

    def quit(self):
        if self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception:
                pass
        self.root.quit()

    def create_image(self, width=64, height=64):
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rectangle((8, 8, width - 8, height - 8), fill=(100, 200, 120, 255))
        draw.line((14, 20, width - 14, 20), fill=(255, 255, 255, 255), width=3)
        draw.line((14, 30, width - 20, 30), fill=(255, 255, 255, 255), width=3)
        draw.line((14, 40, width - 24, 40), fill=(255, 255, 255, 255), width=3)
        return image

    # --- Reminder / pop-up ---------------------------------------------

    def check_reminders(self):
        """Popup for today's and overdue tasks, reschedules itself."""
        today = datetime.today().date()
        due_today = []
        overdue = []

        for t in self.data.get("active", []):
            d = parse_date(t.get("date", ""))
            if not d:
                continue
            d_date = d.date()
            if d_date < today:
                overdue.append(t)
            elif d_date == today:
                due_today.append(t)

        if overdue or due_today:
            lines = []
            if overdue:
                lines.append("⚠ Overdue:")
                lines += [f"- {t['name']} (Due: {t['date']})" for t in overdue]
                lines.append("")
            if due_today:
                lines.append("⭐ Due today:")
                lines += [f"- {t['name']} (Due: {t['date']})" for t in due_today]
            messagebox.showinfo("Reminder – due tasks", "\n".join(lines))

        # check again every 6 hours
        self.root.after(6 * 60 * 60 * 1000, self.check_reminders)

    # --- Tab: New Task --------------------------------------------------

    def build_new_tab(self):
        frame = self.tab_new

        ttk.Label(frame, text="Due date (DD.MM.YYYY):").pack(pady=5)
        self.entry_date = ttk.Entry(frame)
        self.entry_date.pack(pady=5, fill="x", padx=10)

        ttk.Label(frame, text="Name:").pack(pady=5)
        self.entry_name = ttk.Entry(frame)
        self.entry_name.pack(pady=5, fill="x", padx=10)

        ttk.Label(frame, text="Info (text field):").pack(pady=5)
        self.entry_info = tk.Text(frame, height=7, bg="white")
        self.entry_info.pack(pady=5, padx=10, fill="both", expand=True)

        ttk.Label(frame, text="Priority:").pack(pady=5)
        self.priority = tk.StringVar(value="green")
        prio_frame = ttk.Frame(frame)
        prio_frame.pack()

        ttk.Radiobutton(
            prio_frame, text="Not urgent (green)", variable=self.priority, value="green"
        ).pack(anchor="w")
        ttk.Radiobutton(
            prio_frame, text="Medium (blue)", variable=self.priority, value="blue"
        ).pack(anchor="w")
        ttk.Radiobutton(
            prio_frame, text="Important (red)", variable=self.priority, value="red"
        ).pack(anchor="w")

        ttk.Label(frame, text="Recurrence:").pack(pady=5)
        self.recurrence_var = tk.StringVar(value="None")
        rec_combo = ttk.Combobox(
            frame,
            textvariable=self.recurrence_var,
            state="readonly",
            values=RECURRING_OPTIONS,
        )
        rec_combo.pack(pady=5, fill="x", padx=10)

        ttk.Button(frame, text="Save task", command=self.save_task).pack(pady=10)

    def save_task(self):
        name = self.entry_name.get().strip()
        date_str = self.entry_date.get().strip()
        info = self.entry_info.get("1.0", "end").strip()
        priority = self.priority.get()
        rec_label = self.recurrence_var.get()
        recurrence = RECUR_LABEL_TO_VALUE.get(rec_label)

        if not name or not date_str:
            messagebox.showwarning("Error", "Please enter a name and due date.")
            return

        try:
            parsed = datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            messagebox.showwarning(
                "Error",
                "Please use date format DD.MM.YYYY (e.g. 20.10.2000).",
            )
            return

        created_date = datetime.now().strftime("%d.%m.%Y")

        self.data["active"].append(
            {
                "name": name,
                "date": parsed.strftime("%d.%m.%Y"),
                "info": info,
                "priority": priority,
                "created_date": created_date,
                "recurrence": recurrence,
            }
        )

        save_data(self.data)
        self.update_active_list()
        messagebox.showinfo("Saved", "Task has been added.")

        self.entry_name.delete(0, tk.END)
        self.entry_date.delete(0, tk.END)
        self.entry_info.delete("1.0", tk.END)
        self.priority.set("green")
        self.recurrence_var.set("None")

    # --- Tab: Active Tasks ---------------------------------------------

    def build_active_tab(self):
        frame = self.tab_active

        filter_frame = ttk.LabelFrame(frame, text="Filter / Sorting")
        filter_frame.pack(fill="x", padx=10, pady=(5, 0))

        ttk.Label(filter_frame, text="Priority:").grid(
            row=0, column=0, padx=2, pady=2, sticky="w"
        )
        self.active_filter_priority = ttk.Combobox(
            filter_frame,
            state="readonly",
            values=["All", "Red", "Yellow", "Green", "Overdue"],
            width=12,
        )
        self.active_filter_priority.current(0)
        self.active_filter_priority.grid(row=0, column=1, padx=2, pady=2)

        ttk.Label(filter_frame, text="Sorting:").grid(
            row=0, column=2, padx=2, pady=2, sticky="w"
        )
        self.active_sort_order = ttk.Combobox(
            filter_frame,
            state="readonly",
            values=[
                "Date ascending (earliest first)",
                "Date descending (latest first)",
            ],
            width=28,
        )
        self.active_sort_order.current(0)
        self.active_sort_order.grid(row=0, column=3, padx=2, pady=2)

        ttk.Label(filter_frame, text="From date:").grid(
            row=1, column=0, padx=2, pady=2, sticky="w"
        )
        self.active_filter_date = ttk.Entry(filter_frame, width=12)
        self.active_filter_date.grid(row=1, column=1, padx=2, pady=2, sticky="w")
        ttk.Label(filter_frame, text="(DD.MM.YYYY)").grid(
            row=1, column=2, padx=2, pady=2, sticky="w"
        )

        ttk.Label(filter_frame, text="Search (name):").grid(
            row=2, column=0, padx=2, pady=2, sticky="w"
        )
        self.active_search_name = ttk.Entry(filter_frame, width=20)
        self.active_search_name.grid(
            row=2, column=1, columnspan=2, padx=2, pady=2, sticky="w"
        )

        ttk.Button(
            filter_frame, text="Apply", command=self.apply_active_manual_filter
        ).grid(row=2, column=3, padx=2, pady=2, sticky="e")

        ttk.Button(
            filter_frame, text="Today only", command=self.set_filter_today
        ).grid(row=3, column=0, padx=2, pady=2, sticky="w")
        ttk.Button(
            filter_frame, text="This week", command=self.set_filter_week
        ).grid(row=3, column=1, padx=2, pady=2, sticky="w")

        self.active_list = tk.Listbox(frame, height=9, bg="white")
        self.active_list.pack(side="top", padx=10, pady=10, fill="both", expand=True)
        self.active_list.bind("<<ListboxSelect>>", self.show_active_details)

        details_frame = ttk.Frame(frame)
        details_frame.pack(pady=5, padx=10, fill="both", expand=True)

        header_frame = ttk.Frame(details_frame)
        header_frame.pack(fill="x")

        self.details_name = tk.Label(
            header_frame,
            text="",
            anchor="w",
            font=("Segoe UI", 10, "bold"),
            bg=BG_COLOR,
        )
        self.details_name.pack(side="left", expand=True, fill="x")

        self.details_enddate = tk.Label(
            header_frame,
            text="",
            anchor="e",
            bg=BG_COLOR,
        )
        self.details_enddate.pack(side="right")

        self.details_info = tk.Label(
            details_frame,
            text="",
            justify="left",
            anchor="nw",
            wraplength=330,
            bg=BG_COLOR,
        )
        self.details_info.pack(fill="both", expand=True, pady=(5, 0))

        self.details_created = tk.Label(
            details_frame,
            text="",
            anchor="w",
            bg=BG_COLOR,
        )
        self.details_created.pack(fill="x", pady=(5, 0))

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(pady=5)

        ttk.Button(
            btn_frame, text="Edit task", command=self.edit_active_task
        ).pack(side="left", padx=5)
        ttk.Button(
            btn_frame, text="Complete task", command=self.finish_task
        ).pack(side="left", padx=5)

        self.update_active_list()

    def apply_active_manual_filter(self):
        self.active_quick_filter = None
        self.update_active_list()

    def set_filter_today(self):
        self.active_quick_filter = "today"
        self.active_filter_date.delete(0, tk.END)
        self.update_active_list()

    def set_filter_week(self):
        self.active_quick_filter = "week"
        self.active_filter_date.delete(0, tk.END)
        self.update_active_list()

    def update_active_list(self):
        self.active_list.delete(0, tk.END)

        prio_filter_label = self.active_filter_priority.get()
        show_only_overdue = prio_filter_label == "Overdue"
        if prio_filter_label in ("All", "Overdue"):
            prio_filter_value = None
        else:
            prio_filter_value = PRIORITY_VALUE_BY_LABEL.get(prio_filter_label)

        date_filter_str = self.active_filter_date.get().strip()
        filter_date = None
        if date_filter_str:
            filter_date = parse_date(date_filter_str)
            if not filter_date:
                messagebox.showwarning(
                    "Error",
                    "The filter date is invalid. Please use DD.MM.YYYY.",
                )
                filter_date = None

        search_term = self.active_search_name.get().strip().lower()

        sort_choice = self.active_sort_order.get()
        descending = sort_choice.startswith("Date descending")

        today = datetime.today().date()
        week_ahead = today + timedelta(days=7)

        def passes_filters(t):
            prio = t.get("priority")
            if prio == "yellow":
                prio = "blue"  # old data

            if prio_filter_value and prio != prio_filter_value:
                return False

            d = parse_date(t.get("date", ""))
            d_date = d.date() if d else None

            if filter_date is not None:
                if d is None or d < filter_date:
                    return False

            if show_only_overdue:
                if d_date is None or d_date >= today:
                    return False

            if self.active_quick_filter == "today":
                if d_date != today:
                    return False
            elif self.active_quick_filter == "week":
                if d_date is None or not (today <= d_date <= week_ahead):
                    return False

            if search_term and search_term not in t.get("name", "").lower():
                return False

            return True

        def sort_key(t):
            d = parse_date(t.get("date", "")) or datetime.max
            return d

        filtered = [t for t in self.data["active"] if passes_filters(t)]
        self.sorted_active_tasks = sorted(filtered, key=sort_key, reverse=descending)

        for t in self.sorted_active_tasks:
            d = parse_date(t.get("date", ""))
            d_date = d.date() if d else None
            overdue = d_date is not None and d_date < today

            display_text = f"● {t['name']} ({t['date']})"
            if overdue:
                display_text = f"⚠ {display_text}"

            self.active_list.insert(tk.END, display_text)

            prio = t.get("priority", "green")
            if prio == "yellow":
                prio = "blue"
            color = PRIORITY_COLOR.get(prio, "#000000")
            if overdue:
                color = "#ff0000"

            idx = self.active_list.size() - 1
            self.active_list.itemconfig(idx, fg=color)

        self.clear_active_details()

    def clear_active_details(self):
        self.details_name.config(text="")
        self.details_enddate.config(text="", fg="black")
        self.details_info.config(text="")
        self.details_created.config(text="")

    def show_active_details(self, event):
        selection = self.active_list.curselection()
        if not selection:
            return

        index = selection[0]
        if index >= len(self.sorted_active_tasks):
            return

        task = self.sorted_active_tasks[index]

        self.details_name.config(text=task["name"])

        d = parse_date(task.get("date", ""))
        today = datetime.today().date()
        if d is not None and d.date() < today:
            self.details_enddate.config(
                text=f"Due: {task['date']} – OVERDUE!", fg="red"
            )
        else:
            self.details_enddate.config(text=f"Due: {task['date']}", fg="black")

        self.details_info.config(text=task["info"])
        created = task.get("created_date", "?")
        rec_label = RECUR_VALUE_TO_LABEL.get(task.get("recurrence"), "None")
        self.details_created.config(
            text=f"Created: {created} | Recurrence: {rec_label}"
        )

    def get_selected_active_task(self):
        selection = self.active_list.curselection()
        if not selection:
            messagebox.showwarning(
                "Notice", "Please select an active task first."
            )
            return None, None

        index = selection[0]
        if index >= len(self.sorted_active_tasks):
            return None, None

        task = self.sorted_active_tasks[index]

        try:
            orig_index = self.data["active"].index(task)
        except ValueError:
            messagebox.showerror("Error", "Task could not be found.")
            return None, None

        return task, orig_index

    def edit_active_task(self):
        task, orig_index = self.get_selected_active_task()
        if task is None:
            return

        edit_win = tk.Toplevel(self.root)
        edit_win.title("Edit task")
        edit_win.geometry("350x380")
        edit_win.configure(bg=BG_COLOR)
        edit_win.grab_set()

        ttk.Label(edit_win, text="Name:").pack(pady=5)
        name_entry = ttk.Entry(edit_win)
        name_entry.pack(pady=5, fill="x", padx=10)
        name_entry.insert(0, task["name"])

        ttk.Label(edit_win, text="Due date (DD.MM.YYYY):").pack(pady=5)
        date_entry = ttk.Entry(edit_win)
        date_entry.pack(pady=5, fill="x", padx=10)
        date_entry.insert(0, task["date"])

        ttk.Label(edit_win, text="Info:").pack(pady=5)
        info_text = tk.Text(edit_win, height=6, bg="white")
        info_text.pack(pady=5, padx=10, fill="both", expand=True)
        info_text.insert("1.0", task["info"])

        ttk.Label(edit_win, text="Priority:").pack(pady=5)
        prio_var = tk.StringVar(value=task.get("priority", "green"))
        prio_frame = ttk.Frame(edit_win)
        prio_frame.pack()

        ttk.Radiobutton(
            prio_frame,
            text="Not urgent (green)",
            variable=prio_var,
            value="green",
        ).pack(anchor="w")
        ttk.Radiobutton(
            prio_frame,
            text="Medium (yellow)",
            variable=prio_var,
            value="blue",
        ).pack(anchor="w")
        ttk.Radiobutton(
            prio_frame,
            text="Important (red)",
            variable=prio_var,
            value="red",
        ).pack(anchor="w")

        ttk.Label(edit_win, text="Recurrence:").pack(pady=5)
        rec_var = tk.StringVar(
            value=RECUR_VALUE_TO_LABEL.get(task.get("recurrence"), "None")
        )
        rec_combo = ttk.Combobox(
            edit_win,
            textvariable=rec_var,
            state="readonly",
            values=RECURRING_OPTIONS,
        )
        rec_combo.pack(pady=5, fill="x", padx=10)

        def save_changes():
            new_name = name_entry.get().strip()
            new_date_str = date_entry.get().strip()
            new_info = info_text.get("1.0", "end").strip()
            new_prio = prio_var.get()
            new_rec_label = rec_var.get()
            new_recurrence = RECUR_LABEL_TO_VALUE.get(new_rec_label)

            if not new_name or not new_date_str:
                messagebox.showwarning(
                    "Error", "Please enter a name and due date."
                )
                return

            try:
                parsed = datetime.strptime(new_date_str, "%d.%m.%Y")
            except ValueError:
                messagebox.showwarning(
                    "Error", "Please use date format DD.MM.YYYY."
                )
                return

            self.data["active"][orig_index].update(
                {
                    "name": new_name,
                    "date": parsed.strftime("%d.%m.%Y"),
                    "info": new_info,
                    "priority": new_prio,
                    "recurrence": new_recurrence,
                }
            )

            save_data(self.data)
            self.update_active_list()
            edit_win.destroy()

        ttk.Button(edit_win, text="Save changes", command=save_changes).pack(
            pady=10
        )

    def finish_task(self):
        task, orig_index = self.get_selected_active_task()
        if task is None:
            return

        # move current task to finished
        task = self.data["active"].pop(orig_index)
        task["finished_date"] = datetime.now().strftime("%d.%m.%Y")
        self.data["finished"].append(task)

        # if recurring -> create new task with updated date
        recurrence = task.get("recurrence")
        old_date = parse_date(task.get("date", ""))

        if recurrence and old_date:
            if recurrence == "daily":
                new_date = old_date + timedelta(days=1)
            elif recurrence == "weekly":
                new_date = old_date + timedelta(days=7)
            elif recurrence == "monthly":
                new_date = add_months(old_date, 1)
            else:
                new_date = None

            if new_date:
                new_task = {
                    "name": task["name"],
                    "date": new_date.strftime("%d.%m.%Y"),
                    "info": task["info"],
                    "priority": task.get("priority", "green"),
                    "created_date": datetime.now().strftime("%d.%m.%Y"),
                    "recurrence": recurrence,
                }
                self.data["active"].append(new_task)

        save_data(self.data)
        self.update_active_list()
        self.update_finished_list()
        self.clear_active_details()

        messagebox.showinfo("Done", "Task has been completed.")

    # --- Tab: Finished Tasks -------------------------------------------

    def build_finished_tab(self):
        frame = self.tab_finished

        filter_frame = ttk.LabelFrame(frame, text="Filter / Sorting")
        filter_frame.pack(fill="x", padx=10, pady=(5, 0))

        ttk.Label(filter_frame, text="Priority:").grid(
            row=0, column=0, padx=2, pady=2, sticky="w"
        )
        self.finished_filter_priority = ttk.Combobox(
            filter_frame,
            state="readonly",
            values=["All", "Red", "Yellow", "Green"],
            width=10,
        )
        self.finished_filter_priority.current(0)
        self.finished_filter_priority.grid(row=0, column=1, padx=2, pady=2)

        ttk.Label(filter_frame, text="Sorting:").grid(
            row=0, column=2, padx=2, pady=2, sticky="w"
        )
        self.finished_sort_order = ttk.Combobox(
            filter_frame,
            state="readonly",
            values=[
                "Date ascending (earliest first)",
                "Date descending (latest first)",
            ],
            width=28,
        )
        self.finished_sort_order.current(0)
        self.finished_sort_order.grid(row=0, column=3, padx=2, pady=2)

        ttk.Label(filter_frame, text="From date (finished):").grid(
            row=1, column=0, padx=2, pady=2, sticky="w"
        )
        self.finished_filter_date = ttk.Entry(filter_frame, width=12)
        self.finished_filter_date.grid(row=1, column=1, padx=2, pady=2, sticky="w")
        ttk.Label(filter_frame, text="(DD.MM.YYYY)").grid(
            row=1, column=2, padx=2, pady=2, sticky="w"
        )

        ttk.Label(filter_frame, text="Search (name):").grid(
            row=2, column=0, padx=2, pady=2, sticky="w"
        )
        self.finished_search_name = ttk.Entry(filter_frame, width=20)
        self.finished_search_name.grid(
            row=2, column=1, columnspan=2, padx=2, pady=2, sticky="w"
        )

        ttk.Button(filter_frame, text="Apply", command=self.update_finished_list).grid(
            row=2, column=3, padx=2, pady=2, sticky="e"
        )

        self.finished_list = tk.Listbox(frame, height=9, bg="white")
        self.finished_list.pack(pady=10, padx=10, fill="both", expand=True)
        self.finished_list.bind("<<ListboxSelect>>", self.show_finished_details)

        details_frame = ttk.Frame(frame)
        details_frame.pack(pady=5, padx=10, fill="both", expand=True)

        header_frame = ttk.Frame(details_frame)
        header_frame.pack(fill="x")

        self.finished_name = tk.Label(
            header_frame,
            text="",
            anchor="w",
            font=("Segoe UI", 10, "bold"),
            bg=BG_COLOR,
        )
        self.finished_name.pack(side="left", expand=True, fill="x")

        self.finished_enddate = tk.Label(
            header_frame,
            text="",
            anchor="e",
            bg=BG_COLOR,
        )
        self.finished_enddate.pack(side="right")

        self.finished_info = tk.Label(
            details_frame,
            text="",
            justify="left",
            anchor="nw",
            wraplength=330,
            bg=BG_COLOR,
        )
        self.finished_info.pack(fill="both", expand=True, pady=(5, 0))

        self.finished_extra = tk.Label(
            details_frame,
            text="",
            anchor="w",
            bg=BG_COLOR,
        )
        self.finished_extra.pack(fill="x", pady=(5, 0))

        ttk.Button(
            frame,
            text="↩ Set task active again",
            command=self.reactivate_finished_task,
        ).pack(pady=5)

        self.update_finished_list()

    def update_finished_list(self):
        self.finished_list.delete(0, tk.END)

        prio_filter_label = self.finished_filter_priority.get()
        prio_filter_value = PRIORITY_VALUE_BY_LABEL.get(prio_filter_label)

        date_filter_str = self.finished_filter_date.get().strip()
        filter_date = None
        if date_filter_str:
            filter_date = parse_date(date_filter_str)
            if not filter_date:
                messagebox.showwarning(
                    "Error",
                    "The filter date is invalid. Please use DD.MM.YYYY.",
                )
                filter_date = None

        search_term = self.finished_search_name.get().strip().lower()

        sort_choice = self.finished_sort_order.get()
        descending = sort_choice.startswith("Date descending")

        def passes_filters(t):
            prio = t.get("priority")
            if prio == "yellow":
                prio = "blue"
            if prio_filter_value and prio != prio_filter_value:
                return False
            if filter_date is not None:
                d = parse_date(t.get("finished_date", ""))
                if d is None or d < filter_date:
                    return False
            if search_term and search_term not in t.get("name", "").lower():
                return False
            return True

        def sort_key(t):
            d = parse_date(t.get("finished_date", "")) or datetime.min
            return d

        filtered = [t for t in self.data["finished"] if passes_filters(t)]
        self.sorted_finished_tasks = sorted(filtered, key=sort_key, reverse=descending)

        for t in self.sorted_finished_tasks:
            display_text = f"↩ ● {t['name']} – finished on {t.get('finished_date', '?')}"
            self.finished_list.insert(tk.END, display_text)

            prio = t.get("priority", "green")
            if prio == "yellow":
                prio = "blue"
            color = PRIORITY_COLOR.get(prio, "#000000")
            idx = self.finished_list.size() - 1
            self.finished_list.itemconfig(idx, fg=color)

        self.clear_finished_details()

    def clear_finished_details(self):
        self.finished_name.config(text="")
        self.finished_enddate.config(text="")
        self.finished_info.config(text="")
        self.finished_extra.config(text="")

    def show_finished_details(self, event):
        selection = self.finished_list.curselection()
        if not selection:
            return

        index = selection[0]
        if index >= len(self.sorted_finished_tasks):
            return

        task = self.sorted_finished_tasks[index]

        self.finished_name.config(text=task["name"])
        self.finished_enddate.config(text=f"Due: {task['date']}")
        self.finished_info.config(text=task["info"])

        created = task.get("created_date", "?")
        finished = task.get("finished_date", "?")
        rec_label = RECUR_VALUE_TO_LABEL.get(task.get("recurrence"), "None")
        self.finished_extra.config(
            text=f"Created: {created} | Finished: {finished} | Recurrence: {rec_label}"
        )

    def reactivate_finished_task(self):
        selection = self.finished_list.curselection()
        if not selection:
            messagebox.showwarning(
                "Notice", "Please select a finished task first."
            )
            return

        index = selection[0]
        if index >= len(self.sorted_finished_tasks):
            return

        task = self.sorted_finished_tasks[index]

        try:
            orig_index = self.data["finished"].index(task)
        except ValueError:
            messagebox.showerror("Error", "Task could not be found.")
            return

        task = self.data["finished"].pop(orig_index)
        self.data["active"].append(task)

        save_data(self.data)
        self.update_finished_list()
        self.update_active_list()
        messagebox.showinfo("Reactivated", "Task has been set active again.")


# --- Tray icon ---------------------------------------------------------

def run_tray(app: TaskApp):
    def on_open(icon, item):
        app.show_window()

    def on_quit(icon, item):
        app.quit()

    image = app.create_image()
    menu = pystray.Menu(
        pystray.MenuItem("Open", on_open),
        pystray.MenuItem("Quit", on_quit),
    )
    icon = pystray.Icon("NotizZettel", image, "NotizZettel", menu)
    app.tray_icon = icon
    icon.run()


def main():
    root = tk.Tk()
    app = TaskApp(root)

    tray_thread = threading.Thread(target=run_tray, args=(app,), daemon=True)
    tray_thread.start()

    root.mainloop()


if __name__ == "__main__":
    main()
