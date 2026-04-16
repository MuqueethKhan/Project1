from flask import Flask, request, jsonify, send_from_directory, session, redirect
import json
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = "secret123"

NOTES_FILE = "notes.json"
USERS_FILE = "users.json"

# ---------------- INIT FILES ----------------
if not os.path.exists(NOTES_FILE):
    with open(NOTES_FILE, "w") as f:
        json.dump({}, f)

if not os.path.exists(USERS_FILE):
    with open(USERS_FILE, "w") as f:
        json.dump({"users": []}, f)

# ---------------- HELPERS ----------------
def load_json(file):
    with open(file, "r") as f:
        return json.load(f)

def save_json(file, data):
    with open(file, "w") as f:
        json.dump(data, f, indent=2)

# ---------------- AUTH ----------------
@app.route("/register", methods=["POST"])
def register():
    data = request.json
    users = load_json(USERS_FILE)["users"]

    for u in users:
        if u["username"] == data["username"]:
            return jsonify({"error": "User exists"}), 400

    users.append({
        "username": data["username"],
        "password": data["password"]
    })

    save_json(USERS_FILE, {"users": users})
    return jsonify({"message": "Registered"})

@app.route("/login", methods=["POST"])
def login():
    data = request.json
    users = load_json(USERS_FILE)["users"]

    for u in users:
        if u["username"] == data["username"] and u["password"] == data["password"]:
            session["user"] = data["username"]
            return jsonify({"message": "Login success"})

    return jsonify({"error": "Invalid"}), 401

@app.route("/logout")
def logout():
    session.pop("user", None)
    return redirect("/login-page")

# ---------------- PAGES ----------------
@app.route("/")
def home():
    if "user" not in session:
        return redirect("/login-page")
    return send_from_directory(".", "index.html")

@app.route("/login-page")
def login_page():
    return send_from_directory(".", "login.html")

@app.route("/register-page")
def register_page():
    return send_from_directory(".", "register.html")

# ---------------- NOTES (USER-SPECIFIC) ----------------
@app.route("/notes", methods=["GET"])
def get_notes():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data = load_json(NOTES_FILE)
    user = session["user"]

    user_notes = data.get(user, [])
    user_notes.sort(key=lambda x: x["created_at"], reverse=True)

    return jsonify(user_notes)

@app.route("/notes", methods=["POST"])
def add_note():
    if "user" not in session:
        return jsonify({"error": "Unauthorized"}), 401

    data_json = request.json
    data = load_json(NOTES_FILE)
    user = session["user"]

    if user not in data:
        data[user] = []

    note = {
        "id": len(data[user]) + 1,
        "title": data_json["title"],
        "content": data_json["content"],
        "tags": [t.strip() for t in data_json["tags"].split(",") if t.strip()],
        "created_at": datetime.now().isoformat()
    }

    data[user].append(note)
    save_json(NOTES_FILE, data)

    return jsonify({"message": "Note added"})

# ---------------- RUN ----------------
if __name__ == "__main__":
    app.run(debug=True)