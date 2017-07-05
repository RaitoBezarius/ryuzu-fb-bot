from decouple import config

from .base import BaseCeleryConfig

REDIS_URL = config('REDIS_URL')


class CeleryProduction(BaseCeleryConfig):
    enable_utc = config('CELERY_ENABLE_UTC', default=True, cast=bool)
    broker_url = config('CELERY_BROKER_URL',
                        default=REDIS_URL)
    result_backend = config('CELERY_RESULT_BACKEND',
                            default=REDIS_URL)
