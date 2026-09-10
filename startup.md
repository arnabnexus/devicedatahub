# DeviceDataHub Local Kubernetes Startup

This runbook starts the complete DeviceDataHub proof of concept in a local `kind` Kubernetes cluster.

The MQTT broker is **external** and Mosquitto is intentionally not started.

```text
External MQTT broker: 0.tcp.in.ngrok.io:24839
          |
          v
Two mqtt-server Pods with Kubernetes Lease failover
          |
          v
TimescaleDB StatefulSet
          |
          v
Grafana Deployment with the Wi-Fi dashboard
```

## 1. Open a Terminal and Enter the Repository

Log in to the Linux machine or open your terminal, then run:

```bash
cd ~/workspaces/devicedatahub
```

Confirm the repository is correct:

```bash
pwd
ls Dockerfile docker-compose.yml deploy/helm/devicedatahub
```

## 2. Activate or Create the Python Virtual Environment

The Kubernetes application runs in Docker, but the virtual environment is useful for project dependencies and local Python checks.

Create it if it does not exist:

```bash
python3 -m venv .venv
```

Activate it:

```bash
source .venv/bin/activate
```

Install the Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

The MQTT simulator is not used in this runbook.

## 3. Verify Required Tools

The required commands are standalone tools, not Python packages:

```bash
docker --version
kind version
kubectl version --client
helm version
```

Docker must be running because `kind` creates Kubernetes nodes as Docker containers.

If `kubectl`, `kind`, or Helm is not installed, install them before continuing. A local user installation that does not require `sudo` can be used, for example:

```bash
mkdir -p "$HOME/.local/bin"

# kubectl
curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
chmod +x kubectl
mv kubectl "$HOME/.local/bin/kubectl"

# kind
curl -Lo kind https://kind.sigs.k8s.io/dl/latest/kind-linux-amd64
chmod +x kind
mv kind "$HOME/.local/bin/kind"

# Helm 3
curl https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash

export PATH="$HOME/.local/bin:$PATH"
```

For a private container registry, log in before pulling private images:

```bash
docker login
```

This POC uses a locally built application image and public dependency images, so a registry login is normally not required.

## 4. Create or Select the kind Cluster

Create the Kubernetes-in-Docker cluster using the repository configuration:

```bash
kind create cluster \
  --name devicedatahub \
  --image kindest/node:v1.32.2 \
  --config deploy/kind/kind-config.yaml
```

If the cluster already exists, do not run the create command again. Select its context instead:

```bash
kubectl config use-context kind-devicedatahub
kubectl cluster-info
kubectl get nodes
```

Expected nodes are one control-plane node and one worker node.

## 5. Build the DeviceDataHub Image

Build the image from the repository Dockerfile. The final `.` is required because it supplies the Docker build context:

```bash
docker build -t devicedatahub-mqtt-server:poc .
```

Confirm the image exists locally:

```bash
docker image inspect devicedatahub-mqtt-server:poc >/dev/null && echo "image ready"
```

## 6. Load the Image into kind

The kind nodes cannot automatically see images in the host Docker image list. Load the image into the cluster:

```bash
kind load docker-image devicedatahub-mqtt-server:poc \
  --name devicedatahub
```

The command should report that the image was loaded into the worker and control-plane nodes.

## 7. Create the Grafana Dashboard ConfigMap

The Helm chart provisions the Grafana datasource and dashboard provider. Create the dashboard ConfigMap from the repository JSON before installing the chart:

```bash
kubectl create namespace devicedatahub \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap wifi-radio-health-dashboard \
  --from-file=wifi_radio_health_grafana.json=grafana/wifi_radio_health_grafana.json \
  --namespace=devicedatahub \
  --dry-run=client -o yaml | kubectl apply -f -
```

Confirm it exists:

```bash
kubectl get configmap wifi-radio-health-dashboard -n devicedatahub
```

## 8. Install the Complete Helm Release

The POC values file configures:

- External MQTT: `0.tcp.in.ngrok.io:24839`
- MQTT topic: `weh-device/network`
- Mosquitto: disabled
- TimescaleDB: enabled in Kubernetes
- Grafana: enabled in Kubernetes
- Consumer replicas: 2
- Kubernetes Lease failover: enabled

