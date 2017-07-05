import os
from celery import Celery

#: Set default configuration module name
os.environ.setdefault('CELERY_CONFIG_MODULE',
                      'background.config.dev.CeleryConfig')

app = Celery(__name__)
app.config_from_envvar('CELERY_CONFIG_MODULE')
