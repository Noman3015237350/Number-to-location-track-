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
    "google_maps_api_key": "",   # optional
    "ip_geolocation_api": ""     # e.g., ipinfo token or other
}
# ----------------------------

app = Flask(__name__)
app.secret_key = os.environ.get("ENIST_FLASK_SECRET", "change-this-secret-for-prod")

def load_config():
    if not CONFIG_FILE.exists():
        with open(CONFIG_FILE, "w") as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG.copy()
    return json.loads(CONFIG_FILE.read_text())

def save_config(cfg):
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))

cfg = load_config()

# ---------- BOOTSTRAP: if no password hash yet, create one interactively ----------
def ensure_password():
    if cfg.get("password_hash"):
        return
    env_pw = os.environ.get("Noman")
    if env_pw:
        cfg["password_hash"] = generate_password_hash(env_pw)
        save_config(cfg)
        print("[ENIST] Admin password loaded from ENIST_ADMIN_PASSWORD env var.")
        return
    # If running as script and no password set, prompt once in console
    try:
        if os.isatty(0):
            print("No admin password set for ENIST. Please create an admin password now.")
            pw = input("Enter new admin password: ").strip()
            if not pw:
                print("No password entered — using default 'admin' (not recommended).")
                pw = "admin"
            cfg["password_hash"] = generate_password_hash(pw)
            save_config(cfg)
            print("Password saved to config.json (hashed).")
    except Exception:
        # fallback: do nothing (will prevent login until env var or interactive set)
        pass

ensure_password()

# ---------- simple login required decorator ----------
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)
    return decorated

# ---------- Logo generator ----------
def generate_logo(text="TNEH", filename=DATA_DIR/"static"/"logo.png"):
    filename.parent.mkdir(parents=True, exist_ok=True)
    W, H = 600, 200
    img = Image.new("RGBA", (W, H), (255,255,255,0))
    draw = ImageDraw.Draw(img)

    # try common fonts; fallback to default
    font_path = None
    possible = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
    ]
    for p in possible:
        if Path(p).exists():
            font_path = p
            break

    try:
        font = ImageFont.truetype(font_path or None, 110)
    except Exception:
        font = ImageFont.load_default()

    text_w, text_h = draw.textsize(text, font=font)
    x = (W - text_w) // 2
    y = (H - text_h) // 2 - 10
    # background rounded rectangle
    draw.rounded_rectangle([(10,10),(W-10,H-10)], radius=20, fill=(20,50,120,230))
    draw.text((x,y), text, font=font, fill=(255,255,255,255))
    img.save(str(filename), format="PNG")
    return str(filename)

# generate logo on startup (if not exists)
logo_path = DATA_DIR/"static"/"logo.png"
if not logo_path.exists():
    generate_logo("TNEH", logo_path)

# ---------- Routes ----------
@app.route("/")
def index():
    if session.get("logged_in"):
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        pw = request.form.get("password","")
        if cfg.get("password_hash") and check_password_hash(cfg["password_hash"], pw):
            session["logged_in"] = True
            flash("Logged in.", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("Invalid password.", "danger")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
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
            is_valid = phonenumbers.is_valid_number(pn)
            country = geocoder.description_for_number(pn, "en")
            oper = carrier.name_for_number(pn, "en")
            timezones = p_tz.time_zones_for_number(pn)
            e164 = phonenumbers.format_number(pn, phonenumbers.PhoneNumberFormat.E164)
            result = {
                "phone_raw": phone_raw,
                "e164": e164,
                "valid": is_valid,
                "country": country,
                "carrier": oper,
                "timezones": timezones
            }
            # minimal coords attempt: try geocoding the country/region name via an external geocode service if configured
            coords = None
            gm_key = cfg.get("google_maps_api_key") or os.environ.get("ENIST_GOOGLE_MAPS_KEY")
            if gm_key:
                # try Google Geocoding API
                try:
                    gresp = requests.get("https://maps.googleapis.com/maps/api/geocode/json", params={
                        "address": country,
                        "key": gm_key
                    }, timeout=8).json()
                    if gresp.get("results"):
                        loc = gresp["results"][0]["geometry"]["location"]
                        coords = (loc["lat"], loc["lng"])
                except Exception as e:
                    coords = None
            result["coords"] = coords
        except Exception as e:
            result = {"error": "Phone parse error: " + str(e), "phone_raw": phone_raw}

        # ip lookup (consent-based): if provided, call configured ip geolocation provider
        ip_info = None
        if ip_input:
            # use ipinfo.io (token optional) as example
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
    path = generate_logo(text, DATA_DIR/"static"/"logo.png")
    flash(f"Logo generated: {text}", "success")
    return redirect(url_for("dashboard"))

@app.route("/download-logo")
@login_required
def download_logo():
    p = DATA_DIR/"static"/"logo.png"
    return send_file(str(p), as_attachment=True, download_name="TNEH_logo.png")

# Admin settings - change API keys / password
@app.route("/settings", methods=["GET","POST"])
@login_required
def settings():
    if request.method == "POST":
        new_gmap = request.form.get("google_maps_api_key","").strip()
        new_ip_token = request.form.get("ip_geolocation_api","").strip()
        cfg["google_maps_api_key"] = new_gmap
        cfg["ip_geolocation_api"] = new_ip_token
        # change password if provided
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
