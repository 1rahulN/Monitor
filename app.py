from flask import Flask, render_template, request, jsonify, redirect, session
import time
from datetime import datetime, date
import json
import os
import subprocess
import platform
import socket
import re
import urllib.request
import sqlite3
from contextlib import contextmanager

app = Flask(__name__)
app.secret_key = "system_monitor_secret"

# -----------------------------
# DATABASE SETUP
# -----------------------------
DATABASE_FILE = "workstations.db"

def init_database():
    """Initialize the SQLite database with required tables"""
    with get_db() as conn:
        cursor = conn.cursor()
        
        # Create workstations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS workstations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client TEXT NOT NULL,
                ws_name TEXT NOT NULL,
                active_apps TEXT,
                idle_apps TEXT,
                cpu REAL,
                ram REAL,
                disk TEXT,
                top_processes TEXT,
                last_seen REAL,
                current_idle_minutes REAL,
                internet_status TEXT,
                internet_latency REAL,
                internet_speed TEXT,
                internet_connection_name TEXT,
                UNIQUE(client, ws_name)
            )
        ''')
        
        # Create daily_stats table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS daily_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client TEXT NOT NULL,
                ws_name TEXT NOT NULL,
                stat_date TEXT NOT NULL,
                active_time REAL,
                idle_time REAL,
                last_update REAL,
                UNIQUE(client, ws_name, stat_date)
            )
        ''')
        
        conn.commit()
        print("Database initialized successfully")

@contextmanager
def get_db():
    """Get a database connection with context manager"""
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row  # This allows accessing columns by name
    try:
        yield conn
    finally:
        conn.close()

# Initialize database on startup
init_database()

# -----------------------------
# DATA LOAD/SAVE FUNCTIONS (SQLite versions)
# -----------------------------
def load_data():
    """Load all workstations data from SQLite database"""
    data = {"arena": {}, "test1": {}, "test2": {}}
    
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Load workstations
            cursor.execute('''
                SELECT client, ws_name, active_apps, idle_apps, cpu, ram, disk, 
                       top_processes, last_seen, current_idle_minutes, 
                       internet_status, internet_latency, internet_speed, 
                       internet_connection_name
                FROM workstations
            ''')
            
            for row in cursor.fetchall():
                client = row['client']
                ws_name = row['ws_name']
                
                if client not in data:
                    data[client] = {}
                
                # Parse JSON fields
                active_apps = json.loads(row['active_apps']) if row['active_apps'] else []
                idle_apps = json.loads(row['idle_apps']) if row['idle_apps'] else []
                disk = json.loads(row['disk']) if row['disk'] else []
                top_processes = json.loads(row['top_processes']) if row['top_processes'] else []
                
                data[client][ws_name] = {
                    "active_apps": active_apps,
                    "idle_apps": idle_apps,
                    "cpu": row['cpu'] or 0,
                    "ram": row['ram'] or 0,
                    "disk": disk,
                    "topProcesses": top_processes,
                    "last_seen": row['last_seen'] or 0,
                    "current_idle_minutes": row['current_idle_minutes'] or 0,
                    "internetStatus": row['internet_status'] or "unknown",
                    "internetLatency": row['internet_latency'],
                    "internetSpeed": row['internet_speed'],
                    "internetConnectionName": row['internet_connection_name'] or "Unknown",
                    "daily_stats": {}
                }
            
            # Load daily stats
            cursor.execute('''
                SELECT client, ws_name, stat_date, active_time, idle_time, last_update
                FROM daily_stats
                ORDER BY stat_date
            ''')
            
            for row in cursor.fetchall():
                client = row['client']
                ws_name = row['ws_name']
                stat_date = row['stat_date']
                
                if client in data and ws_name in data[client]:
                    data[client][ws_name]["daily_stats"][stat_date] = {
                        "active_time": row['active_time'] or 0,
                        "idle_time": row['idle_time'] or 0,
                        "last_update": row['last_update'] or 0
                    }
            
            print(f"Loaded data for clients: {list(data.keys())}")
            return data
            
    except Exception as e:
        print(f"Error loading data from database: {e}")
        import traceback
        traceback.print_exc()
        return {"arena": {}, "test1": {}, "test2": {}}

