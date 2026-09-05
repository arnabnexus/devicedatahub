import json
import logging
import time
from typing import Any

import paho.mqtt.client as mqtt

from .config import get_settings
from .storage import TelemetryRepository

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=get_settings().log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


class MqttTelemetryConsumer:
    def __init__(self) -> None:
        self.settings = get_settings()
        _setup_logging()
        self.storage = TelemetryRepository()
        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.settings.client_id,
        )
        self.client.enable_logger(logger)

        if self.settings.username and self.settings.password:
            self.client.username_pw_set(self.settings.username, self.settings.password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to MQTT broker at %s:%s", self.settings.broker_host, self.settings.broker_port)
            client.subscribe(self.settings.topic, qos=self.settings.qos)
            logger.info("Subscribed to telemetry topic: %s", self.settings.topic)
        else:
            logger.error("Connection failed with MQTT code %s", rc)

    def _on_message(self, client, userdata, msg):
        payload = msg.payload.decode("utf-8", errors="replace")
        logger.info("Telemetry received from topic '%s': %s", msg.topic, payload)

        device_id = None
        ap_mac = None
        serial_number = None
        firmware_version = None
        uptime_seconds = None
        cpu_utilization_pct = None
        memory_utilization_pct = None
        connected_clients = None
        radio_band = None
        channel = None
        channel_utilization_pct = None
        noise_floor_dbm = None
        max_connected_device = None
        timestamp_epoch = None

        try:
            parsed = json.loads(payload)
            if isinstance(parsed, dict):
                device_id = parsed.get("device_id") or parsed.get("ap_mac") or parsed.get("serial_number")
                ap_mac = parsed.get("ap_mac")
                serial_number = parsed.get("serial_number")
                firmware_version = parsed.get("firmware_version")
                uptime_seconds = parsed.get("uptime_seconds")
                cpu_utilization_pct = parsed.get("cpu_utilization_pct")
                memory_utilization_pct = parsed.get("memory_utilization_pct")
                connected_clients = parsed.get("connected_clients")
                radio_band = parsed.get("radio_band")
                channel = parsed.get("channel")
                channel_utilization_pct = parsed.get("channel_utilization_pct")
                noise_floor_dbm = parsed.get("noise_floor_dbm")
                max_connected_device = parsed.get("max_connected_device")
                timestamp_epoch = parsed.get("timestamp")
                logger.info("Parsed AP telemetry payload: %s", parsed)
            else:
                logger.info("Message is not a JSON object; storing raw payload")
        except json.JSONDecodeError:
            logger.info("Payload is not valid JSON; storing raw payload")

        try:
            self.storage.insert_message(
                topic=msg.topic,
                payload=payload,
                device_id=device_id,
                ap_mac=ap_mac,
                serial_number=serial_number,
                firmware_version=firmware_version,
                uptime_seconds=uptime_seconds,
                cpu_utilization_pct=cpu_utilization_pct,
                memory_utilization_pct=memory_utilization_pct,
                connected_clients=connected_clients,
                radio_band=radio_band,
                channel=channel,
                channel_utilization_pct=channel_utilization_pct,
                noise_floor_dbm=noise_floor_dbm,
                max_connected_device=max_connected_device,
                timestamp_epoch=timestamp_epoch,
            )
            logger.info("Saved AP telemetry to TimescaleDB")
        except Exception:
            logger.exception("Failed to store AP telemetry payload in TimescaleDB")

    def _on_disconnect(self, client, userdata, rc, properties=None):
        logger.warning("Disconnected from MQTT broker with code %s", rc)

    def connect(self) -> None:
        logger.info("Connecting to broker at %s:%s", self.settings.broker_host, self.settings.broker_port)
        self.client.connect(self.settings.broker_host, self.settings.broker_port, self.settings.keepalive)
        self.client.loop_start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutdown requested")
            self.disconnect()

    def publish(self, payload: str | dict[str, Any], topic: str | None = None) -> None:
        target_topic = topic or self.settings.topic
        if isinstance(payload, dict):
            payload = json.dumps(payload)

        result = self.client.publish(target_topic, payload, qos=self.settings.qos)
        result.wait_for_publish()
        logger.info("Published telemetry to %s: %s", target_topic, payload)

    def disconnect(self) -> None:
        self.client.loop_stop()
        self.client.disconnect()
        logger.info("Disconnected from broker")
