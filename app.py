import sqlite3
import os
import uuid
from datetime import datetime, timezone
from flask import Flask, request, jsonify, session, redirect, render_template, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# To this (it forces Flask to look in the current folder for 'static'):
app = Flask(__name__, static_folder="static", static_url_path="/static")
# In production, set this as an environment variable to keep sessions persistent
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

DATABASE = "database.db"


UPLOAD_FOLDER = 'static/uploads'
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ---------------- DATABASE MANAGEMENT ----------------
def get_db():
    """Opens a new database connection if there is none yet for the current application context."""
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    """Closes the database again at the end of the request."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db():
    """Initializes the database schema."""
    with app.app_context():
        db = get_db()
        cur = db.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            )
        """)
        # Update only the notes table part in init_db()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS notes (
            id TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            title TEXT,
            content TEXT,
            tags TEXT,
            image_path TEXT,  -- ADDED THIS
            created_at TEXT,
            is_deleted INTEGER DEFAULT 0,
            deleted_at TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id)
            )
        """)
        db.commit()

# Initialize DB on startup
init_db()

# ---------------- HELPERS ----------------
def get_user_id():
    return session.get("user_id")

# ---------------- AUTH ROUTES ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    if user and check_password_hash(user["password"], password):
        session["user_id"] = user["id"]
        return jsonify({"message": "ok"})

    return jsonify({"error": "Invalid username or password"}), 401

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not username or not password:
        return jsonify({"error": "Username and password required"}), 400

    db = get_db()
    try:
        db.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (username, generate_password_hash(password))
        )
        db.commit()
        return jsonify({"message": "registered"}), 201
    except sqlite3.IntegrityError:
        return jsonify({"error": "Username already exists"}), 400

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- PAGE ROUTES ----------------
@app.route("/")
def home():
    uid = get_user_id() # or session.get("user_id")
    if not uid:
        return redirect("/login")
    
    # NEW: Fetch name and determine greeting
    db = get_db()
    user = db.execute("SELECT username FROM users WHERE id = ?", (uid,)).fetchone()
    
    hour = datetime.now().hour
    if hour < 12:
        greeting = "Good morning"
    elif hour < 18:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    return render_template("index.html", name=user["username"], greeting=greeting)

# ---------------- NOTES API ----------------
@app.route("/notes", methods=["GET"])
def get_notes():
    user_id = get_user_id()
    db = get_db()
    cur = db.execute("SELECT * FROM notes WHERE user_id = ? AND is_deleted = 0 ORDER BY created_at DESC", (user_id,))
    notes = []
    for n in cur.fetchall():
        notes.append({
            "id": n["id"], "title": n["title"], "content": n["content"],
            "tags": n["tags"].split(",") if n["tags"] else [],
            "image_path": n["image_path"] # New field
        })
    return jsonify(notes)

@app.route("/notes", methods=["POST"])
def add_note():
    user_id = get_user_id()
    if not user_id: 
        return jsonify({"error": "unauthorized"}), 401

    # Text data
    title = request.form.get("title", "Untitled")
    content = request.form.get("content", "")
    tags_input = request.form.get("tags", "")
    tags = ",".join([t.strip() for t in str(tags_input).split(",") if t.strip()])

    # Image upload section (The part causing the error)
    image_path = ""
    
    file = request.files.get('image')
    
    if file and file.filename != '' and allowed_file(file.filename):
        filename = secure_filename(f"{uuid.uuid4()}_{file.filename}")
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    
        file.save(filepath)
    
        if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
            image_path = filename   # IMPORTANT CHANGE
        else:
            return jsonify({"error": "Image corrupted"}), 400

    # Database section
    db = get_db()
    db.execute("""
        INSERT INTO notes (id, user_id, title, content, tags, image_path, created_at, is_deleted)
        VALUES (?, ?, ?, ?, ?, ?, ?, 0)
    """, (
        str(uuid.uuid4()), user_id, title, content, tags, image_path,
        datetime.now(timezone.utc).isoformat()
    ))
    db.commit()
    return jsonify({"message": "added"}), 201

@app.route("/notes/<note_id>", methods=["PUT"])
def update_note(note_id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    data = request.get_json(silent=True) or {}
    tags_input = data.get("tags", "")
    tags = ",".join([t.strip() for t in str(tags_input).split(",") if t.strip()])

    db = get_db()
    db.execute("""
        UPDATE notes
        SET title = ?, content = ?, tags = ?
        WHERE id = ? AND user_id = ?
    """, (data.get("title"), data.get("content"), tags, note_id, user_id))
    db.commit()

    return jsonify({"message": "updated"})

@app.route("/notes/<note_id>", methods=["DELETE"])
def delete_note(note_id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    db = get_db()
    db.execute("""
        UPDATE notes
        SET is_deleted = 1, deleted_at = ?
        WHERE id = ? AND user_id = ?
    """, (datetime.now(timezone.utc).isoformat(), note_id, user_id))
    db.commit()

    return jsonify({"message": "moved to trash"})

# ---------------- TRASH & RESTORE ----------------
@app.route("/trash", methods=["GET"])
def get_trash():
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    db = get_db()
    cur = db.execute("""
        SELECT * FROM notes
        WHERE user_id = ? AND is_deleted = 1
        ORDER BY datetime(deleted_at) DESC
    """, (user_id,))

    notes = [{
        "id": n["id"],
        "title": n["title"],
        "content": n["content"],
        "deleted_at": n["deleted_at"]
    } for n in cur.fetchall()]
    
    return jsonify(notes)

@app.route("/notes/<note_id>/undo", methods=["POST"])
def undo_delete(note_id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    db = get_db()
    db.execute("""
        UPDATE notes
        SET is_deleted = 0, deleted_at = NULL
        WHERE id = ? AND user_id = ?
    """, (note_id, user_id))
    db.commit()

    return jsonify({"message": "restored"})

@app.route("/notes/<note_id>/hard", methods=["DELETE"])
def hard_delete(note_id):
    user_id = get_user_id()
    if not user_id:
        return jsonify({"error": "unauthorized"}), 401

    db = get_db()
    db.execute("DELETE FROM notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    db.commit()

    return jsonify({"message": "deleted forever"})

if __name__ == "__main__":
    app.run(debug=True)