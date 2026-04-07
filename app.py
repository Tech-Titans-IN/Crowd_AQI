"""
==========================================================================
 Crowd-AQI  —  Crowdsourced Air Quality Intelligence
 --------------------------------------------------------------------------
 A Flask web application that combines official AQI data from the
 World Air Quality Index (WAQI) API with crowdsourced user observations
 to monitor hyper-local air quality conditions.

 Main components in this file:
   1. Database initialisation   (SQLite via Python's built-in sqlite3)
   2. WAQI API helper           (fetches official AQI for a location)
   3. Chart generation          (Pandas + Matplotlib → static PNG images)
   4. Flask routes              (home / submit / dashboard)
==========================================================================
"""

# ── Standard library imports ─────────────────────────────────────────────
import os
import json
import sqlite3
from datetime import datetime

# ── Third-party imports ──────────────────────────────────────────────────
from flask import (
    Flask, render_template, request, redirect,
    url_for, flash, jsonify, g
)
import requests                # HTTP client for the WAQI API
import pandas as pd            # Data manipulation for analysis
import matplotlib              # Plotting library
matplotlib.use("Agg")         # Use non-interactive backend (no GUI needed)
import matplotlib.pyplot as plt
from dotenv import load_dotenv # Reads .env file into environment variables

# ── Load environment variables from .env (if it exists) ──────────────────
load_dotenv()

# ── Flask application factory ────────────────────────────────────────────
app = Flask(__name__)

# SECRET_KEY is required by Flask for session-based flash messages.
# In production you'd set this to a long random string via an env var.
app.secret_key = os.environ.get("SECRET_KEY", "crowd-aqi-dev-key-change-me")

# ── Configuration ────────────────────────────────────────────────────────
# WAQI API: The World Air Quality Index project provides a free JSON API.
# Get your own token at https://aqicn.org/data-platform/token/
# The user supplied a demo token — works but is rate-limited.
WAQI_API_TOKEN = os.environ.get("WAQI_API_TOKEN", "demo")

# Path to the SQLite database file.  Stored alongside app.py for simplicity.
DATABASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crowd_aqi.db")

# Directory where Matplotlib saves chart images.
PLOTS_DIR = os.path.join(app.static_folder, "plots")
os.makedirs(PLOTS_DIR, exist_ok=True)  # Create on startup if missing


# =========================================================================
#  1. DATABASE  —  helpers for SQLite connection & schema creation
# =========================================================================

def get_db():
    """
    Return a database connection stored on Flask's special `g` object.
    ---------------------------------------------------------------
    Flask's `g` is a per-request global namespace.  By attaching the
    connection to `g`, we reuse the same connection for the entire
    request lifecycle and close it automatically when the request ends.
    """
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        # Return rows as sqlite3.Row objects so we can access columns by name
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    """
    Automatically close the database connection when the app context
    (i.e. the request) is torn down.  This prevents connection leaks.
    """
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """
    Create the `user_reports` table if it doesn't already exist.
    ---------------------------------------------------------------
    Fields overview:
      id               – auto-incrementing primary key
      timestamp         – ISO-8601 string of when the report was filed
      location_name     – human-readable place name (e.g. "Campus Gate 3")
      latitude/longitude – GPS coordinates (from HTML5 Geolocation API)
      official_aqi      – integer AQI fetched from the WAQI API at submit time
      visibility_rating – user's subjective rating 1–5  (1=Clear, 5=Dense Haze)
      smell_rating      – user's subjective rating 1–5  (1=No Smell, 5=Severe)
      symptoms          – JSON-encoded list of symptom strings the user checked
    """
    db = sqlite3.connect(DATABASE)
    db.execute("""
        CREATE TABLE IF NOT EXISTS user_reports (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp         TEXT    NOT NULL,
            location_name     TEXT    NOT NULL,
            latitude          REAL    NOT NULL,
            longitude         REAL    NOT NULL,
            official_aqi      INTEGER,
            visibility_rating INTEGER NOT NULL CHECK(visibility_rating BETWEEN 1 AND 5),
            smell_rating      INTEGER NOT NULL CHECK(smell_rating      BETWEEN 1 AND 5),
            symptoms          TEXT    NOT NULL DEFAULT '[]'
        )
    """)
    db.commit()
    db.close()
    print("✅  Database initialised — user_reports table ready.")


