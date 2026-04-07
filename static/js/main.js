/**
 * ═══════════════════════════════════════════════════════════════════
 *  main.js  —  Crowd-AQI Dynamic Theming Engine & Form Logic
 * ═══════════════════════════════════════════════════════════════════
 *
 *  This file handles ALL client-side interactivity:
 *
 *    §1  THEME ENGINE
 *        Reads the AQI value and changes the `data-theme` attribute
 *        on <body>, which triggers a complete UI palette swap via
 *        CSS Custom Properties.  Also swaps the recommendation
 *        panel content and AQI card display.
 *
 *    §2  GEOLOCATION
 *        Uses the browser's HTML5 Geolocation API to get lat/lon,
 *        fills hidden form fields, and triggers a live AQI fetch.
 *
 *    §3  SLIDER FEEDBACK
 *        Updates the emoji / text below each range slider in
 *        real-time as the user drags.
 *
 *    §4  SYMPTOM PILL LOGIC
 *        Handles the "No Symptoms" ↔ other symptom exclusivity.
 *
 *    §5  FORM SUBMISSION UX
 *        Shows a loading spinner and validates coordinates.
 *
 *    §6  MOBILE NAV & FLASH MESSAGES
 *        Hamburger toggle + auto-dismiss.
 *
 * ═══════════════════════════════════════════════════════════════════
 */


/* ─────────────────────────────────────────────────────────────────
   §1  DYNAMIC THEMING ENGINE
   ─────────────────────────────────────────────────────────────────
   HOW IT WORKS:
   1. Flask passes `window.CROWD_AQI_CONFIG.initialAqi` to the page.
   2. On DOMContentLoaded, we call `applyTheme(aqi)`.
   3. `applyTheme()` determines the theme string ("good", "moderate",
      or "hazardous") and sets it on <body data-theme="...">.
   4. CSS variables scoped to [data-theme="..."] instantly resolve
      to the new palette — and the 0.8s transition on body makes
      it a smooth fade.
   5. We also swap which recommendation panel is visible and update
      the AQI hero card colours/text.
   ───────────────────────────────────────────────────────────────── */

/**
 * applyTheme(aqiValue)
 * ────────────────────
 * The core function that drives the entire UI transformation.
 *
 * @param {number|null} aqiValue  – The AQI integer (0–500+), or null.
 *
 * Steps:
 *   1. Determine theme: "good" (≤70), "moderate" (71–150), "hazardous" (>150)
 *   2. Set body[data-theme] → triggers CSS variable swap
 *   3. Update AQI hero card value + category text
 *   4. Show the correct recommendation panel, hide the others
 *   5. Update the hero emoji to match the current air state
 */
