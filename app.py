from flask import Flask, render_template, request, jsonify, redirect, session
import time
from datetime import datetime, date
import json
import os

app = Flask(__name__)
app.secret_key = "system_monitor_secret"

# ----------------------------- 
# DATA PERSISTENCE FILE
# -----------------------------
DATA_FILE = "workstations_data.json"

# -----------------------------
# CLIENT USERS
# -----------------------------
users = {
    "arena": {
        "password": "1234",
        "title": "Arena System Monitor Dashboard"
    },
    "test1": {
        "password": "123",
        "title": "Lab System Monitor Dashboard"
    },
    "test2": {
        "password": "test123",
        "title": "Office System Monitor Dashboard"
    }
}

# -----------------------------
# LOAD DATA FROM FILE
# -----------------------------
def load_data():
    """Load workstations data from JSON file"""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading data: {e}")
            return {"arena": {}, "test1": {}, "test2": {}}
    return {"arena": {}, "test1": {}, "test2": {}}

def save_data(data):
    """Save workstations data to JSON file"""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Data saved to {DATA_FILE}")
    except Exception as e:
        print(f"Error saving data: {e}")

# Initialize workstations_data from file
workstations_data = load_data()

# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username in users and users[username]["password"] == password:
            session["user"] = username
            return redirect("/")

    return render_template("login.html")

# -----------------------------
# LOGOUT
# -----------------------------
@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login")

