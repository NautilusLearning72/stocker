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
    "ingest-market-sentiment": {
        "task": "stocker.tasks.market_sentiment.ingest_market_sentiment",
        "schedule": crontab(
            day_of_week=settings.SENTIMENT_REFRESH_DAY,
            hour=settings.SENTIMENT_REFRESH_HOUR,
            minute=settings.SENTIMENT_REFRESH_MINUTE,
        ),
    },
}
