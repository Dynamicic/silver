
from __future__ import absolute_import, unicode_literals

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
from antikythera.antikythera.celery import app as celery_app
from antikythera.antikythera.celery import process_hooks
import antikythera.antikythera.celery as celery

import antikythera.antikythera.settings as settings
import antikythera.antikythera.settings_test as settings_test

# from .hooktask import DeliverHook, process_hooks

__all__ = ['celery_app']
