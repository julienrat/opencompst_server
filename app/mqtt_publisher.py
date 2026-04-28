from __future__ import annotations

import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MqttPublisher:
    def __init__(self):
        self.client = mqtt.Client()
        self._current_config = {}

    def disconnect(self):
        self.client.disconnect()

    def publish(
        self,
        host: str,
        port: int,
        topic: str,
        payload: dict[str, Any],
        username: str = "",
        password: str = "",
    ) -> None:
        host = host.strip()
        topic = topic.strip()
        if not host or not topic:
            return

        # Reconnexion seulement si la config change ou si déconnecté
        config = (host, port, username, password)
        if config != self._current_config or not self.client.is_connected():
            if self.client.is_connected():
                self.client.disconnect()
            if username:
                self.client.username_pw_set(username=username, password=password or None)
            try:
                self.client.connect(host, port=port, keepalive=60)
                self.client.loop_start()
                self._current_config = config
            except Exception as exc:
                logger.error("MQTT Connection failed: %s", exc)
                return

        try:
            result = self.client.publish(topic, payload=json.dumps(payload), qos=0, retain=False)
            # On ne bloque pas avec wait_for_publish pour la fluidité
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT publish failed with rc={result.rc}")
        except Exception as exc:
            logger.warning("MQTT publish exception: %s", exc)
