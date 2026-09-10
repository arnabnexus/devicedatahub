# Kubernetes Setup

This guide deploys the DeviceDataHub MQTT consumer with Helm and enables horizontal scaling.

For a local proof of concept using a Kubernetes cluster running in Docker, follow [kubernetespoc.md](kubernetespoc.md) first. It covers `.venv`, kind, the local image, Docker Compose dependencies, and the POC values file.

The Kubernetes deployment contains the stateless `mqtt-server` application. MQTT and TimescaleDB are treated as external dependencies because MQTT brokers and databases need their own persistence, clustering, and operational strategy. Grafana can be deployed separately or kept in Docker Compose.

## 1. Kubernetes Architecture

```text
MQTT broker (external or separately deployed)
                  |
                  v
      DeviceDataHub Deployment
       2+ mqtt-server Pods
                  |
                  v
   External TimescaleDB/PostgreSQL
                  |
                  v
              Grafana
```

The Deployment can run multiple consumer Pods. This is appropriate when the MQTT broker distributes messages between consumers, for example through a shared subscription or broker-side queue. With a normal MQTT subscription, multiple replicas may each receive the same messages depending on broker behavior. Confirm the broker's consumer-group/shared-subscription semantics before increasing replicas.

## 2. Files Added

- `deploy/helm/devicedatahub/Chart.yaml`: Helm chart metadata.
- `deploy/helm/devicedatahub/values.yaml`: Image, MQTT, database, resource, and scaling settings.
- `deploy/helm/devicedatahub/templates/deployment.yaml`: Runs the application Pods.
- `deploy/helm/devicedatahub/templates/hpa.yaml`: Scales Pods from CPU and memory metrics.
- `deploy/helm/devicedatahub/templates/secret.yaml`: Supplies database and MQTT credentials as Kubernetes Secret values.
- `deploy/helm/devicedatahub/templates/serviceaccount.yaml`: Creates a ServiceAccount without mounting a Kubernetes API token.

The application does not expose an HTTP server, so this chart does not create a Service or HTTP readiness probe. Its health is visible through Pod status and logs. Add an application health endpoint before adding HTTP probes.

## 3. Prerequisites

Install or have access to:

- Kubernetes cluster and `kubectl`.
- Helm 3.
- Docker or another OCI image builder.
- A reachable MQTT broker.
- A reachable TimescaleDB/PostgreSQL database.
- Metrics Server installed in the cluster for HPA resource metrics.

Check access:

```bash
kubectl cluster-info
kubectl get nodes
helm version
kubectl top nodes
```

`kubectl top nodes` should return metrics. If it reports that Metrics Server is unavailable, the application can still deploy, but the HPA cannot make scaling decisions.

## 4. Build and Push the Application Image

The image is built from the repository `Dockerfile`. Replace the registry and organization with values available to your cluster.

```bash
export IMAGE_REPOSITORY=ghcr.io/your-org/devicedatahub-mqtt-server
export IMAGE_TAG=0.1.0

docker build -t "${IMAGE_REPOSITORY}:${IMAGE_TAG}" .
docker push "${IMAGE_REPOSITORY}:${IMAGE_TAG}"
```

Update the image values before installation:

```yaml
image:
  repository: ghcr.io/your-org/devicedatahub-mqtt-server
  tag: "0.1.0"
  pullPolicy: IfNotPresent
```

For a private registry, create an image pull secret and reference it in `values.yaml`:

```bash
kubectl create secret docker-registry registry-credentials \
  --docker-server=ghcr.io \
  --docker-username="$GITHUB_USER" \
  --docker-password="$GITHUB_TOKEN" \
  --namespace=devicedatahub
```

```yaml
image:
  pullSecrets:
    - name: registry-credentials
```

Do not put registry tokens in `values.yaml` or commit them to Git.

### Minikube-only image option

For local Minikube testing, the image can be loaded directly instead of pushed to a registry:

```bash
minikube image load "${IMAGE_REPOSITORY}:${IMAGE_TAG}"
```

Use `image.pullPolicy: IfNotPresent` with this option.

## 5. Configure `values.yaml`

Edit `deploy/helm/devicedatahub/values.yaml` for the target environment.

Required settings:

```yaml
image:
  repository: ghcr.io/your-org/devicedatahub-mqtt-server
  tag: "0.1.0"

mqtt:
  host: mqtt.example.com
  port: 1883
  topic: devices/telemetry
  clientId: telemetry-consumer

postgres:
  host: timescaledb.example.com
  port: 5432
  database: telemetry
  user: postgres
  password: change-me
```

For the current Compose external-broker configuration, the equivalent values would be the real reachable broker hostname, port `24839`, and topic `weh-device/network`. Do not copy an expired or unavailable tunnel endpoint into production values.

The application creates the telemetry table on startup. The database user therefore needs permission to create the table and TimescaleDB hypertable, or the schema must be created separately before deployment.

## 6. Protect Credentials

The chart converts `postgres.password`, `mqtt.username`, and `mqtt.password` into a Kubernetes Secret. The default values are placeholders and must be replaced.

For a first deployment, pass secrets without putting them in shell history where possible, or use a separate ignored values file:

```bash
cp deploy/helm/devicedatahub/values.yaml /tmp/devicedatahub-values.yaml
chmod 600 /tmp/devicedatahub-values.yaml
```

Edit the temporary file with the real values, then install using that file. For production, prefer an external secret manager such as External Secrets Operator, a cloud secret manager, or a pre-created Kubernetes Secret. Also consider changing the chart to reference an existing Secret rather than templating credentials into the Helm release.

## 7. Install the Helm Release

Create a namespace:

```bash
kubectl create namespace devicedatahub
```

Validate the chart locally:

```bash
helm lint deploy/helm/devicedatahub
helm template devicedatahub deploy/helm/devicedatahub \
  --namespace devicedatahub \
  --set image.repository="$IMAGE_REPOSITORY" \
  --set image.tag="$IMAGE_TAG"
```

Install or upgrade:

```bash
helm upgrade --install devicedatahub deploy/helm/devicedatahub \
  --namespace devicedatahub \
  --create-namespace \
  --set image.repository="$IMAGE_REPOSITORY" \
  --set image.tag="$IMAGE_TAG"
```

For a real environment, provide a separate values file:

```bash
helm upgrade --install devicedatahub deploy/helm/devicedatahub \
  --namespace devicedatahub \
  --create-namespace \
  --values deploy/helm/devicedatahub/values.yaml \
  --values values.production.yaml
```

## 8. Verify the Deployment

```bash
kubectl get deployments,pods,hpa -n devicedatahub
kubectl rollout status deployment/devicedatahub-devicedatahub -n devicedatahub
kubectl logs deployment/devicedatahub-devicedatahub -n devicedatahub --tail=100
```

Expected application startup logs include database initialization and MQTT connection messages. If the database is unreachable, the application retries database initialization. If MQTT is unreachable, the Pod exits and Kubernetes restarts it.

Inspect the rendered configuration without exposing secret values in shared output:

```bash
kubectl describe deployment devicedatahub-devicedatahub -n devicedatahub
kubectl get secret devicedatahub-devicedatahub -n devicedatahub
```

## 9. Scaling

### Manual scaling

Set the desired number of replicas immediately:

```bash
kubectl scale deployment/devicedatahub-devicedatahub \
  --replicas=4 \
  --namespace=devicedatahub
```

Check the result:

```bash
kubectl get pods -n devicedatahub -l app.kubernetes.io/name=devicedatahub
```

Manual scaling is temporary if Helm is later upgraded with a different `replicaCount`.

### Horizontal Pod Autoscaler

Autoscaling is enabled in `values.yaml`:

```yaml
autoscaling:
  enabled: true
  minReplicas: 2
  maxReplicas: 10
  targetCPUUtilizationPercentage: 70
  targetMemoryUtilizationPercentage: 80
```

The HPA uses the resource requests from the same values file. Kubernetes calculates utilization relative to those requests. Inspect it with:

```bash
kubectl get hpa -n devicedatahub
kubectl describe hpa devicedatahub-devicedatahub -n devicedatahub
kubectl top pods -n devicedatahub
```

If there is no load, the HPA remains at `minReplicas`. To scale based on MQTT message rate or backlog instead of CPU/memory, expose a Prometheus metric and use a custom or external metric adapter.

## 10. Updating the Image

Build and push a new immutable tag:

```bash
export IMAGE_TAG=0.1.1
docker build -t "${IMAGE_REPOSITORY}:${IMAGE_TAG}" .
docker push "${IMAGE_REPOSITORY}:${IMAGE_TAG}"
```

Upgrade the release:

```bash
helm upgrade devicedatahub deploy/helm/devicedatahub \
  --namespace devicedatahub \
  --set image.repository="$IMAGE_REPOSITORY" \
  --set image.tag="$IMAGE_TAG"
```

Watch the rolling update:

```bash
kubectl rollout status deployment/devicedatahub-devicedatahub -n devicedatahub
```

Use immutable version tags rather than repeatedly deploying `latest`; this makes rollback and incident diagnosis reliable.

## 11. Rollback and Removal

Show release history:

```bash
helm history devicedatahub --namespace devicedatahub
```

Roll back:

```bash
helm rollback devicedatahub REVISION --namespace devicedatahub
kubectl rollout status deployment/devicedatahub-devicedatahub -n devicedatahub
```

Remove the application:

```bash
helm uninstall devicedatahub --namespace devicedatahub
```

The Helm uninstall removes the Deployment, HPA, ServiceAccount, and application Secret. It does not remove an external MQTT broker or external TimescaleDB.

## 12. Important Production Recommendations

1. Use an external or highly available TimescaleDB deployment with backups. Do not run a single database Pod just because the consumer is scalable.
2. Use a stable MQTT broker endpoint and configure shared subscriptions or consumer groups before running multiple consumers.
3. Replace placeholder passwords and avoid committing production secrets.
4. Add a readiness/health endpoint to the Python application so Kubernetes can distinguish startup, connection failure, and healthy operation.
5. Add database migrations instead of relying only on application startup schema creation.
6. Add PodDisruptionBudget and topology spread constraints when running more than one replica.
7. Monitor MQTT connection status, message rate, database insert failures, and consumer restarts.
8. Use a custom HPA metric based on MQTT backlog or message throughput when CPU and memory are not reliable indicators of workload.
