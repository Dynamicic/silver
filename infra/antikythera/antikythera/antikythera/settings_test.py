import os, sys
sys.path.append('/code/silver/')
sys.path.append('/code/silver_authorizenet/')

from authorizenet import constants as authorizenetconstants
# import constants
import django

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
        'console': {
            'class': 'logging.StreamHandler',
            # 'formatter': 'console',
        },
    },

    'loggers': {
        'django': {
            'handlers': ['file', 'console'],
            'propagate': True,
            'level': 'WARNING',
        },
        'django.db.backends.schema': {
            'handlers': ['file', 'console'],
            'propagate': True,
            'level': 'WARNING',
        },
        'authorizenet.sdk': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
            'formatter': '%(asctime)s %(name)-12s %(levelname)-8s %(message)s',
        },
        '': {
            'handlers': ['file', 'console'],
            'level': 'DEBUG',
        }
    }
}

# PAYMENT_PROCESSORS = {
#     triggered_processor: {
#         'class': 'silver.tests.fixtures.TriggeredProcessor'
#     },
#     manual_processor: {
#         'class': 'silver.tests.fixtures.ManualProcessor'
#     },
#     failing_void_processor: {
#         'class': 'silver.tests.fixtures.FailingVoidTriggeredProcessor'
#     }
# 
# }



DEBUG=True
# DATABASES={
#     'default': {
#         'ENGINE': 'django.db.backends.sqlite3',
#         'NAME': 'testdb',
#     }
# }

authorize_api_login       = os.environ['AUTHORIZE_API_LOGIN']
authorize_transaction_key = os.environ['AUTHORIZE_TRANSACTION_KEY']
authorize_key             = os.environ['AUTHORIZE_KEY']
authorize_environment     = os.environ.get('AUTHORIZE_ENVIRONMENT', 'SANDBOX')

auth_env = authorizenetconstants.constants.SANDBOX

if authorize_environment == 'PRODUCTION':
    auth_env = authorizenetconstants.constants.PRODUCTION

authorizenet_setup_data = {
    'environment': auth_env,
    'api_login': authorize_api_login,
    'transaction_key': authorize_transaction_key,
    'key': authorize_key
}

PAYMENT_METHOD_SECRET=b'MOW_x1k-ayes3KqnFHNZUxvKipC8iLjxiczEN76TIEA='

PAYMENT_PROCESSORS = {
    'manual': {
        'class': 'silver.payment_processors.manual.ManualProcessor',
    },
    'tests_triggered': {
        'class': 'silver.tests.fixtures.TriggeredProcessor'
    },
    'tests_manual': {
        'class': 'silver.tests.fixtures.ManualProcessor'
    },
    'tests_failing_void': {
        'class': 'silver.tests.fixtures.FailingVoidTriggeredProcessor'
    },
    'authorizenet_triggered': {
        'class': 'silver_authorizenet.payment_processors.AuthorizeNetTriggered',
        'setup_data': {
            'environment': auth_env,
            'api_login': authorize_api_login,
            'transaction_key': authorize_transaction_key,
            'key': authorize_key
        },
    },
    'AuthorizeNetTriggered': {
        'class': 'silver_authorizenet.payment_processors.AuthorizeNetTriggered',
        'setup_data': {
            'environment': auth_env,
            'api_login': authorize_api_login,
            'transaction_key': authorize_transaction_key,
            'key': authorize_key
        },
    },
    # 'braintree_triggered': {
    #     'class': 'silver_braintree.payment_processors.BraintreeTriggered',
    #     'setup_data': braintree_setup_data,
    # },
    # 'braintree_recurring': {
    #     'class': 'silver_braintree.payment_processors.BraintreeTriggeredRecurring',
    #     'setup_data': braintree_setup_data,
    # }
}

INSTALLED_APPS=(
    'dal',
    'dal_select2',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.staticfiles',
    'django.contrib.admin',
    'silver',
    'silver_authorizenet',
)

CACHES={
    'default': {
        'BACKEND': 'django.core.cache.backends.dummy.DummyCache',
        'LOCATION': 'unique-snowflake',
    }
}
USE_TZ=True
STATIC_URL='/static/'
SILVER_AUTOMATICALLY_CREATE_TRANSACTIONS=True


django.setup()
