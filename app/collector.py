from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import datetime, timezone

from .meshcore_client import MeshcoreClient
from .mqtt_publisher import MqttPublisher
from .repository import get_all_settings, get_setting, insert_measurements, list_nodes

logger = logging.getLogger(__name__)


class TelemetryCollector:
    def __init__(self, client: MeshcoreClient) -> None:
        self.client = client
        self.mqtt = MqttPublisher()
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except asyncio.TimeoutError:
                # Evite de bloquer le shutdown quand un appel meshcore-cli traine.
                logger.warning("Collector stop timeout: shutdown continue in background")
            except asyncio.CancelledError:
                pass
            finally:
                with contextlib.suppress(Exception):
                    self._task = None

    async def _loop(self) -> None:
        while self._running:
            try:
                # On exécute la collecte dans un thread séparé pour ne pas
                # geler l'interface web (FastAPI) pendant les appels CLI.
                await asyncio.to_thread(self.collect_sync)
            except Exception as exc:
                logger.exception("Collector cycle failed: %s", exc)
            interval = max(5, int(get_setting("poll_interval_seconds", "60")))
            await asyncio.sleep(interval)

    def collect_sync(self) -> None:
        """
        Version synchrone de la collecte pour exécution en thread.
        Regroupe toute la logique d'interrogation et de stockage.
        """
        settings = get_all_settings()
        preferred_port = settings.get("meshcore_port", "")
        if not self.client.ensure_connection(preferred_port=preferred_port or None):
            logger.warning("MeshCore USB indisponible: %s", self.client.status().get("last_error"))
            return

        nodes = list_nodes(enabled_only=True)
        mqtt_nodes_payload: dict[str, dict[str, float | None]] = {}
        measurements_to_save = []

        for node in nodes:
            mesh_id = node["mesh_id"]
            try:
                data = self.client.read_telemetry(
                    mesh_id=mesh_id,
                    node_type=node.get("node_type", "CLI"),
                )
                if not any(v is not None for v in data.values()):
                    logger.info("No telemetry returned for node %s on this cycle", mesh_id)
                    continue

                measurements_to_save.append({
                    "node_id": node["id"],
                    "temperature_external_c": data.get("temperature_external_c"),
                    "temperature_internal_c": data.get("temperature_internal_c"),
                    "battery_v": data.get("battery_v"),
                    "battery_pct": data.get("battery_pct"),
                    "signal_rssi": data.get("signal_rssi"),
                })

                node_name = (node.get("name") or "").strip() or mesh_id
                mqtt_nodes_payload[node_name] = {
                    "temperature_external_c": data.get("temperature_external_c"),
                    "temperature_internal_c": data.get("temperature_internal_c"),
                    "battery_v": data.get("battery_v"),
                    "battery_pct": data.get("battery_pct"),
                }
            except Exception as exc:
                logger.warning("Read failed for node %s: %s", mesh_id, exc)

        if measurements_to_save:
            insert_measurements(measurements_to_save)

        if mqtt_nodes_payload:
            self._publish_mqtt(mqtt_nodes_payload, settings)

    def _publish_mqtt(self, nodes_payload: dict[str, dict[str, float | None]], settings: dict[str, str]) -> None:
        if settings.get("mqtt_enabled", "0") != "1":
            return
        host = settings.get("mqtt_host", "").strip()
        topic = settings.get("mqtt_topic", "").strip()
        if not host or not topic:
            return

        raw_port = settings.get("mqtt_port", "1883").strip()
        try:
            port = int(raw_port)
        except ValueError:
            logger.warning("Invalid MQTT port: %s", raw_port)
            return

        payload = {
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "nodes": nodes_payload,
        }
        try:
            self.mqtt.publish(
                host=host,
                port=port,
                topic=topic,
                payload=payload,
                username=settings.get("mqtt_username", "").strip(),
                password=settings.get("mqtt_password", ""),
            )
        except Exception as exc:
            logger.warning("MQTT publish failed: %s", exc)
