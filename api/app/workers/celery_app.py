from celery import Celery
from celery.schedules import crontab
from celery.signals import beat_init, worker_process_init, worker_process_shutdown, worker_shutdown

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.services.queues import TASK_ROUTES

settings = get_settings()

celery_app = Celery(
    "cobranca",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_url,
    include=[
        "app.ingest.tasks",
        "app.dunning.tasks",
        "app.channels.tasks",
        "app.receipts.tasks",
        "app.reconciliation.tasks",
        "app.agent.tasks",
    ],
)

celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # O celery-exporter (stack observability/) lê estes eventos no Redis.
    worker_send_task_events=True,
    task_send_sent_event=True,
    worker_prefetch_multiplier=1,
    result_expires=3600,
    timezone="America/Sao_Paulo",
    enable_utc=True,
    task_routes=TASK_ROUTES,
    # Fila sem consumidor de propósito: task nova sem rota em queues.py não roda no worker errado.
    task_default_queue="sem-dono",
    beat_schedule={
        "run-dunning": {
            "task": "app.dunning.tasks.run_dunning",
            "schedule": settings.dunning_interval_minutes * 60,
        },
        "check-promises": {
            "task": "app.dunning.tasks.check_promises",
            "schedule": crontab(minute=0, hour=7),
        },
        "pull-statements": {
            "task": "app.reconciliation.tasks.pull_statements",
            "schedule": settings.statement_interval_minutes * 60,
        },
    },
)


@beat_init.connect
def _init_beat(**_):
    import os

    from app.core.tracing import setup_tracing

    setup_tracing(os.environ.get("SERVICE_NAME") or "relo-disp")


@worker_process_init.connect
def _init_worker(**_):
    # O processo filho precisa do cliente de novo: o do pai não sobrevive ao fork.
    configure_logging()
    from app.core.observability import init_sentry
    from app.core.tracing import instrument_celery

    init_sentry(force=True)
    instrument_celery("celery")


@worker_process_shutdown.connect
@worker_shutdown.connect
def _flush_traces(**_):
    from app.core.observability import flush_traces
    from app.core.tracing import shutdown_tracing

    shutdown_tracing()
    flush_traces()


configure_logging()
