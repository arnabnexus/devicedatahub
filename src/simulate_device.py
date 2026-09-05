import json
import os
import random
import time

import paho.mqtt.client as mqtt

broker_host = os.getenv("MQTT_BROKER_HOST", "localhost")
broker_port = int(os.getenv("MQTT_BROKER_PORT", "1883"))
topic = os.getenv("MQTT_TOPIC", "devices/telemetry")
client_id = os.getenv("MQTT_CLIENT_ID", "device-simulator")

# Keep the simulator to a small set of AP devices for now.
devices = [
    {
        "ap_mac": "00:2B:67:89:AB:CD",
        "serial_number": "WLAN-AP-98765",
        "firmware_version": "v4.2.1-build104",
    },
    {
        "ap_mac": "00:1A:2B:3C:4D:5E",
        "serial_number": "WLAN-AP-11223",
        "firmware_version": "v4.2.2-build118",
    },
    {
        "ap_mac": "00:88:5F:10:22:33",
        "serial_number": "WLAN-AP-44556",
        "firmware_version": "v4.3.0-build127",
    },
    {
        "ap_mac": "00:14:22:99:AA:BB",
        "serial_number": "WLAN-AP-77890",
        "firmware_version": "v4.3.1-build133",
    },
]

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
client.connect(broker_host, broker_port, 60)

counter = 0
while True:
    counter += 1
    device = devices[(counter - 1) % len(devices)]
    payload = {
        "timestamp": int(time.time()),
        "ap_mac": device["ap_mac"],
        "serial_number": device["serial_number"],
        "firmware_version": device["firmware_version"],
        "uptime_seconds": 345600 + counter * 60,
        "cpu_utilization_pct": round(random.uniform(12.0, 68.0), 1),
        "memory_utilization_pct": round(random.uniform(28.0, 76.0), 1),
        "connected_clients": random.randint(10, 60),
        "radio_band": random.choice(["2.4GHz", "5GHz"]),
        "channel": random.choice([1, 6, 11, 36, 40, 44, 149]),
        "channel_utilization_pct": round(random.uniform(15.0, 80.0), 1),
        "noise_floor_dbm": random.randint(-100, -60),
    }
    client.publish(topic, json.dumps(payload), qos=0)
    print(f"Published: {payload}")
    time.sleep(10)
