import logging
import socket
from datetime import datetime, timedelta, timezone

from kubernetes import client, config
from kubernetes.client.rest import ApiException

logger = logging.getLogger(__name__)


class KubernetesLease:
    def __init__(self, name: str, namespace: str, identity: str, duration_seconds: int = 15) -> None:
        config.load_incluster_config()
        self.api = client.CoordinationV1Api()
        self.name = name
        self.namespace = namespace
        self.identity = identity or socket.gethostname()
        self.duration_seconds = duration_seconds

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _is_expired(self, lease: client.V1Lease, now: datetime) -> bool:
        spec = lease.spec
        if not spec or not spec.renew_time:
            return True
        duration = spec.lease_duration_seconds or self.duration_seconds
        return now >= spec.renew_time + timedelta(seconds=duration)

    def try_acquire_or_renew(self) -> bool:
        now = self._now()
        try:
            lease = self.api.read_namespaced_lease(self.name, self.namespace)
        except ApiException as exc:
            if exc.status != 404:
                logger.warning("Could not read leader lease: %s", exc)
                return False
            body = client.V1Lease(
                metadata=client.V1ObjectMeta(name=self.name, namespace=self.namespace),
                spec=client.V1LeaseSpec(
                    holder_identity=self.identity,
                    lease_duration_seconds=self.duration_seconds,
                    acquire_time=now,
                    renew_time=now,
                ),
            )
            try:
                self.api.create_namespaced_lease(self.namespace, body)
                logger.info("Acquired leader lease '%s'", self.name)
                return True
            except ApiException as create_exc:
                if create_exc.status != 409:
                    logger.warning("Could not create leader lease: %s", create_exc)
                return False

        if lease.spec and lease.spec.holder_identity != self.identity and not self._is_expired(lease, now):
            return False

        spec = client.V1LeaseSpec(
            holder_identity=self.identity,
            lease_duration_seconds=self.duration_seconds,
            acquire_time=(
                lease.spec.acquire_time
                if lease.spec and lease.spec.holder_identity == self.identity
                else now
            ),
            renew_time=now,
        )
        body = {
            "spec": {
                "holderIdentity": spec.holder_identity,
                "leaseDurationSeconds": spec.lease_duration_seconds,
                "acquireTime": spec.acquire_time.isoformat(),
                "renewTime": spec.renew_time.isoformat(),
            }
        }
        try:
            self.api.patch_namespaced_lease(self.name, self.namespace, body)
            return True
        except ApiException as exc:
            logger.warning("Could not renew leader lease: %s", exc)
            return False

    def release(self) -> None:
        body = {"spec": {"holderIdentity": None}}
        try:
            self.api.patch_namespaced_lease(self.name, self.namespace, body)
        except ApiException as exc:
            logger.debug("Could not release leader lease: %s", exc)