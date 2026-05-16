import os, io, json, time, threading, datetime, requests
from flask import Flask, jsonify, send_file, Response
from PIL import Image
import numpy as np

app = Flask(__name__, static_folder="static", static_url_path="")

CAMS = {
    "yamabiko-top": {"label": "Kenashi summit", "alt": "1650m", "url": "https://nozawaski.sakura.ne.jp/livecam/yamabiko-top.jpg"},
    "yamabiko":     {"label": "Yamabiko D",      "alt": "1615m", "url": "https://nozawaski.sakura.ne.jp/livecam/yamabiko.jpg"},
    "uenotaira":    {"label": "Uenotaira",        "alt": "1407m", "url": "https://nozawaski.sakura.ne.jp/livecam/uenotaira.jpg"},
    "paradise":     {"label": "Paradise",         "alt": "1230m", "url": "https://nozawaski.sakura.ne.jp/livecam/paradise.jpg"},
    "hikage":       {"label": "Hikage",           "alt": "660m",  "url": "https://nozawaski.sakura.ne.jp/livecam/hikage.jpg"},
    "nagasaka":     {"label": "Nagasaka",         "alt": "616m",  "url": "https://nozawaski.sakura.ne.jp/livecam/nagasaka.jpg"},
    "karasawa":     {"label": "Karasawa",         "alt": "563m",  "url": "https://nozawaski.sakura.ne.jp/livecam/karasawa.jpg"},
}

HEADERS = {"Referer": "https://en.nozawaski.com/", "User-Agent": "Mozilla/5.0"}
DATA_FILE = "data/snapshots.json"
os.makedirs("data", exist_ok=True)

def load_snapshots():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return []

def save_snapshots(snaps):
    with open(DATA_FILE, "w") as f:
        json.dump(snaps[-500:], f)  # keep last 500

def analyse_whiteness(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    arr = np.array(img)
    white = (arr[:,:,0] > 200) & (arr[:,:,1] > 200) & (arr[:,:,2] > 200)
    return round(float(white.mean() * 100), 1)

def capture_all():
    snaps = load_snapshots()
    ts = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    for cam_id, cam in CAMS.items():
        try:
            r = requests.get(cam["url"], headers=HEADERS, timeout=15)
            r.raise_for_status()
            whiteness = analyse_whiteness(r.content)
            snaps.append({"ts": ts, "cam": cam_id, "whiteness": whiteness})
            print(f"  {cam_id}: {whiteness}%")
        except Exception as e:
            print(f"  {cam_id}: ERROR {e}")
    save_snapshots(snaps)

# Background hourly scheduler
def scheduler():
    while True:
        print(f"[{datetime.datetime.utcnow().strftime('%H:%M')}] Auto-capturing...")
        capture_all()
        time.sleep(3600)

threading.Thread(target=scheduler, daemon=True).start()

# --- Routes ---

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/api/cams")
def api_cams():
    return jsonify(CAMS)

@app.route("/api/proxy/<cam_id>")
def proxy(cam_id):
    if cam_id not in CAMS:
        return "Not found", 404
    try:
        r = requests.get(CAMS[cam_id]["url"], headers=HEADERS, timeout=15)
        r.raise_for_status()
        return Response(r.content, mimetype="image/jpeg",
                        headers={"Cache-Control": "no-cache, no-store"})
    except Exception as e:
        return str(e), 502

@app.route("/api/capture", methods=["POST"])
def api_capture():
    capture_all()
    return jsonify({"ok": True, "ts": datetime.datetime.utcnow().isoformat()})

@app.route("/api/snapshots")
def api_snapshots():
    return jsonify(load_snapshots())

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

@app.route("/api/snapshots", methods=["DELETE"])
def delete_snapshots():
    save_snapshots([])
    return jsonify({"ok": True})
