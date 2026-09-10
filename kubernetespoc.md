# Local Kubernetes POC

This guide runs the complete DeviceDataHub POC in Kubernetes with `kind` and Helm. It deploys Mosquitto, TimescaleDB, the DeviceDataHub MQTT consumer, and Grafana as Kubernetes workloads. The Python simulator is not used.

The local POC uses this arrangement:

```text
External MQTT broker: 0.tcp.in.ngrok.io:24839
          |
          v
DeviceDataHub Deployment: mqtt-server Pods
          |
          v
TimescaleDB StatefulSet: timescaledb:5432
          |
          v
Grafana Service: grafana:3000
```

The Kubernetes cluster itself uses the official `kindest/node` Kubernetes node image. The application image is built from this repository's `Dockerfile` and loaded directly into kind, so a container registry is not required.

## 1. What Runs Where

- kind runs Kubernetes nodes as Docker containers.
- Helm installs every application component into the cluster.
- The MQTT consumer connects to the external ngrok MQTT broker.
- TimescaleDB runs as a single-replica StatefulSet with a PVC.
- DeviceDataHub runs as a Kubernetes Deployment.
- Grafana runs as a Kubernetes Deployment with a PVC and provisioned datasource.
- `values.poc.yaml` enables the complete local stack.
- Two `mqtt-server` replicas use a Kubernetes Lease for active-passive failover; only the lease holder connects to MQTT.

Do not start `docker compose` for this POC. The Kubernetes chart owns MQTT, TimescaleDB, the consumer, and Grafana.

## 2. Prerequisites

Install these tools:

- Docker Engine or Docker Desktop.
- `kind`.
- `kubectl`.
- Helm 3.
Check them:

```bash
docker --version
kind version
kubectl version --client
helm version
```

The CLI tools are not Python packages and are not installed by `pip`. The comments in `requirements.txt` document them for the POC, but install them as binaries using your operating system package manager or the official Kubernetes/Helm/kind installation instructions.

For Linux, the official binary-install pattern is:

```bash
# Install kubectl, Helm 3, and kind using their official instructions.
# Then verify:
kubectl version --client
helm version
kind version
```

No virtual environment or simulator is required for this Kubernetes-only POC.

## 3. Create the Kubernetes-in-Docker Cluster

The cluster configuration is in `deploy/kind/kind-config.yaml`. Create it with the official Kubernetes node image:

```bash
kind create cluster \
  --name devicedatahub \
  --image kindest/node:v1.32.2 \
  --config deploy/kind/kind-config.yaml
```

Verify the cluster:

```bash
kubectl cluster-info --context kind-devicedatahub
kubectl get nodes --context kind-devicedatahub
```

Use this context for all following commands:

```bash
kubectl config use-context kind-devicedatahub
```

The `kindest/node` image contains the Kubernetes node components. It is not the DeviceDataHub application image; the application image is built separately in the next step.

## 4. Build and Load the Application Image

Build the same image used by the Dockerfile:

```bash
docker build -t devicedatahub-mqtt-server:poc .
```

Load it into the kind cluster:

```bash
kind load docker-image devicedatahub-mqtt-server:poc \
  --name devicedatahub
```

Confirm that kind can see the image:

```bash
b8docker exec devicedatahub-worker crictl images | grep devicedatahub-mqtt-server
```

If the worker container name differs, list the nodes first:

```bash
docker ps --format '{{.Names}}'
```

## 5. Install the Complete Helm Release

The POC values file is [deploy/helm/devicedatahub/values.poc.yaml](deploy/helm/devicedatahub/values.poc.yaml). It enables the complete stack:

```text
Application image: devicedatahub-mqtt-server:poc
MQTT service: mqtt-broker:1883
Database service: timescaledb:5432
Grafana service: grafana:3000
Consumer replicas: 2 (one active, one standby)
HPA: disabled
```

Create the namespace and install:

```bash
kubectl create namespace devicedatahub

kubectl create configmap wifi-radio-health-dashboard \
  --from-file=wifi_radio_health_grafana.json=grafana/wifi_radio_health_grafana.json \
  --namespace=devicedatahub \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install devicedatahub \
  deploy/helm/devicedatahub \
  --namespace devicedatahub \
  --values deploy/helm/devicedatahub/values.poc.yaml
```

Check the generated resources:

```bash
kubectl get deployment,pods,hpa -n devicedatahub
kubectl rollout status deployment/devicedatahub-devicedatahub -n devicedatahub
```

## 6. Verify the Complete Stack

Check all workloads:

```bash
kubectl get pods,svc,pvc -n devicedatahub
```

Watch the consumer logs:

```bash
kubectl logs -f deployment/devicedatahub-devicedatahub \
  -n devicedatahub
```

