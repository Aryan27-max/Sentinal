"""Alert delivery: console, SNS, CloudWatch Logs (ARCHITECTURE.md §9).

The pipeline only calls `Dispatcher.submit` (put_nowait). A worker task drains the queue and
calls each sink with retries and backoff; boto3 runs in a thread. With DRY_RUN=true, or when
AWS credentials are missing, the AWS sinks log the exact payload they would have sent.
"""

import asyncio
import logging
import time
from typing import Any, Protocol

import boto3

from app.config import Settings
from app.models import Alert

log = logging.getLogger("sentinel.sinks")

RETRIES = 3
QUEUE_SIZE = 1000


class AlertSink(Protocol):
    name: str

    async def send(self, alert: Alert) -> None: ...


def sms_text(a: Alert) -> str:
    """Short enough for one SMS (< 160 chars): severity, service, metric, value vs baseline."""
    if a.detector == "error_rate":
        detail = f"error rate {a.current:.1%} vs {a.baseline_median or 0:.1%}"
    elif a.detector == "latency":
        detail = f"p95 {a.current:.0f}ms vs {a.baseline_median or 0:.0f}ms"
    else:
        detail = f"no logs for {a.current:.0f}s"
    z = f" z={a.z:.1f}" if a.z is not None else ""
    return f"Sentinel {a.severity}: {a.service} {detail}{z}"[:159]


class ConsoleSink:
    name = "console"

    async def send(self, alert: Alert) -> None:
        log.warning("ALERT %s %s", alert.severity, alert.message)


class SNSSink:
    name = "sns"

    def __init__(self, settings: Settings, live: bool) -> None:
        self.s = settings
        self.live = live
        self._client: Any = None

    def _publish(self, text: str, payload: str) -> None:
        if self._client is None:
            self._client = boto3.client("sns", region_name=self.s.aws_region)
        self._client.publish(
            TopicArn=self.s.sns_topic_arn,
            Message=text,
            MessageAttributes={"alert": {"DataType": "String", "StringValue": payload}},
        )

    async def send(self, alert: Alert) -> None:
        text, payload = sms_text(alert), alert.model_dump_json()
        if not self.live:
            log.info("[dry-run] SNS publish topic=%s message=%r", self.s.sns_topic_arn or "-", text)
            return
        await asyncio.to_thread(self._publish, text, payload)


class CloudWatchSink:
    name = "cloudwatch"

    def __init__(self, settings: Settings, live: bool) -> None:
        self.s = settings
        self.live = live
        self._client: Any = None

    def _put(self, ts_ms: int, message: str) -> None:
        if self._client is None:
            client = boto3.client("logs", region_name=self.s.aws_region)
            for create, kwargs in (
                (client.create_log_group, {"logGroupName": self.s.cw_log_group}),
                (
                    client.create_log_stream,
                    {"logGroupName": self.s.cw_log_group, "logStreamName": self.s.cw_log_stream},
                ),
            ):
                try:
                    create(**kwargs)
                except client.exceptions.ResourceAlreadyExistsException:
                    pass
            self._client = client
        self._client.put_log_events(
            logGroupName=self.s.cw_log_group,
            logStreamName=self.s.cw_log_stream,
            logEvents=[{"timestamp": ts_ms, "message": message}],
        )

    async def send(self, alert: Alert) -> None:
        message = alert.model_dump_json()
        if not self.live:
            log.info(
                "[dry-run] CloudWatch put_log_events %s/%s %s",
                self.s.cw_log_group,
                self.s.cw_log_stream,
                message,
            )
            return
        await asyncio.to_thread(self._put, int(time.time() * 1000), message)


class Dispatcher:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.queue: asyncio.Queue[Alert] = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.sinks: list[AlertSink] = [ConsoleSink()]
        self.status: dict[str, str] = {"console": "on", "sns": "dry-run", "cloudwatch": "dry-run"}

    async def setup(self) -> None:
        """Decide which AWS sinks go live. Never raises: missing creds mean dry-run."""
        aws_live = False
        if not self.s.dry_run:
            try:
                creds = await asyncio.to_thread(lambda: boto3.Session().get_credentials())
                aws_live = creds is not None
            except Exception:
                log.exception("AWS credential lookup failed")
            if not aws_live:
                log.warning("DRY_RUN=false but no AWS credentials found; AWS sinks stay dry-run")
        sns_live = aws_live and bool(self.s.sns_topic_arn)
        if aws_live and not sns_live:
            log.warning("SNS_TOPIC_ARN is empty; SNS sink stays dry-run")
        self.sinks += [SNSSink(self.s, sns_live), CloudWatchSink(self.s, aws_live)]
        self.status.update(
            sns="live" if sns_live else "dry-run", cloudwatch="live" if aws_live else "dry-run"
        )

    def submit(self, alert: Alert) -> None:
        try:
            self.queue.put_nowait(alert)
        except asyncio.QueueFull:
            log.error("Sink queue full; dropping alert %s", alert.id)

    async def _deliver(self, sink: AlertSink, alert: Alert) -> None:
        for attempt in range(RETRIES):
            try:
                await sink.send(alert)
                return
            except Exception as exc:
                log.warning(
                    "%s send failed (attempt %d/%d): %s", sink.name, attempt + 1, RETRIES, exc
                )
                await asyncio.sleep(0.5 * 2**attempt)
        log.error("%s gave up on alert %s", sink.name, alert.id)

    async def run(self) -> None:
        while True:
            alert = await self.queue.get()
            await asyncio.gather(*(self._deliver(sink, alert) for sink in self.sinks))
            self.queue.task_done()
