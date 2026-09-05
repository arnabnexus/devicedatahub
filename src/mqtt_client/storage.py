import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import psycopg

logger = logging.getLogger(__name__)


class TelemetryRepository:
    def __init__(self) -> None:
        self.host = os.getenv("DB_HOST", "timescaledb")
        self.port = int(os.getenv("DB_PORT", "5432"))
        self.database = os.getenv("DB_NAME", "telemetry")
        self.user = os.getenv("DB_USER", "postgres")
        self.password = os.getenv("DB_PASSWORD", "postgres")
        self.table_name = os.getenv("DB_TABLE", "telemetry")
        self._conn = None
        self.ensure_db()

    def _connect(self):
        return psycopg.connect(
            host=self.host,
            port=self.port,
            dbname=self.database,
            user=self.user,
            password=self.password,
            connect_timeout=10,
        )

    def ensure_db(self) -> None:
        last_error = None
        for attempt in range(1, 11):
            try:
                with self._connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            """
                            CREATE TABLE IF NOT EXISTS public.telemetry (
                                id BIGSERIAL,
                                event_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                timestamp_epoch BIGINT,
                                device_id TEXT,
                                ap_mac TEXT,
                                serial_number TEXT,
                                firmware_version TEXT,
                                uptime_seconds INTEGER,
                                cpu_utilization_pct DOUBLE PRECISION,
                                memory_utilization_pct DOUBLE PRECISION,
                                connected_clients INTEGER,
                                radio_band TEXT,
                                channel INTEGER,
                                channel_utilization_pct DOUBLE PRECISION,
                                noise_floor_dbm DOUBLE PRECISION,
                                max_connected_device INTEGER,
                                topic TEXT NOT NULL,
                                raw_payload TEXT,
                                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                                PRIMARY KEY (event_time, id)
                            );
                            """
                        )
                        cur.execute("ALTER TABLE public.telemetry DROP COLUMN IF EXISTS payload;")
                        for statement in [
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS timestamp_epoch BIGINT;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS device_id TEXT;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS ap_mac TEXT;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS serial_number TEXT;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS firmware_version TEXT;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS uptime_seconds INTEGER;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS cpu_utilization_pct DOUBLE PRECISION;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS memory_utilization_pct DOUBLE PRECISION;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS connected_clients INTEGER;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS radio_band TEXT;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS channel INTEGER;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS channel_utilization_pct DOUBLE PRECISION;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS noise_floor_dbm DOUBLE PRECISION;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS max_connected_device INTEGER;",
                            "ALTER TABLE public.telemetry ADD COLUMN IF NOT EXISTS raw_payload TEXT;",
                        ]:
                            cur.execute(statement)
                        cur.execute(
                            "SELECT create_hypertable('public.telemetry', 'event_time', if_not_exists => TRUE);"
                        )
                logger.info("Telemetry table ready in database '%s'", self.database)
                return
            except Exception as exc:  # pragma: no cover - depends on DB startup timing
                last_error = exc
                logger.warning("Database not ready yet (attempt %s/10): %s", attempt, exc)
                time.sleep(2)

        raise RuntimeError(f"Could not initialize telemetry storage: {last_error}")

    def _parse_optional_int(self, value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _parse_optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def insert_message(
        self,
        topic: str,
        payload: str,
        device_id: str | None = None,
        ap_mac: str | None = None,
        serial_number: str | None = None,
        firmware_version: str | None = None,
        uptime_seconds: int | None = None,
        cpu_utilization_pct: float | None = None,
        memory_utilization_pct: float | None = None,
        connected_clients: int | None = None,
        radio_band: str | None = None,
        channel: int | None = None,
        channel_utilization_pct: float | None = None,
        noise_floor_dbm: float | None = None,
        max_connected_device: int | None = None,
        timestamp_epoch: int | None = None,
    ) -> None:
        parsed: Any = None
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = None

        if isinstance(parsed, dict):
            device_id = device_id or parsed.get("device_id") or parsed.get("ap_mac") or parsed.get("serial_number")
            ap_mac = ap_mac or parsed.get("ap_mac")
            serial_number = serial_number or parsed.get("serial_number")
            firmware_version = firmware_version or parsed.get("firmware_version")
            uptime_seconds = self._parse_optional_int(parsed.get("uptime_seconds")) if uptime_seconds is None else uptime_seconds
            cpu_utilization_pct = self._parse_optional_float(parsed.get("cpu_utilization_pct")) if cpu_utilization_pct is None else cpu_utilization_pct
            memory_utilization_pct = self._parse_optional_float(parsed.get("memory_utilization_pct")) if memory_utilization_pct is None else memory_utilization_pct
            connected_clients = self._parse_optional_int(parsed.get("connected_clients")) if connected_clients is None else connected_clients
            radio_band = radio_band or parsed.get("radio_band")
            channel = self._parse_optional_int(parsed.get("channel")) if channel is None else channel
            channel_utilization_pct = self._parse_optional_float(parsed.get("channel_utilization_pct")) if channel_utilization_pct is None else channel_utilization_pct
            noise_floor_dbm = self._parse_optional_float(parsed.get("noise_floor_dbm")) if noise_floor_dbm is None else noise_floor_dbm
            max_connected_device = self._parse_optional_int(parsed.get("max_connected_device")) if max_connected_device is None else max_connected_device
            timestamp_epoch = self._parse_optional_int(parsed.get("timestamp")) if timestamp_epoch is None else timestamp_epoch

        event_time = None
        if timestamp_epoch is not None:
            try:
                event_time = datetime.fromtimestamp(timestamp_epoch, tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                event_time = None

        if event_time is None:
            event_time = datetime.now(timezone.utc)

        if device_id is None and ap_mac is not None:
            device_id = ap_mac

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO public.telemetry (
                        event_time,
                        timestamp_epoch,
                        device_id,
                        ap_mac,
                        serial_number,
                        firmware_version,
                        uptime_seconds,
                        cpu_utilization_pct,
                        memory_utilization_pct,
                        connected_clients,
                        radio_band,
                        channel,
                        channel_utilization_pct,
                        noise_floor_dbm,
                        max_connected_device,
                        topic,
                        raw_payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        event_time,
                        timestamp_epoch,
                        device_id,
                        ap_mac,
                        serial_number,
                        firmware_version,
                        uptime_seconds,
                        cpu_utilization_pct,
                        memory_utilization_pct,
                        connected_clients,
                        radio_band,
                        channel,
                        channel_utilization_pct,
                        noise_floor_dbm,
                        max_connected_device,
                        topic,
                        payload,
                    ),
                )

        logger.info(
            "Stored AP telemetry for ap_mac=%s serial_number=%s firmware_version=%s max_connected_device=%s on topic=%s",
            ap_mac,
            serial_number,
            firmware_version,
            max_connected_device,
            topic,
        )
