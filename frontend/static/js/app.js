(function () {
  "use strict";

  const API_BASE = ""; // same-origin; Flask serves both API and frontend
  const NEPAL_CENTER = [28.3949, 84.1240];

  const RISK_COLORS = {
    low: "#2e8b45",
    medium: "#e0a400",
    high: "#e2691a",
    very_high: "#d1373f",
  };
  const RISK_ORDER = { low: 0, medium: 1, high: 2, very_high: 3, unknown: -1 };
  const CONDITION_LABELS = {
    normal: "Normal / no change",
    rising_water: "Rising water level",
    new_cracks: "New cracks in dam/moraine",
    seepage: "Seepage / water leaking through dam",
    debris: "Debris / landslide near lake",
    other: "Other",
  };

  // ---------------- Map + basemaps ----------------
  // All three are free, keyless tile providers (no Google/Apple Maps key
  // required, no billing account needed). Streets/Terrain via CARTO & Esri,
  // Satellite via Esri World Imagery — a good fit for visualizing Himalayan
  // terrain around glacial lakes.
  const map = L.map("map", { zoomControl: true }).setView(NEPAL_CENTER, 7);

  const streets = L.tileLayer("https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png", {
    maxZoom: 19,
    subdomains: "abcd",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
  });

  const terrain = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 18,
    attribution: "Tiles &copy; Esri — Esri, DeLorme, NAVTEQ",
  });

  const satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    attribution: "Tiles &copy; Esri — Source: Esri, Maxar, Earthstar Geographics",
  });

  terrain.addTo(map);
  L.control.layers(
    { "Terrain": terrain, "Streets": streets, "Satellite": satellite },
    null,
    { position: "topright", collapsed: true }
  ).addTo(map);

  // Floating legend
  const legend = L.control({ position: "bottomleft" });
  legend.onAdd = function () {
    const div = L.DomUtil.create("div", "map-legend");
    div.innerHTML = `
      <div class="legend-title">Risk level</div>
      <div class="legend-item"><i class="dot low"></i>Low</div>
      <div class="legend-item"><i class="dot medium"></i>Medium</div>
      <div class="legend-item"><i class="dot high"></i>High</div>
      <div class="legend-item"><i class="dot very_high"></i>Very high</div>
    `;
    L.DomEvent.disableClickPropagation(div);
    return div;
  };
  legend.addTo(map);

  const clusterGroup = L.markerClusterGroup({
    maxClusterRadius: 45,
    iconCreateFunction: function (cluster) {
      const markers = cluster.getAllChildMarkers();
      const worst = markers.reduce(
        (acc, m) => (RISK_ORDER[m.options.riskLevel] > RISK_ORDER[acc] ? m.options.riskLevel : acc),
        "low"
      );
      return L.divIcon({
        html: `<div class="cluster-icon" style="background:${RISK_COLORS[worst] || "#888"}">${cluster.getChildCount()}</div>`,
        className: "cluster-wrapper",
        iconSize: L.point(38, 38),
      });
    },
  });
  map.addLayer(clusterGroup);

  let searchMarker = null;
  let allLakes = []; // cache of GeoJSON features, used to populate the report-modal lake picker

  function riskColor(level) {
    return RISK_COLORS[level] || "#888";
  }

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  function makeLakeMarker(feature) {
    const [lon, lat] = feature.geometry.coordinates;
    const p = feature.properties;
    const level = p.risk_level || "unknown";
    const marker = L.circleMarker([lat, lon], {
      radius: 9,
      color: "#fff",
      weight: 2,
      fillColor: riskColor(level),
      fillOpacity: 0.92,
      riskLevel: level,
    });
    marker.bindPopup(popupHtml(p));
    marker.on("popupopen", () => {
      const btn = document.getElementById(`open-panel-${p.id}`);
      if (btn) btn.addEventListener("click", () => openLakePanel(p.id));
    });
    return marker;
  }

  function popupHtml(p) {
    const scoreText = p.risk_score != null ? `${p.risk_score.toFixed(1)} / 100` : "not yet computed";
    const levelLabel = (p.risk_level || "unknown").replace("_", " ");
    return `
      <div class="popup-title">${escapeHtml(p.name)}</div>
      <div>${escapeHtml(p.district || "")}${p.district ? ", " : ""}${escapeHtml(p.basin || "")}</div>
      <div class="popup-risk" style="color:${riskColor(p.risk_level)}">Risk: ${scoreText} (${levelLabel})</div>
      <div>Dam: ${escapeHtml(p.dam_type)} · Area: ${p.area_km2 != null ? p.area_km2 + " km²" : "n/a"}</div>
      <span class="popup-link" id="open-panel-${p.id}">View details &amp; report →</span>
    `;
  }

  async function loadLakes() {
    const resp = await fetch(`${API_BASE}/api/lakes`);
    const geojson = await resp.json();
    allLakes = geojson.features;
    clusterGroup.clearLayers();
    allLakes.forEach((f) => clusterGroup.addLayer(makeLakeMarker(f)));
    renderStatsBar(allLakes);
  }

  function renderStatsBar(features) {
    const bar = document.getElementById("stats-bar");
    const total = features.length;
    const counts = { low: 0, medium: 0, high: 0, very_high: 0, unknown: 0 };
    features.forEach((f) => {
      const lvl = f.properties.risk_level || "unknown";
      counts[lvl] = (counts[lvl] || 0) + 1;
    });
    const elevated = counts.high + counts.very_high;
    bar.innerHTML = `
      <span><strong>${total}</strong> glacial lakes monitored</span>
      <span><span class="stat-dot" style="background:${RISK_COLORS.very_high}"></span><strong>${elevated}</strong> at high or very high risk</span>
      <span><span class="stat-dot" style="background:${RISK_COLORS.low}"></span><strong>${counts.low}</strong> low risk</span>
    `;
  }

  // ---------------- Search ----------------
  const searchForm = document.getElementById("search-form");
  const searchInput = document.getElementById("search-input");

  searchForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const q = searchInput.value.trim();
    if (!q) return;
    try {
      const resp = await fetch(
        `https://nominatim.openstreetmap.org/search?format=json&limit=1&countrycodes=np&q=${encodeURIComponent(q)}`,
        { headers: { Accept: "application/json" } }
      );
      const results = await resp.json();
      if (!results.length) {
        showToast(`No location found in Nepal for "${q}"`);
        return;
      }
      const { lat, lon, display_name } = results[0];
      focusLocation(parseFloat(lat), parseFloat(lon), display_name);
    } catch (err) {
      showToast("Search failed — network or geocoding service unavailable.");
    }
  });

  async function focusLocation(lat, lon, label) {
    map.setView([lat, lon], 10);
    if (searchMarker) map.removeLayer(searchMarker);
    searchMarker = L.marker([lat, lon], {
      icon: L.divIcon({ className: "search-pin", html: "📍", iconSize: [24, 24] }),
    }).addTo(map);
    if (label) searchMarker.bindPopup(escapeHtml(label)).openPopup();

    try {
      const resp = await fetch(`${API_BASE}/api/lakes/search?lat=${lat}&lon=${lon}&radius_km=75`);
      const geojson = await resp.json();
      showToast(
        geojson.features.length
          ? `${geojson.features.length} glacial lake(s) within 75km`
          : "No glacial lakes within 75km of this location"
      );
    } catch (err) {
      // non-fatal; map recentring already happened
    }
  }

  // ---------------- Side panel: lake detail ----------------
  const sidePanel = document.getElementById("side-panel");
  const panelContent = document.getElementById("panel-content");
  document.getElementById("close-panel").addEventListener("click", () => sidePanel.classList.add("hidden"));

  async function openLakePanel(lakeId) {
    map.closePopup();
    sidePanel.classList.remove("hidden");
    panelContent.innerHTML = "<p>Loading…</p>";
    try {
      const resp = await fetch(`${API_BASE}/api/lakes/${lakeId}`);
      if (!resp.ok) throw new Error("failed to load lake");
      const data = await resp.json();
      renderLakePanel(data);
    } catch (err) {
      panelContent.innerHTML = `<p>Could not load lake details.</p>`;
    }
  }

  function gaugeHtml(normalized0to1, size = "big") {
    const pct = Math.max(0, Math.min(100, normalized0to1 * 100));
    const trackClass = size === "big" ? "gauge-track" : "factor-gauge-track";
    const thumbClass = size === "big" ? "gauge-thumb" : "factor-gauge-thumb";
    return `<div class="${trackClass}"><div class="${thumbClass}" style="left:${pct}%"></div></div>`;
  }

  function factorRow(name, factor) {
    return `
      <div class="factor-row">
        <div class="factor-label">
          <span class="fname">${name.replace(/_/g, " ")}</span>
          <span class="fval">${factor.contribution_points.toFixed(1)} / ${factor.weight_pct} pts</span>
        </div>
        ${gaugeHtml(factor.normalized_0_1, "small")}
      </div>
    `;
  }

  function renderLakePanel(data) {
    const { lake, risk, reports } = data;
    const level = risk ? risk.level : "unknown";
    const scoreText = risk ? risk.score.toFixed(1) : "—";
    const scoreNormalized = risk ? risk.score / 100 : 0;

    let factorsHtml = "";
    let provenanceHtml = "";
    if (risk && risk.breakdown) {
      factorsHtml = Object.entries(risk.breakdown.factors)
        .map(([name, factor]) => factorRow(name, factor))
        .join("");

      const raw = risk.breakdown.raw_inputs || {};
      const sourceTag = (label, source, liveLabel, fallbackLabel) => {
        const ok = source && !source.startsWith("mock") && source !== "error";
        return `${label}: <span class="${ok ? "live-tag" : "mock-tag"}">${ok ? liveLabel : fallbackLabel}</span>`;
      };
      provenanceHtml = `
        <div class="data-provenance">
          ${sourceTag("Lake-area trend", raw.area_change?.source, "live Sentinel-2 (Copernicus Data Space Ecosystem)", "inventory-derived estimate — no live Sentinel-2 credentials configured")}<br>
          ${sourceTag("Seismicity", raw.seismicity?.source, "live USGS earthquake catalog", "unavailable right now — neutral default used")}<br>
          ${sourceTag("Climate", raw.climate?.source, "live Open-Meteo", "unavailable right now — neutral default used")}
        </div>
      `;
    }

    const reportsHtml = reports.length
      ? reports
          .map(
            (r) => `
        <div class="report-item">
          <div class="meta">${escapeHtml(r.reporter_name || "Anonymous")} · ${new Date(r.created_at).toLocaleDateString()} · <span class="status-${r.status}">${r.status}</span></div>
          <div><strong>${escapeHtml(CONDITION_LABELS[r.condition] || r.condition)}</strong> (severity ${r.severity}/5)</div>
          ${r.description ? `<div>${escapeHtml(r.description)}</div>` : ""}
        </div>`
          )
          .join("")
      : `<p class="empty-note">No community reports yet — be the first to report on this lake.</p>`;

    panelContent.innerHTML = `
      <h2 class="panel-title">${escapeHtml(lake.name)}</h2>
      <p class="panel-sub">${escapeHtml(lake.district || "")}${lake.district ? ", " : ""}${escapeHtml(lake.basin || "")} basin · ${lake.elevation_m || "?"} m elevation</p>

      <div class="risk-summary">
        <div class="risk-summary-top">
          <span class="risk-score-value">${scoreText}<span style="font-size:14px;color:var(--muted);font-weight:600"> / 100</span></span>
          <span class="risk-level-tag ${level}">${level.replace("_", " ")}</span>
        </div>
        ${gaugeHtml(scoreNormalized, "big")}
        <div class="gauge-scale"><span>Low</span><span>Medium</span><span>High</span><span>Very high</span></div>
      </div>

      <dl class="attr-grid">
        <dt>Area (current)</dt><dd>${lake.area_km2 != null ? lake.area_km2 + " km²" : "n/a"}</dd>
        <dt>Area (1990 baseline)</dt><dd>${lake.area_1990_km2 != null ? lake.area_1990_km2 + " km²" : "n/a"}</dd>
        <dt>Dam type</dt><dd style="text-transform:capitalize">${escapeHtml(lake.dam_type)}</dd>
        <dt>Slope</dt><dd>${lake.slope_deg != null ? lake.slope_deg + "°" : "n/a"}</dd>
      </dl>

      <div class="section-title">Risk breakdown</div>
      ${factorsHtml || "<p class='empty-note'>Risk not yet computed for this lake.</p>"}
      ${provenanceHtml}

      <div class="section-title">Community reports (${reports.length})</div>
      ${reportsHtml}

      <button class="panel-report-btn" id="panel-report-btn">Submit a report for this lake</button>
    `;

    document.getElementById("panel-report-btn").addEventListener("click", () => openReportModal(lake.id));
  }

  // ---------------- Report form (shared: modal + panel button routes here) ----------------
  const modalBackdrop = document.getElementById("modal-backdrop");
  const modalContent = document.getElementById("modal-content");
  document.getElementById("close-modal").addEventListener("click", closeReportModal);
  modalBackdrop.addEventListener("click", (e) => {
    if (e.target === modalBackdrop) closeReportModal();
  });
  document.getElementById("open-report-modal").addEventListener("click", () => openReportModal(null));

  function closeReportModal() {
    modalBackdrop.classList.add("hidden");
    modalContent.innerHTML = "";
  }

  function openReportModal(presetLakeId) {
    const lakeOptions = allLakes
      .slice()
      .sort((a, b) => a.properties.name.localeCompare(b.properties.name))
      .map(
        (f) =>
          `<option value="${f.properties.id}" ${presetLakeId === f.properties.id ? "selected" : ""}>${escapeHtml(f.properties.name)}</option>`
      )
      .join("");

    modalContent.innerHTML = `
      <h2>Submit a report</h2>
      <p class="modal-sub">Tell us what you're observing at a glacial lake. Reports are moderated before they affect a lake's risk score.</p>
      <form class="report-form" id="report-form">
        <label>
          Which lake?
          <select name="lake_id" required>
            <option value="">Select a lake…</option>
            ${lakeOptions}
          </select>
        </label>
        <label>
          Your name (optional)
          <input type="text" name="reporter_name" maxlength="100" placeholder="Anonymous">
        </label>
        <label>
          Condition observed
          <select name="condition" required>
            <option value="">Select…</option>
            <option value="normal">Normal / no change</option>
            <option value="rising_water">Rising water level</option>
            <option value="new_cracks">New cracks in dam/moraine</option>
            <option value="seepage">Seepage / water leaking through dam</option>
            <option value="debris">Debris / landslide near lake</option>
            <option value="other">Other</option>
          </select>
        </label>
        <label>
          Severity: <span class="severity-value" id="severity-out">2</span> / 5
          <input type="range" name="severity" min="1" max="5" value="2" oninput="document.getElementById('severity-out').textContent=this.value">
        </label>
        <label>
          Details
          <textarea name="description" rows="3" maxlength="4000" placeholder="What did you observe?"></textarea>
        </label>
        <label class="honeypot" aria-hidden="true">
          Website
          <input type="text" name="website" tabindex="-1" autocomplete="off">
        </label>
        <button type="submit">Submit report</button>
        <p class="form-note">Spam and duplicate submissions are filtered automatically before a human reviews reports.</p>
      </form>
    `;
    modalBackdrop.classList.remove("hidden");
    document.getElementById("report-form").addEventListener("submit", submitReport);
  }

  async function submitReport(e) {
    e.preventDefault();
    const form = e.target;
    const fd = new FormData(form);
    const lakeId = fd.get("lake_id");
    if (!lakeId) {
      showToast("Please select a lake.");
      return;
    }
    const payload = {
      reporter_name: fd.get("reporter_name"),
      condition: fd.get("condition"),
      severity: fd.get("severity"),
      description: fd.get("description"),
      website: fd.get("website"), // honeypot
    };
    const submitBtn = form.querySelector("button[type=submit]");
    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting…";
    try {
      const resp = await fetch(`${API_BASE}/api/lakes/${lakeId}/reports`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const result = await resp.json();
      if (!resp.ok) {
        showToast(result.error || "Could not submit report.");
        submitBtn.disabled = false;
        submitBtn.textContent = "Submit report";
        return;
      }
      showToast(result.message);
      closeReportModal();
      if (!sidePanel.classList.contains("hidden")) {
        openLakePanel(parseInt(lakeId, 10)); // refresh panel if it's showing this lake
      }
    } catch (err) {
      showToast("Network error submitting report.");
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit report";
    }
  }

  // ---------------- Toast ----------------
  let toastTimer = null;
  function showToast(msg) {
    const toast = document.getElementById("toast");
    toast.textContent = msg;
    toast.classList.remove("hidden");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.add("hidden"), 4000);
  }

  loadLakes().catch(() => showToast("Could not load lake data from the server."));
})();
