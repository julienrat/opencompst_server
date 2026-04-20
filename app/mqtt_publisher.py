from __future__ import annotations

import json
import logging
from typing import Any

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MqttPublisher:
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

        client = mqtt.Client()
        if username:
            client.username_pw_set(username=username, password=password or None)

        try:
            client.connect(host, port=port, keepalive=15)
            client.loop_start()
            result = client.publish(topic, payload=json.dumps(payload), qos=0, retain=False)
            result.wait_for_publish(timeout=5)
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                raise RuntimeError(f"MQTT publish failed with rc={result.rc}")
        finally:
            try:
                client.loop_stop()
                client.disconnect()
            except Exception as exc:
                logger.debug("MQTT disconnect warning: %s", exc)
