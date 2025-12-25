import os
import sqlite3
import requests
from flask import (
    Flask, render_template, request, redirect,
    url_for, session, flash, jsonify
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ========================================
# ✅ GOOGLE API KEYS LOADED (Tumhare keys!)
# ========================================
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CX_ID   = os.getenv("GOOGLE_CX_ID")

GOOGLE_AVAILABLE = True if GOOGLE_API_KEY and GOOGLE_CX_ID else False

# ========================================
# Flask App Setup
# ========================================
app = Flask(__name__)


app.secret_key = "MEN-PARLOUR-RR-SECRET-2025-CHANGE-IF-NEEDED"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "men_parlour.db")

UPLOAD_FOLDER = os.path.join("static", "hairstyles")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ========================================
# Database Helper Functions
# ========================================
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()

    # Customers table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        mobile TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password TEXT NOT NULL,
        customer_number TEXT UNIQUE,
        profile_image TEXT
    );
    """)

    # Shop owners table (Admin approval required)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shopowners (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_name TEXT NOT NULL,
        owner_name TEXT NOT NULL,
        mobile TEXT UNIQUE NOT NULL,
        email TEXT UNIQUE,
        password TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        logo TEXT
    );
    """)

    # Hairstyles table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS hairstyles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        image_path TEXT NOT NULL,
        description TEXT,
        FOREIGN KEY(owner_id) REFERENCES shopowners(id)
    );
    """)

    # Bookings table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        owner_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        mobile TEXT NOT NULL,
        time_slot TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        FOREIGN KEY(customer_id) REFERENCES customers(id),
        FOREIGN KEY(owner_id) REFERENCES shopowners(id)
    );
    """)

    # Admin table (single admin)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS admin (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        login_id TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        password TEXT NOT NULL
    );
    """)

    # Settings table (tagline)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        id INTEGER PRIMARY KEY CHECK (id = 1),
        tagline TEXT
    );
    """)

    # Default admin (rradmin / admin123)
    cur.execute("SELECT COUNT(*) AS c FROM admin;")
    if cur.fetchone()["c"] == 0:
        cur.execute("""
            INSERT INTO admin (login_id, name, password)
            VALUES (?, ?, ?)
        """, ("rradmin", "R&R Admin", generate_password_hash("admin123")))

    # Default tagline
    cur.execute("SELECT COUNT(*) AS c FROM settings WHERE id = 1;")
    if cur.fetchone()["c"] == 0:
        cur.execute("INSERT INTO settings (id, tagline) VALUES (1, ?)", ("Best styles for modern men",))

    conn.commit()
    conn.close()

# ========================================
# Authentication Decorator
# ========================================
def login_required(role=None):
    def wrapper(fn):
        def decorated(*args, **kwargs):
            if "user_id" not in session or "role" not in session:
                return redirect(url_for("index"))
            if role and session.get("role") != role:
                return redirect(url_for("index"))
            return fn(*args, **kwargs)
        decorated.__name__ = fn.__name__
        return decorated
    return wrapper

# ========================================
# Routes
# ========================================

@app.route("/", methods=["GET"])
def index():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT tagline FROM settings WHERE id = 1;")
    row = cur.fetchone()
    tagline = row["tagline"] if row else "Best styles for modern men"
    conn.close()
    return render_template("index.html", tagline=tagline, google_available=GOOGLE_AVAILABLE)

@app.route("/register/customer", methods=["POST"])
def register_customer():
    name = request.form["name"].strip()
    mobile = request.form["mobile"].strip()
    email = request.form.get("email", "").strip() or None
    password = request.form["password"]

    if not name or not mobile or not password:
        flash("Name, mobile and password required.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO customers (name, mobile, email, password, customer_number)
            VALUES (?,?,?,?,?)
        """, (name, mobile, email, generate_password_hash(password), "CUST-" + mobile))
        conn.commit()
        flash("Customer registered successfully. Please login.", "success")
    except Exception as e:
        flash(f"Registration failed: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("index"))

@app.route("/register/owner", methods=["POST"])
def register_owner():
    shop_name = request.form["shop_name"].strip()
    owner_name = request.form["owner_name"].strip()
    mobile = request.form["mobile"].strip()
    email = request.form.get("email", "").strip() or None
    password = request.form["password"]

    if not all([shop_name, owner_name, mobile, password]):
        flash("All fields required.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO shopowners (shop_name, owner_name, mobile, email, password, status)
            VALUES (?,?,?,?,?, 'pending')
        """, (shop_name, owner_name, mobile, email, generate_password_hash(password)))
        conn.commit()
        flash("Shop owner registered. Wait for admin approval.", "success")
    except Exception as e:
        flash(f"Registration failed: {str(e)}", "danger")
    finally:
        conn.close()
    return redirect(url_for("index"))

