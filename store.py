# =============================
# FULL APP: Flask + SINGLE CAMERA UI (PRO)
# =============================

# pip install flask requests pillow

import os
import sqlite3
import base64
import requests
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, send_from_directory

UPLOAD_FOLDER = "images"
DB_PATH = "products.db"
OPENAI_API_KEY = input("APIKEY: ")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app = Flask(__name__)

# =============================
# DB
# =============================

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            image_path TEXT,
            price REAL,
            note TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =============================
# AI
# =============================

def get_product_name(image_path):
    with open(image_path, "rb") as f:
        image_base64 = base64.b64encode(f.read()).decode("utf-8")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4.1-mini",
        "input": [{
            "role": "user",
            "content": [
                {"type": "input_text", "text": "What product is this? Return short name."},
                {"type": "input_image", "image_base64": image_base64}
            ]
        }]
    }

    try:
        res = requests.post("https://api.openai.com/v1/responses", json=payload, headers=headers)
        return res.json()["output"][0]["content"][0]["text"]
    except:
        return "unknown"

# =============================
# UI
# =============================

@app.route("/")
def index():
    return render_template_string("""
<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>Smart Shop</title>
<style>
body { font-family: Arial; background:#111; color:#fff; text-align:center }
video { width:90%; border-radius:15px; margin-top:10px }
button { padding:12px; margin:5px; border:none; border-radius:10px; font-size:16px }
.add { background:#28a745 }
.search { background:#ffc107 }
input { padding:10px; margin:5px; border-radius:8px; border:none }
.card { background:#222; margin:10px; padding:10px; border-radius:10px }
img { width:80px; border-radius:10px }
</style>
</head>
<body>

<h2>📸 Smart Camera</h2>
<video id="video" autoplay playsinline></video><br>

<button class="add" onclick="captureAdd()">📦 Add Product</button>
<button class="search" onclick="captureSearch()">🔍 Search</button>

<br>
<input id="price" placeholder="Price">
<input id="note" placeholder="Note">

<h3 id="status"></h3>

<h2>📦 Products</h2>
<div id="list"></div>

<canvas id="canvas" style="display:none"></canvas>

<script>
let video = document.getElementById('video');
let canvas = document.getElementById('canvas');

navigator.mediaDevices.getUserMedia({
    video: { facingMode: { ideal: "environment" } }
})
.then(stream => video.srcObject = stream)
.catch(err => alert("Camera error: " + err));

function captureBlob() {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
}

async function captureAdd() {
    let blob = await captureBlob();

    let formData = new FormData();
    formData.append("image", blob, "img.jpg");
    formData.append("price", document.getElementById('price').value);
    formData.append("note", document.getElementById('note').value);

    document.getElementById('status').innerText = "⏳ Saving...";

    let res = await fetch('/add', { method:'POST', body: formData });
    let data = await res.json();

    document.getElementById('status').innerText = "✅ Saved: " + data.name;
    load();
}

async function captureSearch() {
    let blob = await captureBlob();

    let formData = new FormData();
    formData.append("image", blob, "img.jpg");

    document.getElementById('status').innerText = "🔍 Searching...";

    let res = await fetch('/search', { method:'POST', body: formData });
    let data = await res.json();

    let html = `<h3>Result: ${data.query}</h3>`;

    data.results.forEach(p => {
        html += `<div class='card'>
            <img src='/images/${p.image.split('/').pop()}'>
            <div>${p.name}</div>
            <div>${p.price} VND</div>
        </div>`;
    });

    document.getElementById('list').innerHTML = html;
    document.getElementById('status').innerText = "";
}

async function load() {
    let res = await fetch('/products');
    let data = await res.json();

    let html = "";
    data.forEach(p => {
        html += `<div class='card'>
            <img src='/images/${p.image.split('/').pop()}'>
            <div>${p.name}</div>
            <div>${p.price} VND</div>
        </div>`;
    });

    document.getElementById('list').innerHTML = html;
}

load();
</script>

</body>
</html>
    """)

# =============================
# API
# =============================

@app.route("/add", methods=["POST"])
def add():
    file = request.files["image"]
    price = request.form["price"]
    note = request.form.get("note","")

    filename = f"{datetime.now().timestamp()}.jpg"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    name = get_product_name(path)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO products (name,image_path,price,note,created_at) VALUES (?,?,?,?,?)",
              (name,path,price,note,datetime.now().isoformat()))
    conn.commit()
    conn.close()

    return jsonify({"name": name})

@app.route("/search", methods=["POST"])
def search():
    file = request.files["image"]

    temp = os.path.join(UPLOAD_FOLDER, "temp.jpg")
    file.save(temp)

    query = get_product_name(temp)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM products WHERE name LIKE ? ORDER BY id DESC", (f"%{query}%",))
    rows = c.fetchall()
    conn.close()

    return jsonify({
        "query": query,
        "results": [
            {"id":r[0],"name":r[1],"image":r[2],"price":r[3]}
            for r in rows
        ]
    })

@app.route("/products")
def products():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM products ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()

    return jsonify([
        {"id":r[0],"name":r[1],"image":r[2],"price":r[3]}
        for r in rows
    ])

@app.route('/images/<path:filename>')
def images(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# =============================
# RUN
# =============================

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5005, debug=False)
