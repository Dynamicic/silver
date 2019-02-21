from settings import *

triggered_processor = 'triggered'
manual_processor = 'manual'
failing_void_processor = 'failing_void'

LOGGING = {
    'version': 1,
    'handlers': {
        'file': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'filename': '/tmp/silver-debug.log',
        },
    },
    'loggers': {
        'django': {
            'handlers': ['file'],
            'propagate': True,
            'level': 'WARNING',
        },
        'django.db.backends.schema': {
            'handlers': ['file'],
            'propagate': True,
            'level': 'WARNING',
        },
        '': {
            'handlers': ['file'],
            'level': 'DEBUG',
        }
    }
}

PAYMENT_PROCESSORS = {
    triggered_processor: {
        'class': 'silver.tests.fixtures.TriggeredProcessor'
    },
    manual_processor: {
        'class': 'silver.tests.fixtures.ManualProcessor'
    },
    failing_void_processor: {
        'class': 'silver.tests.fixtures.FailingVoidTriggeredProcessor'
    }

}
