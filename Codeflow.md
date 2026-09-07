# DeviceDataHub Code Flow

## 1. System Overview

DeviceDataHub is an MQTT telemetry pipeline:

```text
Wi-Fi device or simulator
          |
          v
      MQTT broker
          |
          v
    src/main.py
          |
          v
mqtt_client/client.py
          |
          v
mqtt_client/storage.py
          |
          v
TimescaleDB: public.telemetry
          |
          v
       Grafana
```

The Python consumer receives MQTT messages, validates and parses JSON payloads, extracts Wi-Fi radio metrics, and stores one database row per radio. Grafana reads those rows from TimescaleDB.

## 2. Python Runtime Flow

### `src/main.py`

This is the application entry point.

1. Creates `MqttTelemetryConsumer`.
2. Registers handlers for `SIGINT` and `SIGTERM`.
3. Calls `consumer.connect()`.
4. Disconnects cleanly when stopped.

The application is started locally with:

```bash
MQTT_BROKER_HOST=localhost PYTHONPATH=src python src/main.py
```

The Docker image starts the same entry point through the command in `Dockerfile`.

### `src/mqtt_client/config.py`

This file loads environment variables and creates the cached `Settings` object used by the MQTT client.

Important settings include:

- `MQTT_BROKER_HOST`
- `MQTT_BROKER_PORT`
- `MQTT_CLIENT_ID`
- `MQTT_USERNAME`
- `MQTT_PASSWORD`
- `MQTT_TOPIC`
- `MQTT_QOS`
- `MQTT_KEEPALIVE`
- `LOG_LEVEL`
- `DB_HOST`
- `DB_PORT`
- `DB_NAME`
- `DB_USER`
- `DB_PASSWORD`
- `DB_TABLE`

Values are loaded from the environment. Defaults are defined in the Python class, and Docker Compose can override them for the container.

### `src/mqtt_client/client.py`

`MqttTelemetryConsumer` owns the MQTT connection.

When it connects:

1. It authenticates if username and password are configured.
2. It subscribes to `MQTT_TOPIC`.
3. It starts the Paho MQTT network loop.

When a message arrives:

1. The MQTT bytes are decoded as UTF-8.
2. The payload is parsed as JSON.
3. Non-object JSON is ignored.
4. `TelemetryRepository.extract_wifi_rows()` searches for Wi-Fi data.
5. If Wi-Fi rows are found, `insert_wifi_metrics()` writes them to TimescaleDB.
6. Invalid JSON and database errors are logged.

### `src/mqtt_client/storage.py`

`TelemetryRepository` owns database initialization, data conversion, and inserts.

On startup it:

1. Reads PostgreSQL connection settings.
2. Retries the connection up to ten times.
3. Creates `public.telemetry` if it does not exist.
4. Converts the table into a TimescaleDB hypertable using `timestamp`.

For each MQTT payload it expects a structure similar to:

```json
{
  "timestamp": "2026-09-05T16:28:31Z",
  "schema_version": "1.0",
  "device_id": "WEH-587BE924EF9B",
  "network": [
    {
      "type": "wifi",
      "radios": [
        {
          "radio": "5GHz",
          "ifname": "phy1-ap0",
          "radio_stats": {
            "channel": 36,
            "channel_utilization_pct": 7
          },
          "clients": []
        }
      ]
    }
  ]
}
```

Each radio becomes one row. Numeric fields are converted to integers or floating-point values when possible. The `clients` list is stored as JSONB.

## 3. Device Simulation

### `src/simulate_device.py`

This script creates a test MQTT publisher. It cycles through four simulated access points, generates random values, publishes every ten seconds, and prints each payload.

Its default configuration is:

```text
MQTT_BROKER_HOST=localhost
MQTT_BROKER_PORT=1883
MQTT_TOPIC=devices/telemetry
```

The simulator publishes the nested structure expected by the storage layer: `network -> radios -> radio_stats`, with one generated 2.4 GHz radio and one generated 5 GHz radio per message. Each radio also includes a generated `clients` list.

## 4. Docker and Services

### `Dockerfile`

The Dockerfile:

1. Uses Python 3.12 slim.
2. Sets `/app` as the working directory.
3. Sets `PYTHONPATH=/app/src`.
4. Installs dependencies from `requirements.txt`.
5. Copies the `src` directory.
6. Runs `python src/main.py`.

### `docker-compose.yml`

The Compose file currently defines two active services:

- `timescaledb`: TimescaleDB using PostgreSQL 16, exposed as host port `5433`.
- `mqtt-server`: the Python consumer built from the Dockerfile.

The database uses:

```text
Database: telemetry
User: postgres
Password: postgres
Container hostname: timescaledb
Container port: 5432
```

The database volume `timescaledb_data` preserves data across restarts.

The local `mqtt-broker` service definition remains commented out, but Grafana is enabled and starts with TimescaleDB. The Compose file mounts the Grafana data-source configuration, although dashboard JSON files are not automatically provisioned yet.

### `mosquitto.conf`

This is the configuration for a local Mosquitto broker:

- Persistence disabled.
- Anonymous connections allowed.
- Listener on port `1883`.
- Logs sent to standard output.

It is currently unused because the Mosquitto service is commented out in Compose.

## 5. Configuration Modes

### Local Python mode

Use `.env.example` as the template for a local `.env` file. The expected local endpoints are:

```text
MQTT broker: localhost:1883
Database: localhost:5433
Topic: devices/telemetry
```

Start the database and broker, then run the consumer and simulator separately.

### Docker mode

Inside the application container, the database is reached through:

```text
DB_HOST=timescaledb
DB_PORT=5432
```

