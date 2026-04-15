# =============================
# FULL APP PRO: Flask + AI + VECTOR SEARCH (CLIP) + FIXED
# =============================

# pip install flask requests pillow numpy
# (Optional nâng cao: pip install onnxruntime)

import os
import sqlite3
import base64
import requests
import numpy as np
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, send_from_directory
from PIL import Image

UPLOAD_FOLDER = "images"
DB_PATH = "products.db"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

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
            embedding BLOB,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

# =============================
# IMAGE UTILS
# =============================

def compress_image(path):
    img = Image.open(path)
    img = img.convert("RGB")
    img.save(path, quality=60, optimize=True)

# =============================
# FAKE EMBEDDING (nhẹ cho Termux)
# =============================

def image_to_vector(path):
    img = Image.open(path).resize((32,32)).convert("L")
    arr = np.array(img).flatten()
    arr = arr / 255.0
    return arr

# =============================
# SIMILARITY
# =============================

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-8)

# =============================
# AI NAME
# =============================

def get_product_name(image_path):
    try:
        with open(image_path, "rb") as f:
            image_base64 = base64.b64encode(f.read()).decode("utf-8")

        res = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": "gpt-4.1-mini",
                "input": [{
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": "Name this product briefly."},
                        {"type": "input_image", "image_base64": image_base64}
                    ]
                }]
            }
        )

        data = res.json()
        if "output" in data:
            return data["output"][0]["content"][0].get("text", "unknown")

        return "unknown"

    except Exception as e:
        print("AI error:", e)
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
video { width:90%; border-radius:15px }
button { padding:12px; margin:5px; border:none; border-radius:10px }
.add { background:#28a745 }
.search { background:#ffc107 }
input { padding:10px; margin:5px; border-radius:8px }
.card { background:#222; margin:10px; padding:10px; border-radius:10px }
img { width:80px }
</style>
</head>
<body>

<h2>📸 Smart Camera</h2>
<video id="video" autoplay playsinline></video><br>

<button class="add" onclick="captureAdd()">📦 Add</button>
<button class="search" onclick="captureSearch()">🔍 Search</button>

<br>
<input id="price" placeholder="Price">
<input id="note" placeholder="Note">

<h3 id="status"></h3>

<div id="searchResult"></div>
<h2>📦 Products</h2>
<div id="list"></div>

<canvas id="canvas" style="display:none"></canvas>

<script>
let video = document.getElementById('video');
let canvas = document.getElementById('canvas');

navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } } })
.then(stream => video.srcObject = stream)
.catch(err => alert(err));

function captureBlob() {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext('2d').drawImage(video, 0, 0);
    return new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg'));
}

async function captureAdd() {
    let blob = await captureBlob();

    let price = document.getElementById('price').value;
    if (!price) return alert("Nhập giá trước!");

    let formData = new FormData();
    formData.append("image", blob, "img.jpg");
    formData.append("price", price);
    formData.append("note", document.getElementById('note').value);

    document.getElementById('status').innerText = "Saving...";

    let res = await fetch('/add', { method:'POST', body: formData });
    let data = await res.json();

    document.getElementById('status').innerText = "Saved: " + data.name;
    load();
}

async function captureSearch() {
    let blob = await captureBlob();

    let formData = new FormData();
    formData.append("image", blob, "img.jpg");

    document.getElementById('status').innerText = "Searching...";

    let res = await fetch('/search', { method:'POST', body: formData });
    let data = await res.json();

    let html = `<h3>Top match:</h3>`;

    data.results.forEach(p => {
        html += `<div class='card'>
            <img src='/images/${p.image.split('/').pop()}'>
            <div>${p.name}</div>
            <div>${p.price} VND</div>
            <div>Score: ${p.score.toFixed(2)}</div>
        </div>`;
    });

    document.getElementById('searchResult').innerHTML = html;
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
    price = request.form.get("price")
    note = request.form.get("note","")

    if not price:
        return jsonify({"error": "Missing price"}), 400

    filename = f"{datetime.now().timestamp()}.jpg"
    path = os.path.join(UPLOAD_FOLDER, filename)
    file.save(path)

    compress_image(path)

    name = get_product_name(path)
    vec = image_to_vector(path)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO products (name,image_path,price,note,embedding,created_at) VALUES (?,?,?,?,?,?)",
              (name,path,price,note,vec.tobytes(),datetime.now().isoformat()))
    conn.commit()
    conn.close()

    return jsonify({"name": name})

@app.route("/search", methods=["POST"])
def search():
    file = request.files["image"]

    temp = os.path.join(UPLOAD_FOLDER, "temp.jpg")
    file.save(temp)

    query_vec = image_to_vector(temp)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM products")
    rows = c.fetchall()
    conn.close()

    results = []

    for r in rows:
        db_vec = np.frombuffer(r[5], dtype=np.float64)
        score = cosine_similarity(query_vec, db_vec)

        results.append({
            "id": r[0],
            "name": r[1],
            "image": r[2],
            "price": r[3],
            "score": float(score)
        })

    results = sorted(results, key=lambda x: x["score"], reverse=True)[:5]

    return jsonify({"results": results})

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
    app.run(host='0.0.0.0', port=5009)
