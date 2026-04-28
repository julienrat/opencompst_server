async function fetchJson(url, options = {}) {
  const res = await fetch(url, options);
  if (!res.ok) {
    throw new Error(await res.text());
  }
  return res.json();
}

let savedSettingsSnapshot = "";
let savedNodesOrderSnapshot = "";
let lastLoggedExecution = "";

function fmtDate(iso) {
  if (!iso) return "N/A";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "N/A";
  return d.toLocaleString("fr-FR");
}

function collectSettingsFromForm() {
  return {
    poll_interval_seconds: Number(document.getElementById("poll-interval").value),
    repeater_login_node: document.getElementById("repeater-login-node").value.trim(),
    repeater_password: document.getElementById("repeater-password").value,
    gauge_temp_min: Number(document.getElementById("gauge-temp-min").value),
    gauge_temp_max: Number(document.getElementById("gauge-temp-max").value),
    mqtt_host: document.getElementById("mqtt-host").value.trim(),
    mqtt_port: Number(document.getElementById("mqtt-port").value || 1883),
    mqtt_topic: document.getElementById("mqtt-topic").value.trim(),
    mqtt_username: document.getElementById("mqtt-username").value.trim(),
    mqtt_password: document.getElementById("mqtt-password").value,
    mqtt_enabled: document.getElementById("mqtt-enabled").checked
  };
}

function collectNodesOrder() {
  const tbody = document.getElementById("nodes-tbody");
  if (!tbody) return "";
  const rows = tbody.querySelectorAll("tr[data-node-id]");
  return Array.from(rows).map((row) => row.dataset.nodeId).join(",");
}

function updateSaveButtonState() {
  const saveBtn = document.getElementById("save-settings-btn");
  const hint = document.getElementById("settings-dirty-hint");
  
  const currentSettings = JSON.stringify(collectSettingsFromForm());
  const currentOrder = collectNodesOrder();
  
  const isSettingsDirty = currentSettings !== savedSettingsSnapshot;
  const isOrderDirty = currentOrder !== savedNodesOrderSnapshot;
  const isDirty = isSettingsDirty || isOrderDirty;

  saveBtn.classList.toggle("save-btn-dirty", isDirty);
  saveBtn.classList.toggle("save-btn-clean", !isDirty);
  hint.textContent = isDirty ? "Modifications non sauvegardees" : "Configuration sauvegardee";
  hint.className = isDirty ? "status-off" : "muted";
}

function updateMqttCardState() {
  const enabled = document.getElementById("mqtt-enabled").checked;
  const container = document.getElementById("mqtt-config-fields");
  container.classList.toggle("mqtt-disabled", !enabled);
  container.querySelectorAll("input").forEach((input) => {
    input.disabled = !enabled;
  });
  updateSaveButtonState();
}

async function refreshNodes() {
  const nodes = await fetchJson("/api/nodes");
  const container = document.getElementById("nodes-admin");

  container.innerHTML = `
    <table>
      <thead><tr><th></th><th>ID</th><th>Type</th><th>Nom</th><th>Actif</th><th>Actions</th></tr></thead>
      <tbody id="nodes-tbody">
      ${nodes.map((n) => `
        <tr data-node-id="${n.id}">
          <td class="drag-handle">☰</td>
          <td>${n.mesh_id}</td>
          <td>
            <select data-type-id="${n.id}">
              <option value="CLI" ${n.node_type === 'CLI' ? 'selected' : ''}>CLI</option>
              <option value="REP" ${n.node_type === 'REP' ? 'selected' : ''}>REP</option>
            </select>
          </td>
          <td><input data-name-id="${n.id}" value="${n.name ?? ""}" placeholder="Nom du noeud"></td>
          <td>${n.enabled ? '<span class="status-ok">Oui</span>' : '<span class="status-off">Non</span>'}</td>
          <td>
            <label><input data-enabled-id="${n.id}" type="checkbox" ${n.enabled ? "checked" : ""}> active</label>
            <button data-save-id="${n.id}">Sauver</button>
            <button data-delete-id="${n.id}" class="btn-danger">Supprimer</button>
          </td>
        </tr>
      `).join("")}
      </tbody>
    </table>
  `;

  container.querySelectorAll("button[data-save-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.saveId;
      const name = container.querySelector(`input[data-name-id="${id}"]`).value;
      const enabled = container.querySelector(`input[data-enabled-id="${id}"]`).checked;
      const node_type = container.querySelector(`select[data-type-id="${id}"]`).value;
      await fetchJson(`/api/nodes/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, enabled, node_type })
      });
      refreshNodes().catch(console.error);
    });
  });

  container.querySelectorAll("button[data-delete-id]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.deleteId;
      const rowName = container.querySelector(`input[data-name-id="${id}"]`)?.value?.trim() || `noeud ${id}`;
      const ok = window.confirm(
        `Supprimer ${rowName} ?\n\nAttention: cette action peut supprimer tout l'historique des mesures pour ce noeud.`
      );
      if (!ok) return;
      await fetchJson(`/api/nodes/${id}`, { method: "DELETE" });
      refreshNodes().catch(console.error);
    });
  });
  
  savedNodesOrderSnapshot = collectNodesOrder();
  updateSaveButtonState();

  // Initialisation du tri sur le tableau des noeuds
  const tbody = document.getElementById("nodes-tbody");
  if (tbody && window.Sortable) {
    new Sortable(tbody, {
      handle: ".drag-handle",
      animation: 150,
      onEnd: () => {
        updateSaveButtonState();
      }
    });
  }
}

