# ENIST (Educational Number Intelligence & Safety Tracker) — Pro (Flask)

## Requirements
Python 3.10+ (recommended)
pip install -r requirements.txt

## First-time setup
Option A (interactive):
$ python app.py
When started, if no admin password in config.json, the app will prompt you to type a new admin password in the console.

Option B (env var):
$ export ENIST_ADMIN_PASSWORD="yourpassword"
$ export ENIST_FLASK_SECRET="change-this-too"
$ python app.py

## Optional (for maps/IP features)
- To enable Google geocoding / nicer maps set `google_maps_api_key` in Settings page or in config.json or env `ENIST_GOOGLE_MAPS_KEY`.
- To use IP geolocation, set `ip_geolocation_api` (e.g., ipinfo token) or export `ENIST_IPINFO_TOKEN`.

## Usage
- Open http://localhost:5000 in your browser
- Login with admin password
- Use Dashboard -> enter phone number, optionally IP (with owner consent)
- Generate logo via 'Generate Logo' (default text "TNEH")

## Notes (Ethics & Legal)
- This tool is educational and consent-based. Do NOT attempt to track people without explicit permission.
- Real-time covert tracking is illegal in many jurisdictions.
