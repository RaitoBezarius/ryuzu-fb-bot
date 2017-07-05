from .base import BaseCeleryConfig


class CeleryConfig(BaseCeleryConfig):
    broker_url = 'redis://'
    result_backend = 'redis://'
