async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

let modalState = {
  nodeId: null,
  nodeLabel: "",
  start: null,
  end: null
};
let gaugeSettings = {
  tempMin: -10,
  tempMax: 120
};
let lastLoggedExecution = "";

function gauge(divId, title, value, suffix, min, max, color) {
  Plotly.newPlot(divId, [{
    type: "indicator",
    mode: "gauge+number",
    value: value ?? 0,
    title: { text: title },
    number: { suffix },
    gauge: {
      axis: { range: [min, max] },
      bar: { color }
    }
  }], {
    margin: { t: 40, b: 10, l: 10, r: 10 },
    paper_bgcolor: "rgba(0,0,0,0)",
    font: { color: "#eff2f7" }
  }, { displayModeBar: false, responsive: true });
}

function valueText(v, suffix = "") {
  if (v === null || v === undefined || Number.isNaN(v)) return "N/A";
  return `${Number(v).toFixed(1)}${suffix}`;
}

function dateText(isoDate) {
  if (!isoDate) return "N/A";
  const d = new Date(isoDate);
  if (Number.isNaN(d.getTime())) return "N/A";
  const datePart = d.toLocaleDateString("fr-FR");
  const timePart = d.toLocaleTimeString("fr-FR");
  return `${datePart}<br>${timePart}`;
}

function miniTempChart(divId, x, y) {
  Plotly.newPlot(divId, [{
    x,
    y,
    mode: "lines",
    line: { color: "#8ec5ff", width: 2.5 },
    fill: "tozeroy",
    fillcolor: "rgba(142, 197, 255, 0.12)",
    hovertemplate: "%{x}<br>%{y:.1f} C<extra></extra>"
  }], {
    margin: { t: 10, b: 26, l: 34, r: 8 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,255,255,0.03)",
    xaxis: {
      showgrid: false,
      tickfont: { color: "#a6b1c2", size: 10 }
    },
    yaxis: {
      title: "C",
      titlefont: { color: "#a6b1c2", size: 10 },
      gridcolor: "rgba(255,255,255,0.08)",
      zeroline: false
    },
    font: { color: "#eff2f7" }
  }, { displayModeBar: false, responsive: true });
}