def save_data(data):
    """Save all workstations data to SQLite database"""
    try:
        with get_db() as conn:
            cursor = conn.cursor()
            
            # Clear existing data
            cursor.execute('DELETE FROM workstations')
            cursor.execute('DELETE FROM daily_stats')
            
            # Insert workstations
            for client, systems in data.items():
                for ws_name, info in systems.items():
                    # Extract daily_stats to save separately
                    daily_stats = info.pop("daily_stats", {})
                    
                    # Prepare data for insertion
                    cursor.execute('''
                        INSERT OR REPLACE INTO workstations 
                        (client, ws_name, active_apps, idle_apps, cpu, ram, disk, 
                         top_processes, last_seen, current_idle_minutes, 
                         internet_status, internet_latency, internet_speed, 
                         internet_connection_name)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (
                        client,
                        ws_name,
                        json.dumps(info.get("active_apps", [])),
                        json.dumps(info.get("idle_apps", [])),
                        info.get("cpu", 0),
                        info.get("ram", 0),
                        json.dumps(info.get("disk", [])),
                        json.dumps(info.get("topProcesses", [])),
                        info.get("last_seen", 0),
                        info.get("current_idle_minutes", 0),
                        info.get("internetStatus", "unknown"),
                        info.get("internetLatency"),
                        info.get("internetSpeed"),
                        info.get("internetConnectionName", "Unknown")
                    ))
                    
                    # Insert daily stats
                    for stat_date, stats in daily_stats.items():
                        cursor.execute('''
                            INSERT OR REPLACE INTO daily_stats 
                            (client, ws_name, stat_date, active_time, idle_time, last_update)
                            VALUES (?, ?, ?, ?, ?, ?)
                        ''', (
                            client,
                            ws_name,
                            stat_date,
                            stats.get("active_time", 0),
                            stats.get("idle_time", 0),
                            stats.get("last_update", 0)
                        ))
                    
                    # Restore daily_stats to info object
                    info["daily_stats"] = daily_stats
            
            conn.commit()
            print(f"Data saved to database: {len(data)} clients")
            
    except Exception as e:
        print(f"Error saving data to database: {e}")
        import traceback
        traceback.print_exc()

# -----------------------------
# BACKWARD COMPATIBILITY: Load data from JSON if it exists
# -----------------------------
def migrate_from_json():
    """Migrate data from JSON file to SQLite if JSON file exists"""
    json_file = "workstations_data.json"
    if os.path.exists(json_file):
        print("Found existing JSON data file. Migrating to SQLite...")
        try:
            with open(json_file, 'r') as f:
                json_data = json.load(f)
            
            # Save JSON data to SQLite
            save_data(json_data)
            
            # Optional: Rename the JSON file as backup
            backup_file = f"{json_file}.backup"
            os.rename(json_file, backup_file)
            print(f"Migration complete. JSON file backed up to {backup_file}")
            
            return json_data
        except Exception as e:
            print(f"Error during migration: {e}")
            return {"arena": {}, "test1": {}, "test2": {}}
    return {"arena": {}, "test1": {}, "test2": {}}

# Initialize workstations_data from database or migrate from JSON
workstations_data = load_data()
if not any(workstations_data.values()):  # If database is empty
    print("Database empty, checking for JSON migration...")
    workstations_data = migrate_from_json()
else:
    print("Loaded data from existing database")

# -----------------------------
# GET INTERNET CONNECTION NAME
# -----------------------------
def get_internet_connection_name():
    """
    Get the name of the active internet connection
    """
    try:
        if platform.system().lower() == "windows":
            # Method 1: Get active network adapter name using PowerShell
            try:
                result = subprocess.run(
                    ["powershell", "-Command", 
                     "Get-NetConnectionProfile | Select-Object -ExpandProperty Name"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    return result.stdout.strip()
            except:
                pass
            
            # Method 2: Get active adapter from ipconfig
            try:
                result = subprocess.run(
                    ["ipconfig"], capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0:
                    lines = result.stdout.split('\n')
                    current_adapter = None
                    for i, line in enumerate(lines):
                        if 'adapter' in line.lower() and ':' in line:
                            current_adapter = line.split(':')[0].strip()
                        if 'Default Gateway' in line and ':' in line and current_adapter:
                            if '::' not in line:
                                return current_adapter
            except:
                pass
            
            return "Network Connection"
            
        else:  # Linux/Mac
            try:
                result = subprocess.run(
                    ["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"],
                    capture_output=True, text=True, timeout=5
                )
                if result.returncode == 0 and result.stdout.strip():
                    lines = result.stdout.strip().split('\n')
                    if lines:
                        return lines[0].split(':')[0]
            except:
                pass
            
            return "Network Connection"
            
    except Exception as e:
        print(f"Error getting connection name: {e}")
    
    return "Network Connection"

# -----------------------------
# INTERNET STATUS CHECK FUNCTION
# -----------------------------
def check_internet_status():
    """
    Check internet connectivity from the server side.
    Returns a dictionary with status, latency, speed info, and connection name.
    """
    try:
        connection_name = get_internet_connection_name()
        
        start_time = time.time()
        
        if platform.system().lower() == "windows":
            ping_cmd = ["ping", "-n", "1", "8.8.8.8"]
        else:
            ping_cmd = ["ping", "-c", "1", "8.8.8.8"]
        
        result = subprocess.run(ping_cmd, capture_output=True, text=True, timeout=5)
        latency = (time.time() - start_time) * 1000
        
        if result.returncode == 0:
            if platform.system().lower() == "windows":
                match = re.search(r'time[=<](\d+)ms', result.stdout)
            else:
                match = re.search(r'time=(\d+\.?\d*) ms', result.stdout)
            
            if match:
                latency = float(match.group(1))
            
            try:
                urllib.request.urlopen('http://www.google.com', timeout=3)
                status = "online"
                speed = "Good"
            except:
                status = "limited"
                speed = "Limited"
            
            return {
                "status": status,
                "latency": round(latency, 2),
                "speed": speed,
                "connection_name": connection_name,
                "last_check": time.time()
            }
        else:
            return {
                "status": "offline",
                "latency": None,
                "speed": "No connection",
                "connection_name": "No Connection",
                "last_check": time.time()
            }
    except subprocess.TimeoutExpired:
        return {
            "status": "offline",
            "latency": None,
            "speed": "Timeout",
            "connection_name": "No Connection",
            "last_check": time.time()
        }
    except Exception as e:
        print(f"Error checking internet: {e}")
        return {
            "status": "unknown",
            "latency": None,
            "speed": "Unknown",
            "connection_name": "Unknown",
            "last_check": time.time()
        }

# -----------------------------
# LOGIN
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username in users and users[username]["password"] == password: # type: ignore
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
        
        active_apps = data.get("active_apps", [])
        idle_apps = data.get("idle_apps", [])
        cpu = data.get("cpu", 0)
        ram = data.get("ram", 0)
        disk = data.get("disk", [])
        top_processes = data.get("topProcesses", [])
        
        internet_status = data.get("internetStatus", {})
        if not internet_status:
            internet_status = check_internet_status()
        elif isinstance(internet_status, str):
            internet_status = {
                "status": internet_status,
                "latency": data.get("internetLatency"),
                "speed": data.get("internetSpeed", "Unknown"),
                "connection_name": data.get("internetConnectionName", "Unknown")
            }
        
        idle_time_minutes = data.get("idle_time_minutes", 0)
        
        print(f"CPU: {cpu}%, RAM: {ram}%")
        print(f"Idle time: {idle_time_minutes} minutes")
        print(f"Internet Status: {internet_status}")
        
        if not isinstance(disk, list):
            print(f"WARNING: Disk is not a list, it's {type(disk)}. Converting to empty list.")
            disk = []
        
        validated_disk = []
        for idx, disk_item in enumerate(disk):
            print(f"Processing disk {idx}: {disk_item}")
            if isinstance(disk_item, dict):
                clean_disk = {
                    "Drive": disk_item.get("Drive", "Unknown"),
                    "UsedPercent": float(disk_item.get("UsedPercent", 0)),
                    "TotalGB": float(disk_item.get("TotalSize", 0)) / (1024**3) if disk_item.get("TotalSize", 0) > 0 else float(disk_item.get("TotalGB", 0)),
                    "FreeGB": float(disk_item.get("FreeSpace", 0)) / (1024**3) if disk_item.get("FreeSpace", 0) > 0 else float(disk_item.get("FreeGB", 0)),
                    "TotalSize": float(disk_item.get("TotalSize", 0)),
                    "FreeSpace": float(disk_item.get("FreeSpace", 0)),
                    "UsedSpace": float(disk_item.get("UsedSpace", 0))
                }
                validated_disk.append(clean_disk)
                print(f"  -> Validated: {clean_disk}")
            else:
                print(f"  -> Skipping non-dict item: {disk_item}")
        
        if not isinstance(top_processes, list):
            top_processes = []
        
        validated_processes = []
        for proc in top_processes:
            if isinstance(proc, dict):
                validated_processes.append({
                    "Name": proc.get("Name", "Unknown"),
                    "CPU": float(proc.get("CPU", 0))
                })

        if client not in workstations_data:
            workstations_data[client] = {}
        
        if ws_name not in workstations_data[client]:
            workstations_data[client][ws_name] = {}
        
        current_data = workstations_data[client][ws_name]
        current_date = date.today().isoformat()
        
        if "daily_stats" not in workstations_data[client][ws_name]:
            workstations_data[client][ws_name]["daily_stats"] = {}
        
        daily_stats = workstations_data[client][ws_name]["daily_stats"]
        
        if current_date not in daily_stats:
            daily_stats[current_date] = {
                "active_time": 0,
                "idle_time": 0,
                "last_update": time.time()
            }
        
        today_stats = daily_stats[current_date]
        
        last_update_time = today_stats.get("last_update", 0)
        current_time = time.time()
        
        time_diff_minutes = (current_time - last_update_time) / 60 if last_update_time > 0 else 0
        
        if time_diff_minutes > 0 and time_diff_minutes < 5:
            if idle_time_minutes < 1:
                today_stats["active_time"] += time_diff_minutes
                print(f"Adding {time_diff_minutes:.2f} minutes to active time")
            else:
                today_stats["idle_time"] += time_diff_minutes
                print(f"Adding {time_diff_minutes:.2f} minutes to idle time")
        
        today_stats["last_update"] = current_time
        
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
        
        workstations_data[client][ws_name].update({
            "active_apps": active_apps if active_apps else current_data.get("active_apps", []),
            "idle_apps": idle_apps if idle_apps else current_data.get("idle_apps", []),
            "cpu": float(cpu) if cpu else current_data.get("cpu", 0),
            "ram": float(ram) if ram else current_data.get("ram", 0),
            "disk": validated_disk if validated_disk else current_data.get("disk", []),
            "topProcesses": validated_processes if validated_processes else current_data.get("topProcesses", []),
            "last_seen": current_time,
            "current_idle_minutes": idle_time_minutes,
            "daily_stats": daily_stats,
            "internetStatus": internet_status.get("status", "unknown"),
            "internetLatency": internet_status.get("latency"),
            "internetSpeed": internet_status.get("speed"),
            "internetConnectionName": internet_status.get("connection_name", "Unknown")
        })
        
        print(f"Updated {ws_name}")
        print(f"Today's stats - Active: {today_stats['active_time']:.1f}m, Idle: {today_stats['idle_time']:.1f}m")
        
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
    title = users[username]["title"] # type: ignore

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
            offline_count += 1
        elif current_time - last_seen > 120:
            status = "Offline"
            offline_count += 1
        else:
            status = "Online"
            online_count += 1

        daily_stats = info.get("daily_stats", {})
        today_stats = daily_stats.get(today_date, {"active_time": 0, "idle_time": 0})
        
        active_time_today = today_stats.get("active_time", 0)
        idle_time_today = today_stats.get("idle_time", 0)

        all_data.append({
            "name": ws_name,
            "active_apps": info.get("active_apps", []),
            "status": status,
            "color": "#28a745" if status == "Online" else "#dc3545",
            "active_time_today": active_time_today,
            "idle_time_today": idle_time_today
        })

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
    title = users[username]["title"] # type: ignore

    systems = workstations_data.get(username, {})

    display_data = []
    current_time = time.time()

    for ws_name, info in systems.items():
        last_seen = info.get("last_seen", 0)

        if last_seen == 0 or current_time - last_seen > 120:
            status = "Offline"
        else:
            status = "Online"

        disk_data = info.get("disk", [])
        if not isinstance(disk_data, list):
            disk_data = []
        
        validated_disks = []
        for disk in disk_data:
            if isinstance(disk, dict):
                validated_disks.append({
                    "Drive": disk.get("Drive", "Unknown"),
                    "UsedPercent": float(disk.get("UsedPercent", 0)),
                    "TotalGB": disk.get("TotalGB", 0),
                    "FreeGB": disk.get("FreeGB", 0)
                })
        
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
            "internetStatus": info.get("internetStatus", "unknown"),
            "internetLatency": info.get("internetLatency"),
            "internetSpeed": info.get("internetSpeed"),
            "internetConnectionName": info.get("internetConnectionName", "")
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
# MANUAL INTERNET CHECK ROUTE
# -----------------------------
@app.route("/check_internet")
def check_internet():
    """Manual endpoint to check internet connectivity"""
    if "user" not in session:
        return redirect("/login")
    return jsonify(check_internet_status())

# -----------------------------
# RUN SERVER
# -----------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