# =========================================================================
#  2. WAQI API  —  fetch official Air Quality Index for a location
# =========================================================================

def fetch_aqi_by_coords(lat, lon):
    """
    Query the WAQI API using geographic coordinates.
    Returns the AQI integer, or None on failure.
    ---------------------------------------------------------------
    API endpoint:  /feed/geo:{lat};{lng}/?token=...
    Response JSON:
      { "status": "ok", "data": { "aqi": 58, ... } }
    The AQI value follows the US EPA scale (0–500).
    """
    try:
        url = f"http://api.waqi.info/feed/geo:{lat};{lon}/?token={WAQI_API_TOKEN}"
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("status") == "ok":
            aqi_value = data["data"]["aqi"]
            # The API sometimes returns "-" when data is unavailable
            return int(aqi_value) if str(aqi_value).lstrip("-").isdigit() else None
        else:
            print(f"⚠  WAQI API error: {data.get('data', 'Unknown error')}")
            return None
    except Exception as e:
        print(f"⚠  Failed to fetch AQI: {e}")
        return None


def fetch_aqi_by_city(city_name):
    """
    Query the WAQI API using a city/station name.
    Returns the AQI integer, or None on failure.
    ---------------------------------------------------------------
    API endpoint:  /feed/{city}/?token=...
    """
    try:
        url = f"http://api.waqi.info/feed/{city_name}/?token={WAQI_API_TOKEN}"
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("status") == "ok":
            aqi_value = data["data"]["aqi"]
            return int(aqi_value) if str(aqi_value).lstrip("-").isdigit() else None
        else:
            return None
    except Exception as e:
        print(f"⚠  Failed to fetch AQI by city: {e}")
        return None


def get_aqi_category(aqi):
    """
    Convert a numeric AQI value to a human-readable category and
    a CSS-friendly colour class.
    ---------------------------------------------------------------
    Categories follow the US EPA breakpoints:
      0– 50  Good           (green)
      51–100 Moderate        (yellow)
     101–150 Unhealthy (SG)  (orange)        SG = Sensitive Groups
     151–200 Unhealthy       (red)
     201–300 Very Unhealthy  (purple)
     301+    Hazardous       (maroon)
    """
    if aqi is None:
        return "Unknown", "unknown"
    if aqi <= 50:
        return "Good", "good"
    if aqi <= 100:
        return "Moderate", "moderate"
    if aqi <= 150:
        return "Unhealthy for Sensitive Groups", "unhealthy-sg"
    if aqi <= 200:
        return "Unhealthy", "unhealthy"
    if aqi <= 300:
        return "Very Unhealthy", "very-unhealthy"
    return "Hazardous", "hazardous"


def get_theme_from_aqi(aqi):
    """
    Map an AQI integer to one of three UI theme names used by the
    frontend's Dynamic Theming Engine.
    ---------------------------------------------------------------
    The frontend uses a `data-theme` attribute on <body> that
    activates a completely different colour palette via CSS Variables.

    Thresholds (matching the user's specification):
      AQI ≤  70  →  "good"       (fresh, forest greens)
      AQI 71–150  →  "moderate"   (smoggy, mustard haze)
      AQI > 150   →  "hazardous"  (alarming reds / crimson)
    """
    if aqi is None:
        return "good"           # Default to the clean theme
    if aqi <= 70:
        return "good"
    if aqi <= 150:
        return "moderate"
    return "hazardous"


# =========================================================================
#  3. CHART GENERATION  —  Pandas + Matplotlib analysis
# =========================================================================

