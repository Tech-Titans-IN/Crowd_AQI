# 🌍 Crowd-AQI — Crowdsourced Air Quality Intelligence

A research-focused web application that combines official AQI data from the [World Air Quality Index (WAQI) API](https://aqicn.org/api/) with crowdsourced human observations to monitor hyper-local air quality conditions.

Built as a capstone project to explore whether physical symptoms reported by people correlate with officially measured air pollution levels.

---

## 🎯 Problem Statement

Official air quality monitoring stations are sparse and provide only city-level data, missing local pollution hotspots like construction zones, busy intersections, or industrial campuses. There is no easy way to track location-specific air quality based on real human experience.

## 💡 Solution

Crowd-AQI bridges this gap by letting users submit geo-tagged air quality observations — visibility, smell, and physical symptoms — and comparing them against official AQI readings fetched in real-time. A dynamic analytics dashboard visualises the correlation between official data and human perception.

---

## ✨ Key Features

### 🎨 Dynamic Theming Engine
The entire UI transforms based on the current AQI value:

| Theme | AQI Range | Vibe | Visual Effects |
|-------|-----------|------|----------------|
| **Good** | ≤ 70 | Fresh, calming | Forest green palette, clean background |
| **Moderate** | 71–150 | Smoggy, cautionary | Mustard/grey palette, drifting haze clouds |
| **Hazardous** | > 150 | Alarming, urgent | Crimson/black palette, pulsing red vignette |

### 📋 Smart Reporting Form
- **HTML5 Geolocation** — one-click coordinate capture
- **Custom range sliders** — for visibility and smell ratings (1–5) with real-time emoji feedback
- **Pill-shaped symptom toggles** — for coughing, eye irritation, headache, breathing difficulty, throat irritation
- **Live AQI preview** — fetched instantly after geolocation

### 📊 Analytics Dashboard
- Summary stat cards (total reports, avg AQI, top symptom, worst location)
- **Matplotlib-generated charts**: AQI vs symptom count, AQI vs user perception
- Scrollable reports table with colour-coded AQI badges

### 💬 Context-Aware Recommendations
Content dynamically changes based on air quality:
- **Good** → Outdoor activity suggestions (running, yoga, cycling)
- **Moderate** → Caution advice (wear masks, close windows)
- **Hazardous** → Strict warnings (stay indoors, use air purifiers)

---

## 🛠️ Technology Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python, Flask |
| **Database** | SQLite |
| **Frontend** | HTML5, CSS3 (Vanilla), JavaScript (Vanilla) |
| **API** | WAQI — World Air Quality Index |
| **Data Analysis** | Pandas, Matplotlib |
| **Design** | Glassmorphism, CSS Custom Properties, CSS Animations |

---
