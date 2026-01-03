from celery import Celery
from celery.schedules import crontab

from stocker.core.config import settings

app = Celery("stocker")
app.conf.broker_url = settings.CELERY_BROKER_URL
app.conf.result_backend = settings.CELERY_RESULT_BACKEND
app.conf.timezone = settings.CELERY_TIMEZONE
app.conf.enable_utc = False

app.autodiscover_tasks(["stocker"])

app.conf.beat_schedule = {
    "ingest-market-data": {
        "task": "stocker.tasks.market_data.ingest_market_data",
        "schedule": crontab(
            hour=settings.MARKET_CLOSE_HOUR,
            minute=settings.MARKET_CLOSE_MINUTE,
        ),
    },
    "ingest-instrument-metrics": {
        "task": "stocker.tasks.instrument_metrics.ingest_instrument_metrics",
        "schedule": crontab(
            hour=settings.FUNDAMENTALS_REFRESH_HOUR,
            minute=settings.FUNDAMENTALS_REFRESH_MINUTE,
        ),
    },
    "ingest-corporate-actions": {
        "task": "stocker.tasks.corporate_actions.ingest_corporate_actions",
        "schedule": crontab(
            day_of_week=settings.CORP_ACTIONS_REFRESH_DAY,
            hour=settings.CORP_ACTIONS_REFRESH_HOUR,
            minute=settings.CORP_ACTIONS_REFRESH_MINUTE,
        ),
    },
    "ingest-market-sentiment": {
        "task": "stocker.tasks.market_sentiment.ingest_market_sentiment",
        "schedule": crontab(
            day_of_week=settings.SENTIMENT_REFRESH_DAY,
            hour=settings.SENTIMENT_REFRESH_HOUR,
            minute=settings.SENTIMENT_REFRESH_MINUTE,
        ),
    },
    # MOO order fill sync - runs after market open to capture fills
    "sync-moo-fills-open": {
        "task": "stocker.tasks.order_sync.sync_moo_fills",
        "schedule": crontab(
            hour=9,
            minute=35,
            day_of_week="mon-fri",
        ),
    },
    "sync-moo-fills-followup": {
        "task": "stocker.tasks.order_sync.sync_moo_fills",
        "schedule": crontab(
            hour=10,
            minute=0,
            day_of_week="mon-fri",
        ),
    },
    "refresh-dynamic-universe": {
        "task": "stocker.tasks.universe_refresh.refresh_dynamic_universe",
        "schedule": crontab(
            hour=settings.UNIVERSE_REFRESH_HOUR,
            minute=settings.UNIVERSE_REFRESH_MINUTE,
            day_of_week="1-5",  # Monday-Friday only
        ),
        "options": {"expires": 3600},
    },
}
