#!/usr/bin/env python
import os
import sys
import dotenv
import antikythera

def main():
    dotenv.load_dotenv(os.path.join(os.getcwd(), '.env'))
    sys.path.insert(0, os.path.dirname(__file__))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "antikythera.antikythera.settings")
    os.environ['DJANGO_SETTINGS_MODULE'] = "antikythera.antikythera.settings"

    try:
        extra_paths = os.environ['ANTIKYTHERA_EXTRA_PATHS'].split(':')
    except:
        extra_paths = ['/code/silver', '/code/silver_authorizenet/']

    for p in extra_paths:
        sys.path.append(p)

    try:
        from django.core.management import execute_from_command_line
    except ImportError:
        # The above import may fail for some other reason. Ensure that the
        # issue is really that Django is missing to avoid masking other
        # exceptions on Python 2.
        try:
            import django
        except ImportError:
            raise ImportError(
                "Couldn't import Django. Are you sure it's installed and "
                "available on your PYTHONPATH environment variable? Did you "
                "forget to activate a virtual environment?"
            )
        raise
    execute_from_command_line(sys.argv)

if __name__ == "__main__":
    main()
