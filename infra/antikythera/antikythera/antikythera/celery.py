from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
import dotenv
from .hooktask import process_hooks

dotenv.read_dotenv(os.path.join(os.getcwd(), '.env'))

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'antikythera.antikythera.settings')

app = Celery('proj',
             broker=os.environ['DJANGO_BROKER_URL'],
             backend=os.environ['REDIS_HOST_STRING'])

# Using a string here means the worker don't have to serialize
# the configuration object to child processes.
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
app.config_from_object('django.conf:settings', namespace='CELERY')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))

app.task(bind=True, name='antikythera.antikythera.hooktask.process_hooks')(process_hooks)
