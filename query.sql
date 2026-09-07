SELECT * FROM public."telemetry";

INSERT INTO public.telemetry (
	timestamp,
	schema_version,
	device_id,
	network_type,
	radio,
	ifname,
	channel,
	frequency_mhz,
	bandwidth_mhz,
	channel_utilization_pct,
	tx_airtime_pct,
	rx_airtime_pct,
	cca_busy_pct,
	noise_floor_dbm,
	client_count,
	active_client_count,
	avg_rssi_dbm,
	min_rssi_dbm,
	avg_snr_db,
	min_snr_db,
	avg_tx_rate_mbps,
	avg_rx_rate_mbps,
	tx_packets,
	rx_packets,
	tx_bytes,
	rx_bytes,
	tx_retries,
	tx_failed,
	tx_airtime_client_pct,
	rx_airtime_client_pct,
	avg_mcs,
	min_mcs,
	avg_nss,
	weak_client_count,
	neighbor_ap_count,
	strong_neighbor_ap_count,
	same_channel_ap_count,
	strong_same_channel_ap_count,
	obss_utilization_pct,
	interference_utilization_pct,
	clients
) VALUES
(
	'2026-09-05T16:28:31Z', '1.0', 'WEH-587BE924EF9B', 'wifi', '5GHz', 'phy1-ap0',
	36, 5180, 80, 7, 0, 6, 7, -92, 1, 1, -39, -39, 53, 53, 1134, 1200,
	4874, 4152, 4096916, 995419, 840, 840, 0, 6, 11, 11, 2, 0, 8, 2, 8, 2, 0, 0,
	'[{"macaddr":"A2:AC:D7:5C:0B:3C","hostname":"","ip_addr":"192.168.1.166","rssi_dbm":-39,"snr_db":53,"tx_rate_mbps":1134,"rx_rate_mbps":1200,"tx_packets":4874,"rx_packets":4152,"tx_retries":840,"tx_failed":840}]'::jsonb
),
(
	'2026-09-05T16:28:31Z', '1.0', 'WEH-587BE924EF9B', 'wifi', '2.4GHz', 'phy0-ap0',
	1, 2412, 20, 50, 0, 45, 50, -89, 0, 0, 0, 0, 0, 0, 0, 0,
	0, 0, 0, 0, 0, 0, 0, 45, 0, 0, 0, 0, 17, 2, 13, 0, 5, 5,
	'[]'::jsonb
)
ON CONFLICT (timestamp, device_id, radio) DO NOTHING;

INSERT INTO public.telemetry (
	timestamp, schema_version, device_id, network_type, radio, ifname,
	channel, frequency_mhz, bandwidth_mhz, channel_utilization_pct,
	tx_airtime_pct, rx_airtime_pct, cca_busy_pct, noise_floor_dbm,
	client_count, active_client_count, avg_rssi_dbm, min_rssi_dbm,
	avg_snr_db, min_snr_db, avg_tx_rate_mbps, avg_rx_rate_mbps,
	tx_packets, rx_packets, tx_bytes, rx_bytes, tx_retries, tx_failed,
	tx_airtime_client_pct, rx_airtime_client_pct, avg_mcs, min_mcs, avg_nss,
	weak_client_count, neighbor_ap_count, strong_neighbor_ap_count,
	same_channel_ap_count, strong_same_channel_ap_count, obss_utilization_pct,
	interference_utilization_pct, clients
) VALUES (
	'2026-09-05 14:01:48+00', '1.0', 'WEH-587BE924EF9B', 'wifi', '5GHz', 'phy1-ap0',
	36, 5180, 80, 3, 0, 2, 3, -92, 1, 1, -37, -37, 55, 55, 680, 24,
	41153, 16536, 45398799, 4383509, 100, 1405, 0, 2, 7, 7, 2, 0, 5, 0, 4, 0, 0, 0,
	'[{"snr_db":55,"ip_addr":"192.168.1.166","macaddr":"A2:AC:D7:5C:0B:3C","hostname":"","rssi_dbm":-37,"tx_failed":1405,"rx_packets":16536,"tx_packets":41153,"tx_retries":1405,"rx_rate_mbps":24,"tx_rate_mbps":680}]'::jsonb
)
ON CONFLICT (timestamp, device_id, radio) DO NOTHING;