The current Compose configuration points MQTT to:

```text
MQTT_BROKER_HOST=0.tcp.in.ngrok.io
MQTT_BROKER_PORT=17241
MQTT_TOPIC=weh-device/network
```

This is different from the local defaults and from the simulator defaults.

### Configuration priority

Runtime environment variables take precedence over the defaults in `config.py`. Docker Compose supplies environment variables directly to the container. `.env.example` is documentation/template material and is not itself automatically used unless copied to `.env` and loaded by the application environment.

## 6. Database and SQL Files

### Database schema

The authoritative runtime schema is currently in `src/mqtt_client/storage.py`, not in a separate migration file. It creates the `public.telemetry` table and the TimescaleDB hypertable.

The primary key is:

```text
(timestamp, device_id, radio)
```

This prevents duplicate observations for the same timestamp, device, and radio.

### `query.sql`

This file contains manual SQL for:

- Selecting all telemetry rows.
- Inserting sample Wi-Fi radio data.
- Avoiding duplicate rows with `ON CONFLICT`.

It is useful for manually testing the schema, but it is not executed automatically by Docker Compose or the Python application.

### `wifi.session.sql`

This file contains manual inspection queries:

- Select all telemetry rows.
- Inspect column names and data types.
- View the newest rows.

It is a database-session helper rather than part of the application runtime.

## 7. Grafana Flow

### `grafana/provisioning/datasources/timescaledb.yml`

This provisions a PostgreSQL-compatible TimescaleDB data source in Grafana.

Grafana connects to:

```text
Host: timescaledb:5432
Database: telemetry
User: postgres
Password: postgres
```

The hostname works only when Grafana runs in the same Docker Compose network as TimescaleDB.

### `grafana/dashboard/ap-telemetry.json`

This dashboard was exported from Grafana. Its panels query `public.telemetry` and use dashboard variables for:

- `device_id`
- `radio`

The panels show current radio state, utilization, airtime, signal quality, packet metrics, and neighboring access points.

### `grafana/dashboard/test.json`

This is another exported or test dashboard. It is not referenced by the Python application.

### Dashboard provisioning status

The Grafana service and its volume/data-source provisioning mount are enabled in `docker-compose.yml`. The data source can therefore be provisioned automatically, but the dashboard JSON files still require manual import because dashboard provisioning has not been configured.

## 8. Repository Creation History

The Git history shows the project was developed incrementally:

- `65dd685` created the initial Docker, MQTT, Python, database, and Grafana files.
- `c1de56c` updated the README and added the architecture image.
- `1e239f2` changed the MQTT/storage implementation and added a test dashboard and design notes.
- `048a9c9` updated the main Grafana dashboard.
- `df50128` changed Docker Compose and MQTT consumer behavior.

The current working tree also contains local changes to `query.sql` and `requirements.txt`, plus the untracked `wifi.session.sql` file.

## 9. Recommendations

### High priority

1. **Choose one MQTT deployment mode.**

   Either enable the local Mosquitto service for development or document the external ngrok broker as the required dependency. Avoid having the README, simulator, and Compose file use different broker/topic values.

2. **Align the simulator with the current schema.**

   Update `src/simulate_device.py` to publish the nested Wi-Fi payload expected by `storage.py`, or add a compatibility parser for the simulator's existing flat payload.

3. **Enable and provision Grafana consistently.**

   Uncomment the Grafana service, mount the data source configuration, and add dashboard provisioning if dashboards should be created automatically. Otherwise, document that dashboards must be imported manually.

4. **Move the database schema into migrations.**

   Creating a table from application startup works for a prototype, but a migration tool or versioned SQL directory is safer for schema changes and production deployment.

### Medium priority

5. **Use one dependency source.**

   Keep dependency versions in either `requirements.txt` or `pyproject.toml`, then generate the other when needed. Remove duplicate entries from `requirements.txt` and align the `psycopg` versions.

6. **Use `DB_TABLE` consistently or remove it.**

   The environment variable is read, but the SQL statements are hard-coded to `public.telemetry`. Either interpolate a validated identifier safely or remove the unused setting.

7. **Add health checks.**

   Add a TimescaleDB health check and make the application depend on service health rather than only container startup order.

8. **Avoid hard-coded credentials.**

   The current PostgreSQL password is `postgres` in multiple files. Use an environment file for development and secret management for deployment.

9. **Add tests for payload parsing.**

   Test valid Wi-Fi payloads, malformed JSON, missing `network`, missing `radios`, invalid numeric values, multiple radios, duplicate rows, and the simulator payload shape.

### Lower priority

10. **Improve logging around ignored messages.**

    Include the reason a payload was ignored and perhaps its topic or device identifier, while avoiding logging sensitive client data.

11. **Add a formal payload schema.**

    A JSON Schema or typed validation model would make the contract between devices, MQTT, storage, and dashboards explicit.

12. **Document the operational commands.**

    Add separate, verified instructions for local development, Docker-only execution, external MQTT usage, database inspection, and Grafana startup.

13. **Add `.env` handling documentation.**

    Explain whether the application should load a local `.env` file automatically or whether users must export the variables before starting it.

## 10. Recommended Target Development Setup

For a predictable local workflow, the project should eventually use this arrangement:

```text
Mosquitto container: localhost:1883
TimescaleDB container: localhost:5433
Grafana container: localhost:3000
Python consumer: local process or mqtt-server container
Simulator: publishes the same nested schema as real devices
Topic: devices/telemetry
```

The consumer and simulator should share the same topic and payload contract, while Grafana should be connected to the same TimescaleDB instance used by the consumer.
