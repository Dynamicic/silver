__version__ = '0.1.1'

from __future__ import absolute_import, unicode_literals

# This will make sure the app is always imported when
# Django starts so that shared_task will use this app.
try:
    from antikythera.antikythera.celery import app as celery_app
    from antikythera.antikythera.celery import process_hooks
    import antikythera.antikythera.celery as celery
    __all__ = ['celery_app']
    # import antikythera.antikythera.settings as settings
    # import antikythera.antikythera.settings_test as settings_test
except:
    pass


# from .hooktask import DeliverHook, process_hooks