The consumer should connect to `0.tcp.in.ngrok.io:24839` and initialize the database at `timescaledb:5432`. This POC has no simulator. The external broker must be running and publishing to `weh-device/network` if you need to create rows.

The two consumer Pods coordinate through the Kubernetes Lease named `devicedatahub-mqtt-server`. Only the current Lease holder connects to MQTT. If the active Pod stops, the standby Pod acquires the Lease after the 15-second lease duration and connects to the same topic.

## 7. Open Grafana

Grafana is exposed as a Kubernetes `NodePort` service. The most portable local command is:

```bash
kubectl port-forward service/grafana 3000:3000 -n devicedatahub
```

Open http://localhost:3000 and sign in with:

```text
Username: admin
Password: admin
```

The TimescaleDB datasource and the `Wi-Fi Radio Health & NOC Operations — TimescaleDB` dashboard are provisioned automatically. The dashboard ConfigMap is created from `grafana/wifi_radio_health_grafana.json` before Helm installs Grafana.

To update the dashboard after editing the JSON file:

```bash
kubectl create configmap wifi-radio-health-dashboard \
  --from-file=wifi_radio_health_grafana.json=grafana/wifi_radio_health_grafana.json \
  --namespace=devicedatahub \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/devicedatahub-devicedatahub-grafana \
  --namespace=devicedatahub
```

## 8. Check the Database

Port-forward TimescaleDB when you want to inspect it from the host:

```bash
kubectl port-forward service/timescaledb 5433:5432 -n devicedatahub

PGPASSWORD=postgres psql \
  --host=localhost \
  --port=5433 \
  --username=postgres \
  --dbname=telemetry \
  -c 'SELECT timestamp, device_id, radio, client_count FROM public.telemetry ORDER BY timestamp DESC LIMIT 10;'
```

The table is initialized by the Kubernetes consumer when it starts. If the table is missing, inspect the consumer logs first.

## 9. Try Scaling

The POC runs two consumer replicas for active-passive failover. Test the failover behavior:

```bash
kubectl get lease devicedatahub-mqtt-server -n devicedatahub -o yaml

kubectl delete pod \
  "$(kubectl get pods -n devicedatahub \
    -l app.kubernetes.io/name=devicedatahub \
    -o jsonpath='{.items[0].metadata.name}')" \
  --namespace=devicedatahub

kubectl get pods -n devicedatahub -w
```

The replacement Pod should become the Lease holder and connect to MQTT. The existing topic does not change, and the standby Pod does not subscribe while it is waiting.

To change the number of failover candidates:

```bash
kubectl scale deployment/devicedatahub-devicedatahub \
  --replicas=3 \
  --namespace=devicedatahub
```

Only one of the replicas remains active. This is failover capacity, not parallel MQTT throughput.

To test the HPA configuration, install with an override:

```bash
helm upgrade devicedatahub \
  deploy/helm/devicedatahub \
  --namespace devicedatahub \
  --values deploy/helm/devicedatahub/values.poc.yaml \
  --set autoscaling.enabled=true \
  --set autoscaling.minReplicas=1 \
  --set autoscaling.maxReplicas=3
```

Metrics Server must be installed for the HPA to show CPU and memory values:

```bash
kubectl top pods -n devicedatahub
kubectl get hpa -n devicedatahub
```

## 10. Troubleshooting

### Pod is `ImagePullBackOff`

The image was not loaded into kind, or the image name/tag does not match the POC values:

```bash
kind load docker-image devicedatahub-mqtt-server:poc --name devicedatahub
kubectl describe pod -n devicedatahub -l app.kubernetes.io/name=devicedatahub
```

### Pod is restarting

Read the logs:

```bash
kubectl logs deployment/devicedatahub-devicedatahub -n devicedatahub --previous
```

Common causes are an unreachable MQTT broker, an unreachable database, or an incorrect topic.

### MQTT connection refused

Confirm the external ngrok MQTT endpoint is active and reachable:

```bash
kubectl logs deployment/devicedatahub-devicedatahub -n devicedatahub
```

### Database connection refused

Confirm the Kubernetes database is ready:

```bash
kubectl get pod,service -n devicedatahub -l app.kubernetes.io/name=timescaledb
kubectl logs statefulset/devicedatahub-devicedatahub-timescaledb -n devicedatahub
```

From inside Kubernetes, use `timescaledb:5432`, not `localhost:5433`.

## 11. Cleanup

Remove the Helm release and namespace:

```bash
helm uninstall devicedatahub --namespace devicedatahub
kubectl delete namespace devicedatahub
```

Delete the kind cluster:

```bash
kind delete cluster --name devicedatahub
```

The Kubernetes PVCs remain unless explicitly deleted. Delete them only when you want to remove the POC database and Grafana data:

```bash
kubectl delete pvc --all -n devicedatahub
```