function applyTheme(aqiValue) {
    // ── Step 1: Determine the theme ──────────────────────────────────
    let theme = "good";                 // Default to clean/calm
    let categoryText = "Good";

    if (aqiValue !== null && aqiValue !== undefined) {
        if (aqiValue <= 70) {
            theme = "good";
            categoryText = "Good";
        } else if (aqiValue <= 150) {
            theme = "moderate";
            categoryText = "Moderate";
        } else {
            theme = "hazardous";
            categoryText = "Hazardous";
        }
    } else {
        categoryText = "Awaiting Location";
    }

    // ── Step 2: Set the data-theme attribute on <body> ──────────────
    // This single line triggers the ENTIRE colour palette swap!
    // CSS selectors like [data-theme="moderate"] {...} now activate,
    // and all var(--xxx) references resolve to the new theme's values.
    document.body.dataset.theme = theme;

    // ── Step 3: Update the AQI hero card (if it exists on this page) ─
    const heroValue = document.getElementById("aqi-hero-value");
    const heroCat   = document.getElementById("aqi-hero-category");

    if (heroValue) {
        heroValue.textContent = (aqiValue !== null && aqiValue !== undefined)
            ? aqiValue
            : "--";
    }
    if (heroCat) {
        heroCat.textContent = categoryText;
    }

    // ── Step 4: Swap recommendation panels ──────────────────────────
    // We have three panels: #rec-good, #rec-moderate, #rec-hazardous.
    // We hide all of them, then show only the one matching the theme.
    const panels = {
        good:      document.getElementById("rec-good"),
        moderate:  document.getElementById("rec-moderate"),
        hazardous: document.getElementById("rec-hazardous"),
    };

    // Hide all panels first
    Object.values(panels).forEach(panel => {
        if (panel) panel.style.display = "none";
    });

    // Show the panel matching the current theme
    if (panels[theme]) {
        panels[theme].style.display = "block";
        // Re-trigger the entrance animation by briefly removing and
        // re-adding the animation class
        panels[theme].style.animation = "none";
        // Force a browser reflow (this "trick" restarts CSS animations)
        panels[theme].offsetHeight;  // eslint-disable-line no-unused-expressions
        panels[theme].style.animation = "";
    }

    // ── Step 5: Change the hero emoji ───────────────────────────────
    const heroEmoji = document.getElementById("hero-emoji");
    if (heroEmoji) {
        const emojiMap = {
            good:      "🌍",     // Healthy earth
            moderate:  "🌫️",     // Hazy
            hazardous: "🚨",     // Siren / alarm
        };
        heroEmoji.textContent = emojiMap[theme] || "🌍";
    }

    console.log(`🎨 Theme applied: "${theme}" (AQI: ${aqiValue})`);
}


/* ─────────────────────────────────────────────────────────────────
   §2  HTML5 GEOLOCATION
   ───────────────────────────────────────────────────────────────── */

/**
 * getLocation()
 * ─────────────
 * Called when the user clicks "Use My Location".
 *
 * Flow:
 *   1. navigator.geolocation.getCurrentPosition() prompts for GPS access.
 *   2. On success: fill hidden lat/lon fields + call fetchLiveAQI().
 *   3. On failure: show a helpful error message.
 *
 * This function is in the global scope so the onclick="" in HTML can reach it.
 */
function getLocation() {
    const geoBtn     = document.getElementById("geo-btn");
    const geoBtnText = document.getElementById("geo-btn-text");
    const geoStatus  = document.getElementById("geo-status");
    const latInput   = document.getElementById("latitude");
    const lonInput   = document.getElementById("longitude");

    // Check if the browser supports Geolocation at all
    if (!navigator.geolocation) {
        geoStatus.textContent = "⚠ Geolocation is not supported by your browser.";
        geoStatus.className   = "geo-status error";
        return;
    }

    // Show loading state
    geoBtnText.textContent = "Locating…";
    geoBtn.disabled = true;
    geoStatus.textContent = "";
    geoStatus.className   = "geo-status";

    navigator.geolocation.getCurrentPosition(
        // ── SUCCESS ──
        (position) => {
            const lat = position.coords.latitude;
            const lon = position.coords.longitude;

            // Fill the hidden form fields
            latInput.value = lat.toFixed(6);
            lonInput.value = lon.toFixed(6);

            // Update UI
            geoBtnText.textContent = "📍 Location Set";
            geoBtn.disabled = false;
            geoStatus.textContent = `Coordinates: ${lat.toFixed(4)}, ${lon.toFixed(4)}`;
            geoStatus.className   = "geo-status success";

            // Fetch live AQI and apply the dynamic theme
            fetchLiveAQI(lat, lon);
        },

        // ── ERROR ──
        (error) => {
            geoBtn.disabled = false;
            geoBtnText.textContent = "Use My Location";
            geoStatus.className    = "geo-status error";

            switch (error.code) {
                case error.PERMISSION_DENIED:
                    geoStatus.textContent = "⚠ Location permission denied. Allow access in browser settings.";
                    break;
                case error.POSITION_UNAVAILABLE:
                    geoStatus.textContent = "⚠ Location unavailable. Try again.";
                    break;
                case error.TIMEOUT:
                    geoStatus.textContent = "⚠ Location request timed out.";
                    break;
                default:
                    geoStatus.textContent = "⚠ An unknown error occurred.";
            }
        },

        // ── OPTIONS ──
        {
            enableHighAccuracy: true,     // Use GPS for better precision
            timeout: 15000,              // Fail after 15s
            maximumAge: 60000            // Accept cached position up to 1 min
        }
    );
}