# -----------------------------
# RECEIVE DATA FROM POWERSHELL
# -----------------------------
@app.route("/update", methods=["POST"])
def update_workstation():
    try:
        data = request.get_json()
        
        if not data:
            print("No JSON data received")
            return jsonify({"error": "No data received"}), 400

        client = data.get("client")
        ws_name = data.get("system", "").strip()
        
        if not client or not ws_name:
            print(f"Missing client or system: client={client}, system={ws_name}")
            return jsonify({"error": "Missing client or system"}), 400

        print(f"\n=== Received data from {client}/{ws_name} ===")
        
        # Get data with defaults
        active_apps = data.get("active_apps", [])
        idle_apps = data.get("idle_apps", [])
        cpu = data.get("cpu", 0)
        ram = data.get("ram", 0)
        disk = data.get("disk", [])
        top_processes = data.get("topProcesses", [])
        
        # Get idle time from the data (if provided by PowerShell)
        idle_time_minutes = data.get("idle_time_minutes", 0)
        
        print(f"CPU: {cpu}%, RAM: {ram}%")
        print(f"Idle time: {idle_time_minutes} minutes")
        
        # Ensure disk is a list
        if not isinstance(disk, list):
            print(f"WARNING: Disk is not a list, it's {type(disk)}. Converting to empty list.")
            disk = []
        
        # Validate and clean disk data
        validated_disk = []
        for idx, disk_item in enumerate(disk):
            print(f"Processing disk {idx}: {disk_item}")
            if isinstance(disk_item, dict):
                clean_disk = {
                    "Drive": disk_item.get("Drive", "Unknown"),
                    "UsedPercent": float(disk_item.get("UsedPercent", 0)),
                    "TotalSize": float(disk_item.get("TotalSize", 0)),
                    "FreeSpace": float(disk_item.get("FreeSpace", 0)),
                    "UsedSpace": float(disk_item.get("UsedSpace", 0))
                }
                validated_disk.append(clean_disk)
                print(f"  -> Validated: {clean_disk}")
            else:
                print(f"  -> Skipping non-dict item: {disk_item}")
        
        # Validate top processes
        if not isinstance(top_processes, list):
            top_processes = []
        
        validated_processes = []
        for proc in top_processes:
            if isinstance(proc, dict):
                validated_processes.append({
                    "Name": proc.get("Name", "Unknown"),
                    "CPU": float(proc.get("CPU", 0))
                })

        # Create or update client data
        if client not in workstations_data:
            workstations_data[client] = {}
        
        if ws_name not in workstations_data[client]:
            workstations_data[client][ws_name] = {}
        
        current_data = workstations_data[client][ws_name]
        current_date = date.today().isoformat()
        
        # Initialize or get daily stats
        if "daily_stats" not in workstations_data[client][ws_name]:
            workstations_data[client][ws_name]["daily_stats"] = {}
        
        daily_stats = workstations_data[client][ws_name]["daily_stats"]
        
        # Get or create today's stats
        if current_date not in daily_stats:
            daily_stats[current_date] = {
                "active_time": 0,  # Total active time in minutes today
                "idle_time": 0,    # Total idle time in minutes today
                "last_update": time.time()
            }
        
        today_stats = daily_stats[current_date]
        
        # Check if we need to reset for a new day
        last_update_time = today_stats.get("last_update", 0)
        current_time = time.time()
        
        # Calculate time since last update (in minutes)
        time_diff_minutes = (current_time - last_update_time) / 60 if last_update_time > 0 else 0
        
        # Update daily stats based on current idle time
        if time_diff_minutes > 0 and time_diff_minutes < 5:  # Only count reasonable time intervals
            # If user is active (idle_time_minutes < 1), add to active time
            if idle_time_minutes < 1:
                today_stats["active_time"] += time_diff_minutes
                print(f"Adding {time_diff_minutes:.2f} minutes to active time")
            else:
                # User is idle, add to idle time
                today_stats["idle_time"] += time_diff_minutes
                print(f"Adding {time_diff_minutes:.2f} minutes to idle time")
        
        # Update last update time
        today_stats["last_update"] = current_time
        
        # Clean up old daily stats (keep only last 7 days)
        days_to_keep = 7
        dates_to_remove = []
        for date_key in daily_stats.keys():
            try:
                stat_date = datetime.fromisoformat(date_key).date()
                days_old = (date.today() - stat_date).days
                if days_old > days_to_keep:
                    dates_to_remove.append(date_key)
            except:
                pass
        
        for old_date in dates_to_remove:
            del daily_stats[old_date]
            print(f"Removed old stats for {old_date}")
        
        # Update data
        workstations_data[client][ws_name].update({
            "active_apps": active_apps if active_apps else current_data.get("active_apps", []),
            "idle_apps": idle_apps if idle_apps else current_data.get("idle_apps", []),
            "cpu": float(cpu) if cpu else current_data.get("cpu", 0),
            "ram": float(ram) if ram else current_data.get("ram", 0),
            "disk": validated_disk if validated_disk else current_data.get("disk", []),
            "topProcesses": validated_processes if validated_processes else current_data.get("topProcesses", []),
            "last_seen": current_time,
            "current_idle_minutes": idle_time_minutes,
            "daily_stats": daily_stats
        })
        
        print(f"Updated {ws_name}")
        print(f"Today's stats - Active: {today_stats['active_time']:.1f}m, Idle: {today_stats['idle_time']:.1f}m")
        
        # Save to file
        save_data(workstations_data)
        
        return jsonify({"message": "Data updated", "disks_received": len(validated_disk)}), 200
        
    except Exception as e:
        print(f"ERROR in update_workstation: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

# -----------------------------
# DASHBOARD (HOME WITH PAGINATION)
# -----------------------------
@app.route("/")
def dashboard():
    if "user" not in session:
        return redirect("/login")

    username = session["user"]
    title = users[username]["title"]

    systems = workstations_data.get(username, {})

    all_data = []
    total_systems = len(systems)
    online_count = 0
    offline_count = 0

    current_time = time.time()
    today_date = date.today().isoformat()

    for ws_name, info in systems.items():
        last_seen = info.get("last_seen", 0)

        if last_seen == 0:
            status = "Offline"
            color = "red"
            offline_count += 1
        elif current_time - last_seen > 120:
            status = "Offline"
            color = "red"
            offline_count += 1
        else:
            status = "Online"
            color = "green"
            online_count += 1

        # Get today's stats
        daily_stats = info.get("daily_stats", {})
        today_stats = daily_stats.get(today_date, {"active_time": 0, "idle_time": 0})
        
        active_time_today = today_stats.get("active_time", 0)
        idle_time_today = today_stats.get("idle_time", 0)

        all_data.append({
            "name": ws_name,
            "active_apps": info.get("active_apps", []),
            "status": status,
            "color": color,
            "active_time_today": active_time_today,
            "idle_time_today": idle_time_today
        })

    # Pagination
    page = int(request.args.get("page", 1))
    per_page = 10

    start = (page - 1) * per_page
    end = start + per_page

    paginated_data = all_data[start:end]
    has_next = end < len(all_data)

    return render_template(
        "index.j2",
        workstations=paginated_data,
        title=title,
        page=page,
        has_next=has_next,
        total_systems=total_systems,
        online_count=online_count,
        offline_count=offline_count
    )

# -----------------------------
# WORKSTATIONS PAGE
# -----------------------------
@app.route("/workstations")
def workstations():
    if "user" not in session:
        return redirect("/login")

    username = session["user"]
    title = users[username]["title"]

    systems = workstations_data.get(username, {})

    display_data = []
    current_time = time.time()

    for ws_name, info in systems.items():
        last_seen = info.get("last_seen", 0)

        if last_seen == 0 or current_time - last_seen > 120:
            status = "Offline"
            color = "red"
        else:
            status = "Online"
            color = "green"

        # Get disk data
        disk_data = info.get("disk", [])
        if not isinstance(disk_data, list):
            disk_data = []
        
        # Validate disk entries
        validated_disks = []
        for disk in disk_data:
            if isinstance(disk, dict):
                validated_disks.append({
                    "Drive": disk.get("Drive", "Unknown"),
                    "UsedPercent": float(disk.get("UsedPercent", 0)),
                    "TotalSize": float(disk.get("TotalSize", 0)),
                    "FreeSpace": float(disk.get("FreeSpace", 0)),
                    "UsedSpace": float(disk.get("UsedSpace", 0))
                })
        
        # Get top processes
        top_processes = info.get("topProcesses", [])
        if not isinstance(top_processes, list):
            top_processes = []
        
        validated_processes = []
        for proc in top_processes:
            if isinstance(proc, dict):
                validated_processes.append({
                    "Name": proc.get("Name", "Unknown"),
                    "CPU": float(proc.get("CPU", 0))
                })

        display_data.append({
            "name": ws_name,
            "ram": float(info.get("ram", 0)),
            "cpu": float(info.get("cpu", 0)),
            "disk": validated_disks,
            "topProcesses": validated_processes,
            "status": status,
            "color": color
        })
        
        print(f"Workstation {ws_name}: {len(validated_disks)} disks found")

    return render_template(
        "workstations.j2",
        workstations=display_data,
        title=title
    )

# -----------------------------
# DEBUG ROUTE TO VIEW RAW DATA
# -----------------------------
@app.route("/debug")
def debug():
    if "user" not in session:
        return redirect("/login")
    return jsonify(workstations_data)

# -----------------------------
# RUN SERVER
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
