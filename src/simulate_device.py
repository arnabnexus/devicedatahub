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
    timestamp = int(time.time())
    radios = []

    for radio_band, channel, frequency_mhz, bandwidth_mhz in [
        ("2.4GHz", random.choice([1, 6, 11]), random.choice([2412, 2437, 2462]), 20),
        ("5GHz", random.choice([36, 40, 44, 149]), random.choice([5180, 5200, 5220, 5745]), 80),
    ]:
        client_count = random.randint(0, 8)
        channel_utilization = round(random.uniform(15.0, 80.0), 1)
        avg_rssi = random.randint(-72, -35) if client_count else 0
        avg_snr = random.randint(20, 60) if client_count else 0
        clients = [
            {
                "macaddr": f"02:00:00:00:{counter:02X}:{client_index:02X}",
                "hostname": f"client-{client_index}",
                "ip_addr": f"192.168.1.{100 + client_index}",
                "rssi_dbm": avg_rssi,
                "snr_db": avg_snr,
                "tx_rate_mbps": round(random.uniform(50.0, 1200.0), 1),
                "rx_rate_mbps": round(random.uniform(50.0, 1200.0), 1),
                "tx_packets": random.randint(1000, 100000),
                "rx_packets": random.randint(1000, 100000),
                "tx_retries": random.randint(0, 1000),
                "tx_failed": random.randint(0, 100),
            }
            for client_index in range(1, client_count + 1)
        ]
        radios.append(
            {
                "radio": radio_band,
                "ifname": f"phy{len(radios)}-ap0",
                "radio_stats": {
                    "channel": channel,
                    "frequency_mhz": frequency_mhz,
                    "bandwidth_mhz": bandwidth_mhz,
                    "channel_utilization_pct": channel_utilization,
                    "tx_airtime_pct": round(random.uniform(0.0, 40.0), 1),
                    "rx_airtime_pct": round(random.uniform(0.0, 40.0), 1),
                    "cca_busy_pct": channel_utilization,
                    "noise_floor_dbm": random.randint(-100, -60),
                    "client_count": client_count,
                    "active_client_count": random.randint(0, client_count),
                    "avg_rssi_dbm": avg_rssi,
                    "min_rssi_dbm": avg_rssi - random.randint(0, 8) if client_count else 0,
                    "avg_snr_db": avg_snr,
                    "min_snr_db": avg_snr - random.randint(0, 8) if client_count else 0,
                    "avg_tx_rate_mbps": round(random.uniform(50.0, 1200.0), 1),
                    "avg_rx_rate_mbps": round(random.uniform(50.0, 1200.0), 1),
                    "tx_packets": random.randint(1000, 100000),
                    "rx_packets": random.randint(1000, 100000),
                    "tx_bytes": random.randint(100000, 10000000),
                    "rx_bytes": random.randint(100000, 10000000),
                    "tx_retries": random.randint(0, 1000),
                    "tx_failed": random.randint(0, 100),
                    "tx_airtime_client_pct": round(random.uniform(0.0, 40.0), 1),
                    "rx_airtime_client_pct": round(random.uniform(0.0, 40.0), 1),
                    "avg_mcs": round(random.uniform(1.0, 11.0), 1),
                    "min_mcs": random.randint(0, 11),
                    "avg_nss": round(random.uniform(1.0, 4.0), 1),
                    "weak_client_count": random.randint(0, client_count),
                    "neighbor_ap_count": random.randint(0, 12),
                    "strong_neighbor_ap_count": random.randint(0, 5),
                    "same_channel_ap_count": random.randint(0, 5),
                    "strong_same_channel_ap_count": random.randint(0, 3),
                    "obss_utilization_pct": round(random.uniform(0.0, 40.0), 1),
                    "interference_utilization_pct": round(random.uniform(0.0, 40.0), 1),
                },
                "clients": clients,
            }
        )

    payload = {
        "timestamp": timestamp,
        "schema_version": "1.0",
        "device_id": device["serial_number"],
        "network": [
            {
                "type": "wifi",
                "radios": radios,
            }
        ],
    }
    client.publish(topic, json.dumps(payload), qos=0)
    print(f"Published: {payload}")
    time.sleep(10)