/**
 * fetchLiveAQI(lat, lon)
 * ──────────────────────
 * After geolocation succeeds, call our Flask /api/aqi endpoint
 * to get the official AQI for these coordinates.
 *
 * When the response arrives, call applyTheme() to trigger the
 * full dynamic UI transformation.
 */
function fetchLiveAQI(lat, lon) {
    fetch(`/api/aqi?lat=${lat}&lon=${lon}`)
        .then(res => res.json())
        .then(data => {
            if (data.aqi !== null && data.aqi !== undefined) {
                // THIS IS THE MAGIC LINE: apply the theme based on live AQI!
                applyTheme(data.aqi);
            } else {
                // AQI unavailable — keep current theme but update card
                const heroValue = document.getElementById("aqi-hero-value");
                const heroCat   = document.getElementById("aqi-hero-category");
                if (heroValue) heroValue.textContent = "—";
                if (heroCat)   heroCat.textContent   = "AQI Unavailable";
            }
        })
        .catch(err => {
            console.warn("Failed to fetch live AQI:", err);
        });
}


/* ─────────────────────────────────────────────────────────────────
   §3  RANGE SLIDER FEEDBACK
   ─────────────────────────────────────────────────────────────────
   Each custom slider (<input type="range">) has a "feedback" area
   below it that shows an emoji + text label matching the current
   value.  We listen for the "input" event (fires as the user drags,
   not just on release) to update in real-time.
   ───────────────────────────────────────────────────────────────── */

/**
 * Lookup tables mapping slider values (1–5) to emoji + label.
 * These are used by the event listeners set up in initSliders().
 */
const VISIBILITY_LEVELS = {
    1: { emoji: "☀️",     text: "Crystal Clear" },
    2: { emoji: "🌤️",    text: "Slightly Hazy" },
    3: { emoji: "🌥️",    text: "Moderate Haze" },
    4: { emoji: "🌫️",    text: "Heavy Haze" },
    5: { emoji: "😶‍🌫️", text: "Dense / Can't See Far" },
};

const SMELL_LEVELS = {
    1: { emoji: "🍃",  text: "Fresh / No Smell" },
    2: { emoji: "🌿",  text: "Faint Odour" },
    3: { emoji: "💨",  text: "Noticeable" },
    4: { emoji: "🏭",  text: "Strong" },
    5: { emoji: "🤢",  text: "Severe / Unbearable" },
};

function initSliders() {
    /**
     * Helper: wires up a slider to its feedback elements.
     * @param {string} sliderId   – ID of the <input type="range">
     * @param {string} emojiId    – ID of the feedback emoji <span>
     * @param {string} textId     – ID of the feedback text <span>
     * @param {string} valueId    – ID of the "X / 5" value <span>
     * @param {object} levels     – Lookup table (e.g. VISIBILITY_LEVELS)
     */
    function wireSlider(sliderId, emojiId, textId, valueId, levels) {
        const slider = document.getElementById(sliderId);
        if (!slider) return;

        const emojiEl = document.getElementById(emojiId);
        const textEl  = document.getElementById(textId);
        const valueEl = document.getElementById(valueId);

        // The "input" event fires CONTINUOUSLY as the user drags
        // (unlike "change" which only fires on release).
        slider.addEventListener("input", () => {
            const val   = slider.value;
            const level = levels[val];

            if (emojiEl) emojiEl.textContent = level.emoji;
            if (textEl)  textEl.textContent  = level.text;
            if (valueEl) valueEl.textContent = `${val} / 5`;
        });
    }

    wireSlider("visibility-slider", "vis-emoji",   "vis-text",   "vis-value",   VISIBILITY_LEVELS);
    wireSlider("smell-slider",      "smell-emoji", "smell-text", "smell-value", SMELL_LEVELS);
}