def generate_charts():
    """
    Read all reports from the database, build a Pandas DataFrame,
    and produce two analytical charts saved as PNG images.
    ---------------------------------------------------------------
    Chart 1 — "AQI vs Average Symptom Count"
        Groups reports by AQI category and shows the mean number of
        symptoms users reported.  Reveals whether higher AQI correlates
        with more physical discomfort.

    Chart 2 — "AQI vs User Perception"
        Scatter plot overlaying visibility_rating and smell_rating
        against the official AQI.  Shows how well human perception
        tracks the instrument-measured air quality.
    """
    db = sqlite3.connect(DATABASE)
    # pd.read_sql_query loads a SQL result straight into a DataFrame — very handy!
    df = pd.read_sql_query("SELECT * FROM user_reports", db)
    db.close()

    if df.empty:
        return  # Nothing to plot yet

    # ── Prepare derived columns ──────────────────────────────────────────
    # Count how many symptoms each user checked (stored as JSON list)
    df["symptom_count"] = df["symptoms"].apply(
        lambda s: len(json.loads(s)) if s else 0
    )

    # Assign an AQI category label to every row
    df["aqi_category"] = df["official_aqi"].apply(
        lambda x: get_aqi_category(x)[0]
    )

    # ── Chart styling ────────────────────────────────────────────────────
    # Use a dark background to match the app's dark theme
    plt.style.use("dark_background")

    # Colour palette matching AQI categories
    category_colours = {
        "Good": "#2ecc71",
        "Moderate": "#f1c40f",
        "Unhealthy for Sensitive Groups": "#e67e22",
        "Unhealthy": "#e74c3c",
        "Very Unhealthy": "#9b59b6",
        "Hazardous": "#8b0000",
        "Unknown": "#7f8c8d",
    }

    # Desired display order (from best to worst air quality)
    cat_order = [
        "Good", "Moderate", "Unhealthy for Sensitive Groups",
        "Unhealthy", "Very Unhealthy", "Hazardous",
    ]

    # ── CHART 1: AQI Category vs Average Symptom Count ──────────────────
    fig1, ax1 = plt.subplots(figsize=(10, 5))
    fig1.patch.set_facecolor("#0f1923")
    ax1.set_facecolor("#0f1923")

    grouped = df.groupby("aqi_category")["symptom_count"].mean()
    # Reindex so bars appear in severity order (missing categories dropped)
    grouped = grouped.reindex([c for c in cat_order if c in grouped.index])

    if not grouped.empty:
        colours = [category_colours.get(c, "#7f8c8d") for c in grouped.index]
        bars = ax1.bar(grouped.index, grouped.values, color=colours,
                       edgecolor="white", linewidth=0.5, width=0.6)

        # Add value labels on top of each bar
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width() / 2., height + 0.05,
                     f"{height:.1f}", ha="center", va="bottom",
                     fontweight="bold", fontsize=11, color="white")

    ax1.set_title("Official AQI Category vs Avg. Reported Symptoms",
                  fontsize=14, fontweight="bold", color="#00e5ff", pad=15)
    ax1.set_xlabel("AQI Category", fontsize=11, color="#b0bec5")
    ax1.set_ylabel("Avg. Symptom Count", fontsize=11, color="#b0bec5")
    ax1.tick_params(colors="#b0bec5", labelsize=9)
    plt.xticks(rotation=25, ha="right")
    plt.tight_layout()
    fig1.savefig(os.path.join(PLOTS_DIR, "aqi_vs_symptoms.png"), dpi=150)
    plt.close(fig1)

    # ── CHART 2: AQI vs User Perception (Visibility & Smell) ────────────
    # Only plot if we have valid AQI values
    valid = df.dropna(subset=["official_aqi"])
    if not valid.empty:
        fig2, ax2 = plt.subplots(figsize=(10, 5))
        fig2.patch.set_facecolor("#0f1923")
        ax2.set_facecolor("#0f1923")

        ax2.scatter(valid["official_aqi"], valid["visibility_rating"],
                    c="#00e5ff", alpha=0.7, s=80, label="Visibility Rating",
                    edgecolors="white", linewidths=0.5)
        ax2.scatter(valid["official_aqi"], valid["smell_rating"],
                    c="#ff6f61", alpha=0.7, s=80, label="Smell Rating",
                    edgecolors="white", linewidths=0.5, marker="D")

        ax2.set_title("Official AQI vs User Perception Ratings",
                      fontsize=14, fontweight="bold", color="#00e5ff", pad=15)
        ax2.set_xlabel("Official AQI", fontsize=11, color="#b0bec5")
        ax2.set_ylabel("User Rating (1–5)", fontsize=11, color="#b0bec5")
        ax2.set_yticks([1, 2, 3, 4, 5])
        ax2.legend(facecolor="#1a2a3a", edgecolor="#00e5ff",
                   fontsize=10, labelcolor="white")
        ax2.tick_params(colors="#b0bec5")
        plt.tight_layout()
        fig2.savefig(os.path.join(PLOTS_DIR, "aqi_vs_perception.png"), dpi=150)
        plt.close(fig2)

    print("📊  Charts generated in static/plots/")


