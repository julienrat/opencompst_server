from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from .collector import TelemetryCollector
from .db import init_db
from .meshcore_client import MeshcoreClient
from .repository import (
    delete_node,
    get_setting,
    latest_measurements,
    list_nodes,
    series_for_export,
    series_for_node,
    set_setting,
    update_node,
    upsert_node,
)

app = FastAPI(title="OpenCompost Telemetry")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

meshcore = MeshcoreClient()
collector = TelemetryCollector(meshcore)


class NodeUpdate(BaseModel):
    name: str | None = None
    enabled: bool = True


class SettingsUpdate(BaseModel):
    poll_interval_seconds: int = Field(ge=5, le=3600)
    repeater_login_node: str = ""
    repeater_password: str = ""
    gauge_temp_min: float = -10
    gauge_temp_max: float = 120
    mqtt_host: str = ""
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_topic: str = ""
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_enabled: bool = False


class PortConnect(BaseModel):
    port: str = Field(min_length=3, max_length=300)


@app.on_event("startup")
async def startup_event() -> None:
    init_db()
    meshcore.set_port(get_setting("meshcore_port", ""))
    await collector.start()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await collector.stop()


@app.get("/", response_class=HTMLResponse)
async def dashboard_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="dashboard.html")


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request=request, name="admin.html")


@app.get("/api/nodes")
async def api_nodes(enabled_only: bool = False) -> list[dict]:
    return list_nodes(enabled_only=enabled_only)


@app.post("/api/nodes/discover")
async def api_discover_nodes() -> dict:
    discovered = meshcore.discover_nodes()
    stored = [upsert_node(n["mesh_id"], n.get("name"), n.get("node_type", "CLI")) for n in discovered]
    return {"count": len(stored), "nodes": stored}


@app.put("/api/nodes/{node_id}")
async def api_update_node(node_id: int, payload: NodeUpdate) -> dict:
    updated = update_node(node_id, payload.name, payload.enabled)
    if not updated:
        raise HTTPException(status_code=404, detail="Node not found")
    return updated


@app.delete("/api/nodes/{node_id}")
async def api_delete_node(node_id: int) -> dict:
    deleted = delete_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")
    return {"deleted": True, "node_id": node_id}


@app.get("/api/settings")
async def api_settings() -> dict:
    return {
        "poll_interval_seconds": int(get_setting("poll_interval_seconds", "60")),
        "meshcore_port": get_setting("meshcore_port", ""),
        "repeater_login_node": get_setting("repeater_login_node", ""),
        "repeater_password": get_setting("repeater_password", ""),
        "gauge_temp_min": float(get_setting("gauge_temp_min", "-10")),
        "gauge_temp_max": float(get_setting("gauge_temp_max", "120")),
        "mqtt_host": get_setting("mqtt_host", ""),
        "mqtt_port": int(get_setting("mqtt_port", "1883")),
        "mqtt_topic": get_setting("mqtt_topic", ""),
        "mqtt_username": get_setting("mqtt_username", ""),
        "mqtt_password": get_setting("mqtt_password", ""),
        "mqtt_enabled": get_setting("mqtt_enabled", "0") == "1",
    }


@app.put("/api/settings")
async def api_update_settings(payload: SettingsUpdate) -> dict:
    if payload.gauge_temp_min >= payload.gauge_temp_max:
        raise HTTPException(status_code=400, detail="gauge_temp_min must be lower than gauge_temp_max")
    set_setting("poll_interval_seconds", str(payload.poll_interval_seconds))
    set_setting("repeater_login_node", payload.repeater_login_node.strip())
    set_setting("repeater_password", payload.repeater_password)
    set_setting("gauge_temp_min", str(payload.gauge_temp_min))
    set_setting("gauge_temp_max", str(payload.gauge_temp_max))
    set_setting("mqtt_host", payload.mqtt_host.strip())
    set_setting("mqtt_port", str(payload.mqtt_port))
    set_setting("mqtt_topic", payload.mqtt_topic.strip())
    set_setting("mqtt_username", payload.mqtt_username.strip())
    set_setting("mqtt_password", payload.mqtt_password)
    set_setting("mqtt_enabled", "1" if payload.mqtt_enabled else "0")
    return {
        "poll_interval_seconds": payload.poll_interval_seconds,
        "repeater_login_node": payload.repeater_login_node.strip(),
        "gauge_temp_min": payload.gauge_temp_min,
        "gauge_temp_max": payload.gauge_temp_max,
        "mqtt_host": payload.mqtt_host.strip(),
        "mqtt_port": payload.mqtt_port,
        "mqtt_topic": payload.mqtt_topic.strip(),
        "mqtt_username": payload.mqtt_username.strip(),
        "mqtt_enabled": payload.mqtt_enabled,
    }


@app.get("/api/ports")
async def api_ports() -> dict:
    candidates = set()
    for port in meshcore.list_devices():
        candidates.add(port)
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/serial/by-id/*"):
        for device in Path("/").glob(pattern.lstrip("/")):
            candidates.add(str(device.resolve()) if device.is_symlink() else str(device))
    current = get_setting("meshcore_port", "")
    ports = sorted(candidates)
    if current and current not in ports:
        ports.insert(0, current)
    return {"ports": ports, "current": current}


@app.post("/api/ports/connect")
async def api_connect_port(payload: PortConnect) -> dict:
    meshcore.set_port(payload.port)
    ok = meshcore.test_connection()
    if not ok:
        meshcore.set_port(get_setting("meshcore_port", ""))
        raise HTTPException(status_code=400, detail=f"Connexion impossible sur {payload.port}")

    set_setting("meshcore_port", payload.port)
    return {"connected": True, "port": payload.port}


@app.get("/api/meshcore/status")
async def api_meshcore_status() -> dict:
    # Lecture d'etat uniquement; la reconnexion automatique est geree par le collecteur.
    return meshcore.status()


@app.get("/api/latest")
async def api_latest() -> list[dict]:
    return latest_measurements()


@app.get("/api/measurements/{node_id}")
async def api_measurements(
    node_id: int,
    hours: int = Query(default=24, ge=1, le=24 * 90),
    start: datetime | None = None,
    end: datetime | None = None,
) -> dict:
    if start and end:
        if start >= end:
            raise HTTPException(status_code=400, detail="start must be before end")
        series = series_for_export(node_id, start.isoformat(), end.isoformat())
    else:
        window_start = datetime.now(timezone.utc) - timedelta(hours=hours)
        series = series_for_node(node_id, window_start.isoformat())
    return {"node_id": node_id, "series": series}


@app.get("/api/export.csv")
async def api_export_csv(
    node_id: int,
    start: datetime,
    end: datetime,
) -> Response:
    if start >= end:
        raise HTTPException(status_code=400, detail="start must be before end")
    rows = series_for_export(node_id=node_id, start_iso=start.isoformat(), end_iso=end.isoformat())
    output = StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=["measured_at", "temperature_external_c", "temperature_internal_c", "battery_v", "battery_pct"],
    )
    writer.writeheader()
    writer.writerows(rows)
    filename = f"node_{node_id}_{start.date()}_{end.date()}.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return PlainTextResponse(output.getvalue(), media_type="text/csv", headers=headers)
