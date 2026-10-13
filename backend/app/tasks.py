"""Background job dispatch.

* InlineQueue (local, tests): runs the job on a small thread pool inside the process.
* CloudTasksQueue (prod): enqueues an HTTP task that calls POST /tasks/prebunk on this
  same service with an OIDC token minted for api-sa. Cloud Tasks retries with backoff,
  so a crashed instance never loses a brief.
  Docs: https://cloud.google.com/tasks/docs/creating-http-target-tasks

/tasks/* endpoints accept ONLY a Google signed OIDC token for our own service account
and audience. Docs: https://cloud.google.com/run/docs/authenticating/service-to-service
"""

from __future__ import annotations

import json
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Protocol

Job = Callable[[], Any]
OidcVerifier = Callable[[str], dict[str, Any]]


class TaskQueue(Protocol):
    def enqueue_prebunk(self, session_id: str, job: Job) -> None: ...


class InlineQueue:
    def __init__(self, workers: int = 2) -> None:
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="job")
        self.futures: list[Future[Any]] = []

    def enqueue_prebunk(self, session_id: str, job: Job) -> None:
        self.futures.append(self.pool.submit(job))

    def drain(self) -> None:
        for f in self.futures:
            f.result()
        self.futures.clear()


class SyncQueue:
    """Runs the job immediately. Tests use it for deterministic assertions."""

    def enqueue_prebunk(self, session_id: str, job: Job) -> None:
        job()


class CloudTasksQueue:  # pragma: no cover - needs GCP
    def __init__(
        self, project: str, region: str, queue: str, target_base: str, sa_email: str
    ) -> None:
        from google.cloud import tasks_v2

        self.client = tasks_v2.CloudTasksClient()
        self.parent = self.client.queue_path(project, region, queue)
        self.target_base = target_base.rstrip("/")
        self.sa_email = sa_email

    def enqueue_prebunk(self, session_id: str, job: Job) -> None:
        from google.cloud import tasks_v2

        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=f"{self.target_base}/tasks/prebunk",
                headers={"Content-Type": "application/json"},
                body=json.dumps({"session_id": session_id}).encode(),
                oidc_token=tasks_v2.OidcToken(
                    service_account_email=self.sa_email, audience=self.target_base
                ),
            )
        )
        self.client.create_task(parent=self.parent, task=task)


def google_oidc_verifier(audience: str, allowed_email: str) -> OidcVerifier:  # pragma: no cover
    from google.auth.transport import requests as ga_requests
    from google.oauth2 import id_token

    req = ga_requests.Request()

    def _verify(token: str) -> dict[str, Any]:
        claims: dict[str, Any] = id_token.verify_oauth2_token(  # type: ignore[no-untyped-call]
            token, req, audience=audience
        )
        if claims.get("email") != allowed_email or not claims.get("email_verified"):
            raise ValueError("wrong caller")
        return claims

    return _verify