# =========================================================================
#  4. FLASK ROUTES  —  pages & form handling
# =========================================================================

@app.route("/")
def index():
    """
    Render the home / report-submission page.
    ---------------------------------------------------------------
    We look up the most recently submitted AQI in the database so
    the page can render with the correct theme *immediately* (before
    any geolocation happens).  If there's nothing in the DB yet, we
    default to theme="good".
    """
    # Grab the latest AQI from the database (if any reports exist)
    latest_aqi = None
    try:
        db = get_db()
        row = db.execute(
            "SELECT official_aqi FROM user_reports "
            "WHERE official_aqi IS NOT NULL "
            "ORDER BY timestamp DESC LIMIT 1"
        ).fetchone()
        if row:
            latest_aqi = row["official_aqi"]
    except Exception:
        pass  # DB may not exist on very first run

    return render_template(
        "index.html",
        waqi_token=WAQI_API_TOKEN,
        initial_aqi=latest_aqi,                       # Integer or None
        initial_theme=get_theme_from_aqi(latest_aqi),  # "good" | "moderate" | "hazardous"
    )


@app.route("/submit", methods=["POST"])
def submit_report():
    """
    Handle the report form submission.
    ---------------------------------------------------------------
    Steps:
      1. Read all form fields from the POST data.
      2. Fetch the official AQI from WAQI for the given coordinates.
      3. Insert the report into the SQLite database.
      4. Flash a success message and redirect back to the home page.
    """
    # ── 1. Extract form data ─────────────────────────────────────────────
    location_name     = request.form.get("location_name", "").strip()
    latitude          = request.form.get("latitude", "")
    longitude         = request.form.get("longitude", "")
    visibility_rating = request.form.get("visibility_rating", "3")
    smell_rating      = request.form.get("smell_rating", "3")

    # Symptoms arrive as a list of checked checkbox values
    # e.g. ["coughing", "eye_irritation"]
    symptoms = request.form.getlist("symptoms")

    # ── Basic validation ─────────────────────────────────────────────────
    if not location_name or not latitude or not longitude:
        flash("Please provide a location name and allow geolocation.", "error")
        return redirect(url_for("index"))

    try:
        lat = float(latitude)
        lon = float(longitude)
    except ValueError:
        flash("Invalid coordinates. Please try again.", "error")
        return redirect(url_for("index"))

    # ── 2. Fetch official AQI ────────────────────────────────────────────
    official_aqi = fetch_aqi_by_coords(lat, lon)

    # ── 3. Insert into database ──────────────────────────────────────────
    db = get_db()
    db.execute(
        """INSERT INTO user_reports
           (timestamp, location_name, latitude, longitude,
            official_aqi, visibility_rating, smell_rating, symptoms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            datetime.now().isoformat(),        # ISO timestamp
            location_name,
            lat,
            lon,
            official_aqi,                       # May be None if API failed
            int(visibility_rating),
            int(smell_rating),
            json.dumps(symptoms),               # Store symptoms as JSON text
        ),
    )
    db.commit()

    # ── 4. Feedback & redirect ───────────────────────────────────────────
    aqi_msg = f"Official AQI: {official_aqi}" if official_aqi else "AQI data unavailable"
    flash(f"✅ Report submitted successfully!  {aqi_msg}", "success")
    return redirect(url_for("index"))


@app.route("/dashboard")
def dashboard():
    """
    Render the analytics dashboard.
    ---------------------------------------------------------------
    1. Query all reports from the DB.
    2. Compute summary statistics.
    3. Generate Matplotlib charts.
    4. Pass everything to the dashboard template.
    """
    db = get_db()
    reports = db.execute(
        "SELECT * FROM user_reports ORDER BY timestamp DESC"
    ).fetchall()

    # ── Summary statistics ───────────────────────────────────────────────
    total_reports = len(reports)
    avg_aqi = None
    most_common_symptom = "N/A"
    worst_location = "N/A"

    if total_reports > 0:
        # Average AQI (only from reports where API returned a value)
        valid_aqis = [r["official_aqi"] for r in reports if r["official_aqi"]]
        avg_aqi = round(sum(valid_aqis) / len(valid_aqis)) if valid_aqis else None

        # Most frequently reported symptom across all reports
        all_symptoms = []
        for r in reports:
            all_symptoms.extend(json.loads(r["symptoms"]))
        if all_symptoms:
            # Count occurrences and find the max
            from collections import Counter
            symptom_counts = Counter(all_symptoms)
            most_common_symptom = symptom_counts.most_common(1)[0][0].replace("_", " ").title()

        # Location with the highest average visibility+smell rating (worst air)
        location_scores = {}
        for r in reports:
            loc = r["location_name"]
            score = r["visibility_rating"] + r["smell_rating"]
            location_scores.setdefault(loc, []).append(score)
        if location_scores:
            worst_location = max(
                location_scores,
                key=lambda loc: sum(location_scores[loc]) / len(location_scores[loc])
            )

    # ── Generate charts ──────────────────────────────────────────────────
    generate_charts()

    # ── Check which chart files exist (so template can conditionally show them)
    chart1_exists = os.path.exists(os.path.join(PLOTS_DIR, "aqi_vs_symptoms.png"))
    chart2_exists = os.path.exists(os.path.join(PLOTS_DIR, "aqi_vs_perception.png"))

    # ── Enrich reports with AQI category for table display ───────────────
    enriched_reports = []
    for r in reports:
        report_dict = dict(r)
        cat_label, cat_class = get_aqi_category(r["official_aqi"])
        report_dict["aqi_category"] = cat_label
        report_dict["aqi_class"] = cat_class
        report_dict["symptoms_list"] = json.loads(r["symptoms"])
        enriched_reports.append(report_dict)

    return render_template(
        "dashboard.html",
        reports=enriched_reports,
        total_reports=total_reports,
        avg_aqi=avg_aqi,
        avg_aqi_category=get_aqi_category(avg_aqi)[0] if avg_aqi else "N/A",
        avg_aqi_class=get_aqi_category(avg_aqi)[1] if avg_aqi else "unknown",
        most_common_symptom=most_common_symptom,
        worst_location=worst_location,
        chart1_exists=chart1_exists,
        chart2_exists=chart2_exists,
        # Pass the theme so the dashboard also adapts its colours
        initial_aqi=avg_aqi,
        initial_theme=get_theme_from_aqi(avg_aqi),
    )


@app.route("/api/aqi")
def api_aqi():
    """
    A small JSON API endpoint so the frontend can preview AQI
    without a full form submission.
    ---------------------------------------------------------------
    Query params:  ?lat=...&lon=...   OR   ?city=...
    Returns:       { "aqi": 58, "category": "Moderate", "class": "moderate" }
    """
    lat = request.args.get("lat")
    lon = request.args.get("lon")
    city = request.args.get("city")

    if lat and lon:
        aqi = fetch_aqi_by_coords(float(lat), float(lon))
    elif city:
        aqi = fetch_aqi_by_city(city)
    else:
        return jsonify({"error": "Provide lat/lon or city"}), 400

    cat_label, cat_class = get_aqi_category(aqi)
    return jsonify({"aqi": aqi, "category": cat_label, "class": cat_class})


# =========================================================================
#  5. APPLICATION ENTRY POINT
# =========================================================================

if __name__ == "__main__":
    # Ensure the database table exists before serving requests
    init_db()

    # debug=True gives auto-reload on code changes & helpful error pages.
    # In production you'd use a proper WSGI server (gunicorn, waitress).
    print("🚀  Crowd-AQI running at http://127.0.0.1:5000")
    app.run(debug=True, port=5000)