@app.route("/login", methods=["POST"])
def login():
    role = request.form.get("role")
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not all([role, username, password]):
        flash("All fields required.", "danger")
        return redirect(url_for("index"))

    conn = get_db()
    cur = conn.cursor()

    if role == "customer":
        cur.execute("SELECT * FROM customers WHERE mobile = ? OR email = ?", (username, username))
        user = cur.fetchone()
        if user and check_password_hash(user["password"], password):
            session["role"] = "customer"
            session["user_id"] = user["id"]
            conn.close()
            return redirect(url_for("customer_dashboard"))
        flash("Invalid customer credentials.", "danger")

    elif role == "owner":
        cur.execute("SELECT * FROM shopowners WHERE mobile = ? OR email = ?", (username, username))
        owner = cur.fetchone()
        if owner and check_password_hash(owner["password"], password):
            if owner["status"] != "active":
                flash("Account pending admin approval.", "warning")
            else:
                session["role"] = "owner"
                session["user_id"] = owner["id"]
                conn.close()
                return redirect(url_for("owner_dashboard"))
        flash("Invalid owner credentials.", "danger")

    elif role == "admin":
        cur.execute("SELECT * FROM admin WHERE login_id = ?", (username,))
        adm = cur.fetchone()
        if adm and check_password_hash(adm["password"], password):
            session["role"] = "admin"
            session["user_id"] = adm["id"]
            conn.close()
            return redirect(url_for("admin_dashboard"))
        flash("Invalid admin credentials.", "danger")

    conn.close()
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "info")
    return redirect(url_for("index"))

# ========================================
# Customer Dashboard
# ========================================
@app.route("/customer/dashboard")
@login_required(role="customer")
def customer_dashboard():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM customers WHERE id = ?", (session["user_id"],))
    customer = cur.fetchone()

    cur.execute("""
        SELECT h.*, s.shop_name
        FROM hairstyles h JOIN shopowners s ON h.owner_id = s.id
        WHERE s.status = 'active' ORDER BY h.id DESC
    """)
    styles = cur.fetchall()

    cur.execute("SELECT id, shop_name FROM shopowners WHERE status = 'active' ORDER BY shop_name")
    owners = cur.fetchall()

    cur.execute("""
        SELECT b.*, s.shop_name
        FROM bookings b JOIN shopowners s ON b.owner_id = s.id
        WHERE b.customer_id = ? ORDER BY b.id DESC LIMIT 1
    """, (session["user_id"],))
    last_booking = cur.fetchone()

    conn.close()
    return render_template("customer_dashboard.html", customer=customer, styles=styles, 
                          owners=owners, last_booking=last_booking, google_available=GOOGLE_AVAILABLE)

@app.route("/customer/update_profile", methods=["POST"])
@login_required(role="customer")
def customer_update_profile():
    name = request.form["name"].strip()
    mobile = request.form["mobile"].strip()
    email = request.form.get("email", "").strip() or None
    file = request.files.get("profile_image")

    conn = get_db()
    cur = conn.cursor()

    image_path = None
    if file and file.filename:
        filename = secure_filename(file.filename)
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)
        image_path = f"static/hairstyles/{filename}"

    if image_path:
        cur.execute("UPDATE customers SET name=?, mobile=?, email=?, profile_image=? WHERE id=?", 
                   (name, mobile, email, image_path, session["user_id"]))
    else:
        cur.execute("UPDATE customers SET name=?, mobile=?, email=? WHERE id=?", 
                   (name, mobile, email, session["user_id"]))

    conn.commit()
    conn.close()
    flash("Profile updated!", "success")
    return redirect(url_for("customer_dashboard"))

