import os
import json
from pathlib import Path
from functools import wraps

from flask import Flask, render_template, request, redirect, url_for, session, send_file, flash
from werkzeug.security import generate_password_hash, check_password_hash
import phonenumbers
from phonenumbers import geocoder, carrier, timezone as p_tz
from PIL import Image, ImageDraw, ImageFont
import requests

# ---------- CONFIG ----------
DATA_DIR = Path(__file__).parent
CONFIG_FILE = DATA_DIR / "config.json"
DEFAULT_CONFIG = {
    "password_hash": None,
    "google_maps_api_key": "",
    "ip_geolocation_api": ""
}
# ----------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("ENIST_SECRET_KEY", os.urandom(24))

def load_config():
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG.copy()
    return json.loads(CONFIG_FILE.read_text())

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

cfg = load_config()

# ---------- PASSWORD SETUP ----------
def ensure_password():
    if cfg.get("password_hash"):
        return
    env_pw = os.environ.get("Noman")
    if env_pw:
        cfg["password_hash"] = generate_password_hash(env_pw)
        save_config(cfg)
        print("[ENIST] Admin password loaded from environment variable.")
        return
    try:
        if os.isatty(0):
            print("No admin password set for ENIST. Please create an admin password now.")
            pw = input("Enter new admin password: ").strip() or "admin"
            cfg["password_hash"] = generate_password_hash(pw)
            save_config(cfg)
            print("Password saved to config.json (hashed).")
    except Exception:
        pass

ensure_password()

# ---------- LOGIN REQUIRED DECORATOR ----------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("logged_in"):
            flash("Login required.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

# ---------- LOGO GENERATOR ----------
def generate_logo(text="TNEH", filename=DATA_DIR / "static" / "logo.png"):
    filename.parent.mkdir(parents=True, exist_ok=True)
    W, H = 600, 200
    img = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Try system fonts
    font = None
    for fpath in [
        "arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]:
        if Path(fpath).exists():
            font = ImageFont.truetype(fpath, 110)
            break
    if not font:
        font = ImageFont.load_default()

    # Center text
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (W - text_w) / 2
    y = (H - text_h) / 2 - 10

    # Rounded rectangle background
    draw.rounded_rectangle([(10,10),(W-10,H-10)], radius=20, fill=(20,50,120,230))
    draw.text((x, y), text, fill=(255,255,255,255), font=font)

    img.save(filename)
    return str(filename)

# Generate logo on startup if missing
logo_path = DATA_DIR / "static" / "logo.png"
if not logo_path.exists():
    generate_logo("TNEH", logo_path)

# ---------- ROUTES ----------
@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if cfg.get("password_hash") and check_password_hash(cfg["password_hash"], pw):
            session["logged_in"] = True
            flash("Logged in successfully.", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out.", "info")
    return redirect(url_for("login"))

@app.route("/dashboard", methods=["GET","POST"])
@login_required
def dashboard():
    result = None
    if request.method == "POST":
        phone_raw = request.form.get("phone","").strip()
        ip_input = request.form.get("ip","").strip()
        # phone lookup
        try:
            pn = phonenumbers.parse(phone_raw, None)
            result = {
                "phone_raw": phone_raw,
                "e164": phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164),
                "valid": phonenumbers.is_valid_number(pn),
                "country": geocoder.description_for_number(pn, "en"),
                "carrier": carrier.name_for_number(pn, "en"),
                "timezones": p_tz.time_zones_for_number(pn),
                "coords": None
            }
            # Google Maps API geocoding
            gm_key = cfg.get("google_maps_api_key") or os.environ.get("ENIST_GOOGLE_MAPS_KEY")
            if gm_key:
                try:
                    gresp = requests.get(
                        "https://maps.googleapis.com/maps/api/geocode/json",
                        params={"address": result["country"], "key": gm_key},
                        timeout=8
                    ).json()
                    if gresp.get("results"):
                        loc = gresp["results"][0]["geometry"]["location"]
                        result["coords"] = (loc["lat"], loc["lng"])
                except:
                    result["coords"] = None
        except Exception as e:
            result = {"error": f"Phone parse error: {e}", "phone_raw": phone_raw}

        # IP lookup
        ip_info = None
        if ip_input:
            token = cfg.get("ip_geolocation_api") or os.environ.get("ENIST_IPINFO_TOKEN")
            try:
                url = f"https://ipinfo.io/{ip_input}/json"
                if token:
                    url += f"?token={token}"
                ip_info = requests.get(url, timeout=8).json()
            except Exception as e:
                ip_info = {"error": str(e)}
        result["ip_info"] = ip_info

    return render_template("dashboard.html", result=result, logo_url=url_for("static", filename="logo.png"), cfg=cfg)

@app.route("/generate-logo", methods=["POST"])
@login_required
def generate_logo_route():
    text = request.form.get("logo_text","TNEH")[:20]
    generate_logo(text, DATA_DIR / "static" / "logo.png")
    flash(f"Logo generated: {text}", "success")
    return redirect(url_for("dashboard"))

@app.route("/download-logo")
@login_required
def download_logo():
    return send_file(str(DATA_DIR / "static" / "logo.png"), as_attachment=True, download_name="TNEH_logo.png")

@app.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    if request.method == "POST":
        cfg["google_maps_api_key"] = request.form.get("google_maps_api_key","").strip()
        cfg["ip_geolocation_api"] = request.form.get("ip_geolocation_api","").strip()
        newpw = request.form.get("new_password","").strip()
        if newpw:
            cfg["password_hash"] = generate_password_hash(newpw)
            flash("Password updated.", "success")
        save_config(cfg)
        flash("Settings saved.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", cfg=cfg)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
