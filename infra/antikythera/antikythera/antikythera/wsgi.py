"""
WSGI config for silverintegration project.

It exposes the WSGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/1.11/howto/deployment/wsgi/
"""

import os
import dotenv

dotenv.load_dotenv(os.path.join(os.getcwd(), '.env'))
from django.core.wsgi import get_wsgi_application

os.environ["DJANGO_SETTINGS_MODULE"] = "antikythera.antikythera.settings"

application = get_wsgi_application()