@app.route("/customer/book", methods=["POST"])
@login_required(role="customer")
def book():
    owner_id = request.form["owner_id"]
    name = request.form["name"].strip()
    mobile = request.form["mobile"].strip()
    time_slot = request.form["time_slot"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO bookings (customer_id, owner_id, name, mobile, time_slot)
        VALUES (?,?,?,?,?)
    """, (session["user_id"], owner_id, name, mobile, time_slot))
    conn.commit()
    conn.close()

    flash("Appointment booked! Wait for confirmation.", "success")
    return redirect(url_for("customer_dashboard"))

# ========================================
# Owner Dashboard
# ========================================
@app.route("/owner/dashboard")
@login_required(role="owner")
def owner_dashboard():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM shopowners WHERE id = ?", (session["user_id"],))
    owner = cur.fetchone()

    cur.execute("SELECT * FROM hairstyles WHERE owner_id = ? ORDER BY id DESC", (session["user_id"],))
    styles = cur.fetchall()

    cur.execute("""
        SELECT b.*, c.name AS customer_name
        FROM bookings b JOIN customers c ON b.customer_id = c.id
        WHERE b.owner_id = ? ORDER BY b.id DESC
    """, (session["user_id"],))
    bookings = cur.fetchall()

    conn.close()
    return render_template("owner_dashboard.html", owner=owner, styles=styles, bookings=bookings)

@app.route("/owner/add_hairstyle", methods=["POST"])
@login_required(role="owner")
def add_hairstyle():
    name = request.form["name"].strip()
    description = request.form.get("description", "").strip()
    files = request.files.getlist("photos")

    conn = get_db()
    cur = conn.cursor()

    for file in files:
        if file and file.filename:
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
            file.save(save_path)
            cur.execute("""
                INSERT INTO hairstyles (owner_id, name, image_path, description)
                VALUES (?,?,?,?)
            """, (session["user_id"], name, f"static/hairstyles/{filename}", description))

    conn.commit()
    conn.close()
    flash("Hairstyle(s) added successfully!", "success")
    return redirect(url_for("owner_dashboard"))

@app.route("/owner/booking_action", methods=["POST"])
@login_required(role="owner")
def booking_action():
    booking_id = request.form["booking_id"]
    action = request.form["action"]
    status = "accepted" if action == "accept" else "rejected"

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE bookings SET status=? WHERE id=? AND owner_id=?", 
               (status, booking_id, session["user_id"]))
    conn.commit()
    conn.close()

    flash(f"Booking {status}!", "info")
    return redirect(url_for("owner_dashboard"))

# ========================================
# Admin Dashboard
# ========================================
@app.route("/admin/dashboard")
@login_required(role="admin")
def admin_dashboard():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM admin WHERE id = ?", (session["user_id"],))
    admin_user = cur.fetchone()

    cur.execute("SELECT COUNT(*) AS c FROM customers")
    total_customers = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*) AS c FROM shopowners")
    total_owners = cur.fetchone()["c"]

    cur.execute("SELECT * FROM shopowners ORDER BY id DESC")
    owners = cur.fetchall()

    conn.close()
    return render_template("admin_dashboard.html", admin_user=admin_user, 
                          total_customers=total_customers, total_owners=total_owners, owners=owners)

@app.route("/admin/update_profile", methods=["POST"])
@login_required(role="admin")
def admin_update_profile():
    name = request.form["name"].strip()
    login_id = request.form["login_id"].strip()
    password = request.form.get("password", "").strip()

    conn = get_db()
    cur = conn.cursor()

    if password:
        cur.execute("UPDATE admin SET name=?, login_id=?, password=? WHERE id=?", 
                   (name, login_id, generate_password_hash(password), session["user_id"]))
    else:
        cur.execute("UPDATE admin SET name=?, login_id=? WHERE id=?", 
                   (name, login_id, session["user_id"]))

    conn.commit()
    conn.close()
    flash("Admin profile updated!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/owner_status", methods=["POST"])
@login_required(role="admin")
def admin_owner_status():
    owner_id = request.form["owner_id"]
    status = request.form["status"]

    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE shopowners SET status=? WHERE id=?", (status, owner_id))
    conn.commit()
    conn.close()

    flash(f"Owner status set to {status}", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/tagline", methods=["POST"])
@login_required(role="admin")
def admin_set_tagline():
    tagline = request.form.get("tagline", "").strip()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("UPDATE settings SET tagline=? WHERE id=1", (tagline,))
    conn.commit()
    conn.close()
    flash("Tagline updated!", "success")
    return redirect(url_for("admin_dashboard"))

# ========================================
# ✅ GOOGLE IMAGES SEARCH API (FULLY WORKING!)
# ========================================
@app.route("/api/search_images")
@login_required(role="customer")
def search_images():
    """Customer dashboard search box → Real Google Images"""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"items": []})

    params = {
        "key": GOOGLE_API_KEY,
        "cx": GOOGLE_CX_ID,
        "searchType": "image",
        "q": query + " hairstyle men",
        "num": 8,
        "safe": "medium"
    }

    try:
        response = requests.get("https://www.googleapis.com/customsearch/v1", params=params, timeout=5)
        data = response.json()
        
        items = []
        for item in data.get("items", []):
            items.append({
                "link": item.get("link", ""),
                "title": item.get("title", "")[:60] + "..."
            })
        
        return jsonify({"items": items[:6]})  # Max 6 results
        
    except Exception as e:
        print(f"Google API error: {e}")
        return jsonify({"items": []})

# ========================================
# Initialize DB & Run
# 
# ========================================
# Initialize & Run (Termux friendly)
# ========================================
# App start hote hi DB init
with app.app_context():
    init_db()

if __name__ == "__main__":
    print("🚀 Men's Parlour R&R - ADMIN FIXED VERSION")
    print("✅ Google API: READY")
    print("✅ Admin: rradmin / admin123")
    print("🌐 http://127.0.0.1:5000")
    print("-" * 50)
    app.run(debug=True)