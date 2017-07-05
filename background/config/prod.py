from decouple import config

from .base import BaseCeleryConfig


class CeleryProduction(BaseCeleryConfig):
    enable_utc = config('CELERY_ENABLE_UTC', default=True, cast=bool)
    broker_url = config('CELERY_BROKER_URL')
    result_backend = config('CELERY_RESULT_BACKEND')
