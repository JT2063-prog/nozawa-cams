import os, io, json, time, threading, datetime, requests, glob
from flask import Flask, jsonify, send_file, Response
from PIL import Image, ImageDraw, ImageFont
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

HEADERS       = {"Referer": "https://en.nozawaski.com/", "User-Agent": "Mozilla/5.0"}
DATA_FILE     = "data/snapshots.json"
FRAMES_DIR    = "data/frames"
TIMELAPSE_DIR = "data/timelapse"
CAPTURE_INTERVAL = 1800  # 30 minutes

for d in ["data", FRAMES_DIR, TIMELAPSE_DIR]:
    os.makedirs(d, exist_ok=True)

def load_snapshots():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            return json.load(f)
    return []

def save_snapshots(snaps):
    with open(DATA_FILE, "w") as f:
        json.dump(snaps[-2000:], f)

def analyse_whiteness(img_bytes):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    arr = np.array(img)
    white = (arr[:,:,0] > 200) & (arr[:,:,1] > 200) & (arr[:,:,2] > 200)
    return round(float(white.mean() * 100), 1)

def add_overlay(img_bytes, ts_display, cam_label, whiteness):
    img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    img = img.resize((640, 360), Image.LANCZOS)
    draw = ImageDraw.Draw(img)
    try:
        font_b = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18)
        font_s = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
    except:
        font_b = font_s = ImageFont.load_default()
    bar = Image.new("RGBA", (640, 44), (0, 0, 0, 170))
    img.paste(bar, (0, 316), bar)
    draw.text((8, 320), cam_label, fill="white", font=font_b)
    draw.text((8, 340), f"{ts_display}   Snow: {whiteness}%", fill="#aad4ff", font=font_s)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()

def save_frame(cam_id, img_bytes, ts_display, whiteness):
    cam_dir = os.path.join(FRAMES_DIR, cam_id)
    os.makedirs(cam_dir, exist_ok=True)
    safe_ts = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H-%M-%S")
    path = os.path.join(cam_dir, f"{safe_ts}.jpg")
    framed = add_overlay(img_bytes, ts_display, CAMS[cam_id]["label"], whiteness)
    with open(path, "wb") as f:
        f.write(framed)
    frames = sorted(glob.glob(os.path.join(cam_dir, "*.jpg")))
    for old in frames[:-336]:
        os.remove(old)

def capture_all():
    snaps = load_snapshots()
    ts_iso     = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    ts_display = datetime.datetime.utcnow().strftime("%d %b %Y  %H:%M UTC")
    for cam_id, cam in CAMS.items():
        try:
            r = requests.get(cam["url"], headers=HEADERS, timeout=15)
            r.raise_for_status()
            whiteness = analyse_whiteness(r.content)
            save_frame(cam_id, r.content, ts_display, whiteness)
            snaps.append({"ts": ts_iso, "cam": cam_id, "whiteness": whiteness})
            print(f"  {cam_id}: {whiteness}%")
        except Exception as e:
            print(f"  {cam_id}: ERROR {e}")
    save_snapshots(snaps)

def build_timelapse(cam_id, days=1, fps=8):
    cam_dir = os.path.join(FRAMES_DIR, cam_id)
    if not os.path.exists(cam_dir):
        return None, "No frames captured yet for this camera"
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    all_frames = sorted(glob.glob(os.path.join(cam_dir, "*.jpg")))
    selected = []
    for f in all_frames:
        try:
            name = os.path.basename(f).replace(".jpg", "")
            dt = datetime.datetime.strptime(name, "%Y-%m-%dT%H-%M-%S")
            if dt >= cutoff:
                selected.append(f)
        except:
            selected.append(f)
    if len(selected) < 2:
        return None, f"Only {len(selected)} frame(s) so far — need at least 2. Check back after more captures."
    images = []
    for f in selected:
        try:
            img = Image.open(f).convert("RGB").resize((480, 270), Image.LANCZOS)
            images.append(img)
        except:
            pass
    if len(images) < 2:
        return None, "Could not load enough frames"
    out_path = os.path.join(TIMELAPSE_DIR, f"{cam_id}_{days}d.gif")
    duration_ms = max(60, int(1000 / fps))
    images[0].save(out_path, save_all=True, append_images=images[1:],
                   optimize=False, duration=duration_ms, loop=0)
    return out_path, None

def scheduler():
    while True:
        print(f"[{datetime.datetime.utcnow().strftime('%H:%M')}] Capturing...")
        capture_all()
        time.sleep(CAPTURE_INTERVAL)

threading.Thread(target=scheduler, daemon=True).start()

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

@app.route("/api/snapshots", methods=["DELETE"])
def delete_snapshots():
    save_snapshots([])
    return jsonify({"ok": True})

@app.route("/api/status")
def api_status():
    snaps = load_snapshots()
    frame_counts = {}
    for cam_id in CAMS:
        cam_dir = os.path.join(FRAMES_DIR, cam_id)
        frame_counts[cam_id] = len(glob.glob(os.path.join(cam_dir, "*.jpg"))) if os.path.exists(cam_dir) else 0
    return jsonify({
        "snapshots": len(snaps),
        "frame_counts": frame_counts,
        "interval_minutes": CAPTURE_INTERVAL // 60,
        "last_capture": snaps[-1]["ts"] if snaps else None
    })

@app.route("/api/timelapse/<cam_id>")
def get_timelapse(cam_id):
    from flask import request as freq
    days = int(freq.args.get("days", 1))
    fps  = int(freq.args.get("fps", 8))
    if cam_id not in CAMS:
        return "Not found", 404
    path, err = build_timelapse(cam_id, days=days, fps=fps)
    if err:
        return jsonify({"error": err}), 404
    return send_file(path, mimetype="image/gif",
                     download_name=f"nozawa-{cam_id}-{days}d.gif")
@app.route("/api/download-frames")
def download_frames():
    import zipfile, tempfile
    cam_dir = os.path.join(FRAMES_DIR, "yamabiko")
    if not os.path.exists(cam_dir):
        return "No frames found", 404
    frames = sorted(glob.glob(os.path.join(cam_dir, "*.jpg")))
    if not frames:
        return "No frames found", 404
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".zip")
    with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in frames:
            zf.write(f, os.path.basename(f))
    return send_file(tmp.name, mimetype="application/zip",
                     as_attachment=True,
                     download_name="yamabiko-frames.zip")
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