Install or upgrade the release:

```bash
helm upgrade --install devicedatahub \
  deploy/helm/devicedatahub \
  --namespace devicedatahub \
  --values deploy/helm/devicedatahub/values.poc.yaml
```

Check the release:

```bash
helm status devicedatahub --namespace devicedatahub
```

## 9. Wait for Kubernetes Components

Watch all Pods:

```bash
kubectl get pods -n devicedatahub -w
```

In another terminal, wait for the main Deployments:

```bash
kubectl rollout status deployment/devicedatahub-devicedatahub \
  --namespace=devicedatahub \
  --timeout=180s

kubectl rollout status deployment/devicedatahub-devicedatahub-grafana \
  --namespace=devicedatahub \
  --timeout=180s
```

Check the final state:

```bash
kubectl get pods,services,pvc -n devicedatahub
```

Expected application components:

```text
2 mqtt-server Pods: Running
1 TimescaleDB Pod: Running
1 Grafana Pod: Running
No mqtt-broker Pod or Service
```

## 10. Verify the MQTT Consumer

Read both consumer Pods' logs:

```bash
for pod in $(kubectl get pods -n devicedatahub \
  -l app.kubernetes.io/name=devicedatahub \
  -o jsonpath='{.items[*].metadata.name}'); do
  echo "--- $pod"
  kubectl logs "$pod" -n devicedatahub --tail=30
 done
```

The active Pod should show messages similar to:

```text
Acquired leader lease 'devicedatahub-mqtt-server'
Connecting to broker at 0.tcp.in.ngrok.io:24839
```

The standby Pod should show:

```text
Waiting for leader lease 'devicedatahub-mqtt-server'
```

Check the Lease directly:

```bash
kubectl get lease devicedatahub-mqtt-server \
  --namespace=devicedatahub \
  -o jsonpath='holder={.spec.holderIdentity}{" renew="}{.spec.renewTime}{"\n"}'
```

Only the Lease holder should connect to the external MQTT broker. The MQTT topic remains `weh-device/network`.

## 11. Open Grafana

Start the Grafana port-forward in a separate terminal and leave that terminal running:

```bash
kubectl port-forward service/grafana 3000:3000 \
  --namespace=devicedatahub
```

This maps the Kubernetes Grafana Service to your local machine:

```text
localhost:3000 -> grafana:3000
```

Open:

```text
http://localhost:3000
```

Login:

```text
Username: admin
Password: admin
```

Open the provisioned dashboard:

```text
http://localhost:3000/d/wifi-radio-health-tsdb/b950652
```

The chart provisions:

- TimescaleDB datasource
- `Wi-Fi Radio Health & NOC Operations — TimescaleDB` dashboard

## 12. Check TimescaleDB

Use another separate terminal and forward PostgreSQL to the host. Keep this terminal running while using SQLTools or `psql`:

```bash
kubectl port-forward service/timescaledb 5433:5432 \
  --namespace=devicedatahub
```

This maps the Kubernetes database Service to your local machine:

```text
localhost:5433 -> timescaledb:5432
```

SQLTools connection settings:

```text
Host: localhost
Port: 5433
Database: telemetry
Username: postgres
Password: postgres
```

For the ML service running in a separate Docker container, expose the
port-forward on the Docker host interface instead:

```bash
kubectl port-forward \
  --address 0.0.0.0 \
  service/timescaledb 5433:5432 \
  --namespace=devicedatahub
```

Configure the ML container with:

```text
DB_HOST=host.docker.internal
DB_PORT=5433
DB_NAME=telemetry
DB_USER=postgres
DB_PASSWORD=postgres
```

On Linux Docker Engine, add this to the ML service in its Compose file so
`host.docker.internal` resolves to the Docker host:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

Only one port-forward can listen on host port `5433`. Stop an existing
`kubectl port-forward service/timescaledb 5433:5432` process before starting
the `--address 0.0.0.0` version.

If `psql` is installed, query telemetry from another terminal:

```bash
PGPASSWORD=postgres psql \
  --host=localhost \
  --port=5433 \
  --username=postgres \
  --dbname=telemetry \
  -c 'SELECT timestamp, device_id, radio, client_count FROM public.telemetry ORDER BY timestamp DESC LIMIT 10;'
```

The application creates the `public.telemetry` table when it starts. The external MQTT broker must publish valid Wi-Fi telemetry for new rows to appear.

## 13. Test Consumer Failover

The two `mqtt-server` replicas use the Kubernetes Lease named `devicedatahub-mqtt-server`. Only one replica is active; the other is standby.

### 13.1 Record the current leader

```bash
LEADER=$(kubectl get lease devicedatahub-mqtt-server \
  --namespace=devicedatahub \
  -o jsonpath='{.spec.holderIdentity}')

echo "Current leader: $LEADER"
```

Record the current Pods:

```bash
kubectl get pods -n devicedatahub \
  -l app.kubernetes.io/name=devicedatahub \
  -o wide
```

### 13.2 Delete the active Pod

```bash
kubectl delete pod "$LEADER" --namespace=devicedatahub
```

Kubernetes will create a replacement Pod automatically because the Deployment still requires two replicas.

### 13.3 Watch the replacement

```bash
kubectl get pods -n devicedatahub \
  -l app.kubernetes.io/name=devicedatahub -w
```

In another terminal, watch the Lease:

```bash
kubectl get lease devicedatahub-mqtt-server \
  --namespace=devicedatahub -w
```

After the old leader disappears, the standby or replacement Pod should acquire the Lease. The normal lease duration is 15 seconds.

### 13.4 Confirm failover logs

```bash
for pod in $(kubectl get pods -n devicedatahub \
  -l app.kubernetes.io/name=devicedatahub \
  -o jsonpath='{.items[*].metadata.name}'); do
  echo "--- $pod"
  kubectl logs "$pod" -n devicedatahub --tail=30 | \
    grep -E 'Acquired|Waiting|Connecting|Disconnected|lease'
 done
```

Expected result:

```text
Old leader: terminated
Standby or replacement: Acquired leader lease
New leader: Connecting to broker at 0.tcp.in.ngrok.io:24839
Replica count: 2
MQTT topic: unchanged
```

The failover is active-passive. Increasing replicas gives more failover candidates, not parallel MQTT throughput:

```bash
kubectl scale deployment/devicedatahub-devicedatahub \
  --replicas=3 \
  --namespace=devicedatahub
```

## 14. Refresh the Grafana Dashboard

After editing `grafana/wifi_radio_health_grafana.json`, update the ConfigMap and restart Grafana:

```bash
kubectl create configmap wifi-radio-health-dashboard \
  --from-file=wifi_radio_health_grafana.json=grafana/wifi_radio_health_grafana.json \
  --namespace=devicedatahub \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl rollout restart deployment/devicedatahub-devicedatahub-grafana \
  --namespace=devicedatahub
```

## 15. Stop or Clean Up

Stop the local port-forward terminals with `Ctrl+C`.

Remove the Helm-managed resources:

```bash
helm uninstall devicedatahub --namespace=devicedatahub
kubectl delete namespace devicedatahub
```

Delete the local kind cluster:

```bash
kind delete cluster --name devicedatahub
```

The namespace deletion removes the POC PVCs and their TimescaleDB/Grafana data. The external MQTT broker is not affected.

## 16. Quick Restart After the First Setup

Once the tools and kind cluster already exist, the shorter restart sequence is:

```bash
cd ~/workspaces/devicedatahub
source .venv/bin/activate
kubectl config use-context kind-devicedatahub

docker build -t devicedatahub-mqtt-server:poc .
kind load docker-image devicedatahub-mqtt-server:poc --name devicedatahub

kubectl create configmap wifi-radio-health-dashboard \
  --from-file=wifi_radio_health_grafana.json=grafana/wifi_radio_health_grafana.json \
  --namespace=devicedatahub \
  --dry-run=client -o yaml | kubectl apply -f -

helm upgrade --install devicedatahub \
  deploy/helm/devicedatahub \
  --namespace=devicedatahub \
  --values deploy/helm/devicedatahub/values.poc.yaml
```
