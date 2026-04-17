import sqlite3
from flask import Flask, request, jsonify, session, redirect, render_template
from werkzeug.security import generate_password_hash, check_password_hash
import uuid
from datetime import datetime, timezone
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(24))

DATABASE = "database.db"


# ---------------- DB ----------------
def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS notes (
        id TEXT PRIMARY KEY,
        user_id INTEGER,
        title TEXT,
        content TEXT,
        tags TEXT,
        created_at TEXT,
        is_deleted INTEGER DEFAULT 0,
        deleted_at TEXT
    )
    """)

    conn.commit()
    conn.close()


init_db()


# ---------------- HELPERS ----------------
def get_user():
    return session.get("user_id")


# ---------------- AUTH ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    data = request.json

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE username = ?", (data["username"],))
    user = cur.fetchone()
    conn.close()

    if user and check_password_hash(user["password"], data["password"]):
        session["user_id"] = user["id"]
        return jsonify({"message": "ok"})

    return jsonify({"error": "invalid"}), 401


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html")

    data = request.json

    try:
        conn = get_db()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO users (username, password) VALUES (?, ?)",
            (data["username"], generate_password_hash(data["password"]))
        )

        conn.commit()
        conn.close()

        return jsonify({"message": "registered"})
    except:
        return jsonify({"error": "user exists"}), 400


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ---------------- PAGE ----------------
@app.route("/")
def home():
    if not get_user():
        return redirect("/login")
    return render_template("index.html")


# ---------------- NOTES (ACTIVE) ----------------
@app.route("/notes", methods=["GET"])
def get_notes():
    user = get_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM notes
        WHERE user_id = ? AND is_deleted = 0
        ORDER BY datetime(created_at) DESC
    """, (user,))

    notes = []
    for n in cur.fetchall():
        notes.append({
            "id": n["id"],
            "title": n["title"],
            "content": n["content"],
            "tags": n["tags"].split(",") if n["tags"] else []
        })

    conn.close()
    return jsonify(notes)


# ---------------- ADD NOTE ----------------
@app.route("/notes", methods=["POST"])
def add_note():
    user = get_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    data = request.json

    note_id = str(uuid.uuid4())

    tags = data.get("tags", "")
    if isinstance(tags, str):
        tags = ",".join([t.strip() for t in tags.split(",") if t.strip()])

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO notes
        (id, user_id, title, content, tags, created_at, is_deleted, deleted_at)
        VALUES (?, ?, ?, ?, ?, ?, 0, NULL)
    """, (
        note_id,
        user,
        data["title"],
        data["content"],
        tags,
        datetime.now(timezone.utc).isoformat()
    ))

    conn.commit()
    conn.close()

    return jsonify({"message": "added"})


# ---------------- UPDATE NOTE ----------------
@app.route("/notes/<note_id>", methods=["PUT"])
def update_note(note_id):
    user = get_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    data = request.json

    tags = data.get("tags", "")
    if isinstance(tags, str):
        tags = ",".join([t.strip() for t in tags.split(",") if t.strip()])

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE notes
        SET title = ?, content = ?, tags = ?
        WHERE id = ? AND user_id = ?
    """, (data["title"], data["content"], tags, note_id, user))

    conn.commit()
    conn.close()

    return jsonify({"message": "updated"})


# ---------------- SOFT DELETE ----------------
@app.route("/notes/<note_id>", methods=["DELETE"])
def delete_note(note_id):
    user = get_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE notes
        SET is_deleted = 1,
            deleted_at = ?
        WHERE id = ? AND user_id = ?
    """, (datetime.now(timezone.utc).isoformat(), note_id, user))

    conn.commit()
    conn.close()

    return jsonify({"message": "moved to trash"})


# ---------------- TRASH ----------------
@app.route("/trash", methods=["GET"])
def get_trash():
    user = get_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM notes
        WHERE user_id = ? AND is_deleted = 1
        ORDER BY datetime(deleted_at) DESC
    """, (user,))

    notes = []
    for n in cur.fetchall():
        notes.append({
            "id": n["id"],
            "title": n["title"],
            "content": n["content"],
            "tags": n["tags"].split(",") if n["tags"] else [],
            "deleted_at": n["deleted_at"]
        })

    conn.close()
    return jsonify(notes)


# ---------------- UNDO DELETE ----------------
@app.route("/notes/<note_id>/undo", methods=["POST"])
def undo_delete(note_id):
    user = get_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        UPDATE notes
        SET is_deleted = 0,
            deleted_at = NULL
        WHERE id = ? AND user_id = ?
    """, (note_id, user))

    conn.commit()
    conn.close()

    return jsonify({"message": "restored"})


# ---------------- HARD DELETE ----------------
@app.route("/notes/<note_id>/hard", methods=["DELETE"])
def hard_delete(note_id):
    user = get_user()
    if not user:
        return jsonify({"error": "unauthorized"}), 401

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        DELETE FROM notes
        WHERE id = ? AND user_id = ?
    """, (note_id, user))

    conn.commit()
    conn.close()

    return jsonify({"message": "deleted forever"})


if __name__ == "__main__":
    app.run(debug=True)