async function refreshSettings() {
  const settings = await fetchJson("/api/settings");
  document.getElementById("poll-interval").value = settings.poll_interval_seconds;
  document.getElementById("repeater-login-node").value = settings.repeater_login_node || "";
  document.getElementById("repeater-password").value = settings.repeater_password || "";
  document.getElementById("gauge-temp-min").value = settings.gauge_temp_min ?? -10;
  document.getElementById("gauge-temp-max").value = settings.gauge_temp_max ?? 120;
  document.getElementById("mqtt-host").value = settings.mqtt_host || "";
  document.getElementById("mqtt-port").value = settings.mqtt_port ?? 1883;
  document.getElementById("mqtt-topic").value = settings.mqtt_topic || "";
  document.getElementById("mqtt-username").value = settings.mqtt_username || "";
  document.getElementById("mqtt-password").value = settings.mqtt_password || "";
  document.getElementById("mqtt-enabled").checked = Boolean(settings.mqtt_enabled);
  updateMqttCardState();
  savedSettingsSnapshot = JSON.stringify(collectSettingsFromForm());
  updateSaveButtonState();
  const status = document.getElementById("port-status");
  if (settings.meshcore_port) {
    status.textContent = `Port configure: ${settings.meshcore_port}`;
    status.className = "status-ok";
  } else {
    status.textContent = "Aucun port configure";
    status.className = "muted";
  }
}

async function refreshPorts() {
  const data = await fetchJson("/api/ports");
  const select = document.getElementById("meshcore-port");
  select.innerHTML = data.ports.map((p) => `<option value="${p}">${p}</option>`).join("");
  if (data.current) {
    select.value = data.current;
  }
}

document.getElementById("discover-btn").addEventListener("click", async () => {
  const discoverBtn = document.getElementById("discover-btn");
  const status = document.getElementById("port-status");
  discoverBtn.disabled = true;
  status.textContent = "Detection des noeuds en cours...";
  status.className = "muted";
  try {
    const result = await fetchJson("/api/nodes/discover", { method: "POST" });
    status.textContent = `${result.count || 0} noeud(s) detecte(s), liste mise a jour`;
    status.className = "status-ok";
  } catch (error) {
    status.textContent = `Echec detection: ${String(error.message).slice(0, 140)}`;
    status.className = "status-off";
  } finally {
    discoverBtn.disabled = false;
    await refreshNodes();
  }
});

document.getElementById("connect-port-btn").addEventListener("click", async () => {
  const status = document.getElementById("port-status");
  const port = document.getElementById("meshcore-port").value;
  if (!port) {
    status.textContent = "Selectionne un port.";
    status.className = "status-off";
    return;
  }
  status.textContent = "Connexion en cours...";
  status.className = "muted";
  try {
    const result = await fetchJson("/api/ports/connect", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ port })
    });
    status.textContent = `Connecte: ${result.port}`;
    status.className = "status-ok";
    refreshMeshcoreStatus().catch(console.error);
    refreshPorts().catch(console.error);
  } catch (error) {
    status.textContent = `Echec: ${String(error.message).slice(0, 140)}`;
    status.className = "status-off";
  }
});

document.getElementById("save-settings-btn").addEventListener("click", async () => {
  const payload = collectSettingsFromForm();
  
  // Sauvegarde des reglages generaux
  const p1 = fetchJson("/api/settings", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });

  // Sauvegarde de l'ordre des noeuds
  const tbody = document.getElementById("nodes-tbody");
  const rows = tbody ? tbody.querySelectorAll("tr[data-node-id]") : [];
  const orders = Array.from(rows).map((row, index) => ({
    id: parseInt(row.dataset.nodeId),
    order: index
  }));
  const p2 = fetchJson("/api/nodes/reorder", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(orders)
  });

  await Promise.all([p1, p2]);

  savedSettingsSnapshot = JSON.stringify(payload);
  savedNodesOrderSnapshot = collectNodesOrder();
  updateSaveButtonState();
  refreshMeshcoreStatus().catch(console.error);
});

document.getElementById("mqtt-enabled").addEventListener("change", updateMqttCardState);

[
  "poll-interval",
  "repeater-login-node",
  "repeater-password",
  "gauge-temp-min",
  "gauge-temp-max",
  "mqtt-host",
  "mqtt-port",
  "mqtt-topic",
  "mqtt-username",
  "mqtt-password"
].forEach((id) => {
  const el = document.getElementById(id);
  el.addEventListener("input", updateSaveButtonState);
  el.addEventListener("change", updateSaveButtonState);
});

async function refreshMeshcoreStatus() {
  const el = document.getElementById("meshcore-server-status");
  try {
    const s = await fetchJson("/api/meshcore/status");

    if (s.last_command && s.last_execution_at !== lastLoggedExecution) {
      console.group(`[MeshCLI] ${s.last_command}`);
      console.log(s.last_output);
      console.groupEnd();
      lastLoggedExecution = s.last_execution_at;
    }

    if (s.connected) {
      el.textContent = `Etat MeshCore USB: Connecte sur ${s.port || "N/A"} | Derniere reussite: ${fmtDate(s.last_ok_at)}`;
      el.className = "status-ok";
    } else {
      el.textContent = `Etat MeshCore USB: Deconnecte, reconnexion automatique active | Derniere tentative: ${fmtDate(s.last_attempt_at)} | Erreur: ${s.last_error || "N/A"}`;
      el.className = "status-off";
    }
  } catch (error) {
    el.textContent = `Etat MeshCore USB: indisponible (${String(error.message).slice(0, 120)})`;
    el.className = "status-off";
  }
}

refreshSettings().catch(console.error);
refreshPorts().catch(console.error);
refreshNodes().catch(console.error);
refreshMeshcoreStatus().catch(console.error);
setInterval(() => refreshMeshcoreStatus().catch(console.error), 30000);