function bigTempChart(divId, x, yExt, yInt, name) {
  Plotly.newPlot(divId, [
    {
      x,
      y: yExt,
      mode: "lines",
      name: "Temp ext.",
      line: { color: "#ff9f43", width: 3 },
      hovertemplate: "%{x}<br>Ext: %{y:.1f} C<extra></extra>"
    },
    {
      x,
      y: yInt,
      mode: "lines",
      name: "Temp boitier",
      line: { color: "#8ec5ff", width: 2 },
      hovertemplate: "%{x}<br>Boitier: %{y:.1f} C<extra></extra>"
    }
  ], {
    title: { text: `Historique ${name}` },
    margin: { t: 50, b: 45, l: 50, r: 20 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(255,255,255,0.02)",
    xaxis: { rangeslider: { visible: true } },
    yaxis: { title: "Temperature (C)" },
    font: { color: "#eff2f7" },
    legend: { orientation: "h", y: 1.12 }
  }, { responsive: true });
}

function toPickerValue(date) {
  const d = String(date.getDate()).padStart(2, "0");
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const y = date.getFullYear();
  const h = String(date.getHours()).padStart(2, "0");
  const min = String(date.getMinutes()).padStart(2, "0");
  return `${d}/${m}/${y} ${h}:${min}`;
}

function parsePickerDate(value) {
  if (!value) return null;
  const fr = value.match(/^(\d{2})\/(\d{2})\/(\d{4})\s+(\d{2}):(\d{2})$/);
  if (fr) {
    const [, dd, mm, yyyy, hh, mi] = fr;
    return new Date(Number(yyyy), Number(mm) - 1, Number(dd), Number(hh), Number(mi));
  }
  const fallback = new Date(value);
  return Number.isNaN(fallback.getTime()) ? null : fallback;
}

function setupModalPickers() {
  const startInput = document.getElementById("modal-start");
  const endInput = document.getElementById("modal-end");
  if (window.flatpickr) {
    const opts = {
      enableTime: true,
      dateFormat: "d/m/Y H:i",
      time_24hr: true,
      locale: "fr",
      altInput: true,
      altFormat: "l d F Y H:i"
    };
    flatpickr(startInput, opts);
    flatpickr(endInput, opts);
  }
}

function openModal() {
  document.getElementById("chart-modal").classList.remove("hidden");
}

function closeModal() {
  document.getElementById("chart-modal").classList.add("hidden");
}

async function refreshModalChart() {
  if (!modalState.nodeId || !modalState.start || !modalState.end) return;
  const params = new URLSearchParams({
    start: modalState.start.toISOString(),
    end: modalState.end.toISOString()
  });
  const series = await fetchJson(`/api/measurements/${modalState.nodeId}?${params.toString()}`);
  const x = series.series.map((s) => new Date(s.measured_at)); // Convertir en objet Date
  const yExt = series.series.map((s) => s.temperature_external_c);
  const yInt = series.series.map((s) => s.temperature_internal_c);
  bigTempChart("modal-chart", x, yExt, yInt, modalState.nodeLabel);
}

function initModalEvents() {
  const closeBtn = document.getElementById("modal-close-btn");
  const applyBtn = document.getElementById("modal-apply-btn");
  const exportBtn = document.getElementById("modal-export-btn");
  const backdrop = document.getElementById("chart-modal");
  const startInput = document.getElementById("modal-start");
  const endInput = document.getElementById("modal-end");

  closeBtn.addEventListener("click", closeModal);
  backdrop.addEventListener("click", (e) => {
    if (e.target.id === "chart-modal") closeModal();
  });

  applyBtn.addEventListener("click", async () => {
    const start = parsePickerDate(startInput.value);
    const end = parsePickerDate(endInput.value);
    if (!start || !end || start >= end) return;
    modalState.start = start;
    modalState.end = end;
    await refreshModalChart();
  });

  exportBtn.addEventListener("click", () => {
    if (!modalState.nodeId || !modalState.start || !modalState.end) return;
    const params = new URLSearchParams({
      node_id: String(modalState.nodeId),
      start: modalState.start.toISOString(),
      end: modalState.end.toISOString()
    });
    window.location.href = `/api/export.csv?${params.toString()}`;
  });
}

async function openChartModalForNode(node) {
  modalState.nodeId = node.node_id;
  modalState.nodeLabel = node.label;
  const end = new Date();
  const start = new Date(end.getTime() - 24 * 3600 * 1000);
  modalState.start = start;
  modalState.end = end;
  document.getElementById("modal-title").textContent = `${node.label} - Historique temperature`;
  document.getElementById("modal-start").value = toPickerValue(start);
  document.getElementById("modal-end").value = toPickerValue(end);
  openModal();
  await refreshModalChart();
}

async function render() {
  const grid = document.getElementById("node-grid");
  const [latest, settings] = await Promise.all([
    fetchJson("/api/latest"),
    fetchJson("/api/settings")
  ]);

  // On récupère toutes les séries en parallèle pour éviter de bloquer la boucle
  const allSeries = await Promise.all(
    latest.map(n => 
      fetchJson(`/api/measurements/${n.node_id}?hours=24`).catch(err => {
        console.warn(`Impossible de charger les mesures pour ${n.label}`, err);
        return { node_id: n.node_id, series: [] };
      })
    )
  );

  gaugeSettings.tempMin = Number(settings.gauge_temp_min ?? -10);
  gaugeSettings.tempMax = Number(settings.gauge_temp_max ?? 120);
  if (gaugeSettings.tempMin >= gaugeSettings.tempMax) {
    gaugeSettings.tempMin = -10;
    gaugeSettings.tempMax = 120;
  }
  grid.innerHTML = "";

  latest.forEach((node, index) => {
    const card = document.createElement("article");
    card.className = "node-card";
    card.dataset.nodeId = node.node_id;

    const rssi = node.signal_rssi;
    let sigText = "Signal inconnu";
    let sigColor = "#a6b1c2"; // muted
    if (rssi !== null && rssi !== undefined && !Number.isNaN(rssi)) {
      if (rssi > -60) {
        sigText = "Excellent / Fort";
        sigColor = "#4caf50"; // Vert
      } else if (rssi >= -75) {
        sigText = "Correct / Moyen";
        sigColor = "#ff9800"; // Orange
      } else {
        sigText = "Faible / Critique";
        sigColor = "#f44336"; // Rouge
      }
    }

    const tempExtDiv = `temp-ext-${node.node_id}`;
    const miniChartDiv = `temp-mini-${node.node_id}`;
    card.innerHTML = `
      <div class="node-card-content">
        <div class="node-card-left">
          <h3>${node.label}</h3>
          <p class="node-metric-text"><strong>Temp boitier:</strong> ${valueText(node.temperature_internal_c, " C")}</p>
          <p class="node-metric-text"><strong>Batterie:</strong> ${valueText(node.battery_pct, " %")}</p>
          <p class="node-metric-text"><strong>Signal:</strong> ${valueText(node.signal_rssi, " dBm")}</p>
          <div class="node-metric-text" style="display: flex; align-items: center; gap: 6px; color: ${sigColor}; margin: 4px 0 8px 0;">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12.55a11 11 0 0 1 14.08 0"></path><path d="M1.42 9a16 16 0 0 1 21.16 0"></path><path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line></svg>
            <span style="font-size: 0.85em; font-weight: 600;">${sigText}</span>
          </div>
          <p class="node-metric-text node-metric-small muted"><strong>Derniere mise a jour:</strong><br>${dateText(node.measured_at)}</p>
        </div>
        <div class="node-card-middle">
          <p class="muted chart-title">température sonde</p>
          <div id="${miniChartDiv}" class="temp-mini-chart"></div>
        </div>
        <div class="node-card-right">
          <div id="${tempExtDiv}" class="temp-gauge"></div>
        </div>
      </div>
    `;
    grid.appendChild(card);

    gauge(
      tempExtDiv,
      "Temp Sonde",
      node.temperature_external_c,
      " C",
      gaugeSettings.tempMin,
      gaugeSettings.tempMax,
      "#ff9f43"
    );
    const series = allSeries[index];
    const x = series.series.map(s => new Date(s.measured_at)); // Convertir en objet Date
    const y = series.series.map(s => s.temperature_external_c);
    miniTempChart(miniChartDiv, x, y);
    card.querySelector(".node-card-middle").addEventListener("click", () => {
      openChartModalForNode(node).catch(console.error);
    });
  });
}

async function monitorMeshcoreStatus() {
  try {
    const s = await fetchJson("/api/meshcore/status");
    if (s.last_command && s.last_execution_at !== lastLoggedExecution) {
      console.group(`[MeshCLI] ${s.last_command}`);
      console.log(s.last_output);
      console.groupEnd();
      lastLoggedExecution = s.last_execution_at;
    }
  } catch (e) {
    // Ignorer silencieusement les erreurs de monitoring
  }
}

setupModalPickers();
initModalEvents();
render().catch(console.error);

setInterval(() => {
  render().catch(console.error);
  // Rafraîchir le graphique historique s'il est visible
  const modal = document.getElementById("chart-modal");
  if (modal && !modal.classList.contains("hidden")) {
    refreshModalChart().catch(console.error);
  }
}, 30000);

setInterval(monitorMeshcoreStatus, 5000);