/* ─────────────────────────────────────────────────────────────────
   §4  SYMPTOM PILL TOGGLE LOGIC
   ─────────────────────────────────────────────────────────────────
   Business rule:
   • If "No Symptoms" is checked → uncheck all real symptoms.
   • If any real symptom is checked → uncheck "No Symptoms".
   This ensures mutually exclusive selections.
   ───────────────────────────────────────────────────────────────── */
function initSymptomPills() {
    const noneCheckbox  = document.getElementById("no-symptoms-check");
    const allCheckboxes = document.querySelectorAll('.symptom-pill input[type="checkbox"]');

    allCheckboxes.forEach(cb => {
        cb.addEventListener("change", () => {
            if (cb === noneCheckbox && cb.checked) {
                // "No Symptoms" was just checked → uncheck all others
                allCheckboxes.forEach(other => {
                    if (other !== noneCheckbox) other.checked = false;
                });
            } else if (cb !== noneCheckbox && cb.checked) {
                // A real symptom was checked → uncheck "No Symptoms"
                if (noneCheckbox) noneCheckbox.checked = false;
            }
        });
    });
}


/* ─────────────────────────────────────────────────────────────────
   §5  FORM SUBMISSION UX
   ───────────────────────────────────────────────────────────────── */
function initFormSubmit() {
    const form = document.getElementById("report-form");
    if (!form) return;

    form.addEventListener("submit", (e) => {
        const submitBtn = document.getElementById("submit-btn");
        const btnText   = submitBtn.querySelector(".submit-btn-text");
        const btnLoader = submitBtn.querySelector(".submit-btn-loader");

        // Validate coordinates
        const lat = document.getElementById("latitude").value;
        const lon = document.getElementById("longitude").value;

        if (!lat || !lon) {
            e.preventDefault();
            alert("📍 Please click 'Use My Location' first so we can fetch AQI for your area.");
            return;
        }

        // Show loading spinner
        if (btnText)   btnText.style.display  = "none";
        if (btnLoader) btnLoader.style.display = "inline-flex";
        submitBtn.disabled = true;
    });
}


/* ─────────────────────────────────────────────────────────────────
   §6  MOBILE NAV TOGGLE & FLASH AUTO-DISMISS
   ───────────────────────────────────────────────────────────────── */
function initNavToggle() {
    const toggle = document.getElementById("nav-toggle");
    const links  = document.getElementById("nav-links");

    if (toggle && links) {
        toggle.addEventListener("click", () => {
            links.classList.toggle("open");
            toggle.classList.toggle("active");
        });
    }
}

function initFlashDismiss() {
    // Auto-dismiss flash messages after 6 seconds with a fade-out
    document.querySelectorAll(".flash-message").forEach(msg => {
        setTimeout(() => {
            msg.style.transition = "opacity 0.4s ease, transform 0.4s ease";
            msg.style.opacity    = "0";
            msg.style.transform  = "translateY(-10px)";
            setTimeout(() => msg.remove(), 400);
        }, 6000);
    });
}


/* ─────────────────────────────────────────────────────────────────
   INITIALISATION  —  DOMContentLoaded
   ─────────────────────────────────────────────────────────────────
   Everything kicks off here once the DOM is fully parsed.
   We check window.CROWD_AQI_CONFIG (set by Flask in base.html)
   and apply the initial theme immediately — no flash of wrong theme.
   ───────────────────────────────────────────────────────────────── */
document.addEventListener("DOMContentLoaded", () => {
    // Apply the initial theme from the Flask-rendered config
    const config = window.CROWD_AQI_CONFIG || {};
    applyTheme(config.initialAqi);

    // Initialise all interactive components
    initSliders();
    initSymptomPills();
    initFormSubmit();
    initNavToggle();
    initFlashDismiss();

    console.log("✅ Crowd-AQI frontend initialised");
});
