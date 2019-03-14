#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""The setup script."""

from setuptools import setup, find_packages

with open('README.rst') as readme_file:
    readme = readme_file.read()

with open('HISTORY.rst') as history_file:
    history = history_file.read()

# TODO: may need to replace xhtmlpdf with a zip.
requirements = [
    'Click>=6.0',
    # 'Fabric3',
    # 'python-dotenv==0.10.1',
    'django==1.11.17',
    'django-dotenv==1.4.2',
    'uwsgi==2.0.17.1',
    'kombu==4.4.0',
    'mysqlclient==1.3.14',
    'djangorestframework==3.9.1',
    'djangorestframework-bulk<0.3',
    'django-reversion==3.0.3',
    'django-reversion-compare==0.8.6',
    'django-rest-hooks==1.5.0',
    'django-rest-hooks-delivery',
    'django-rest-swagger==2.2.0',
    'drf-yasg',
    'celery==4.3.0rc2',
    'redis==3.2.0',
    'celery-once>=1.2,<2.1',
    'sqlparse>=0.2,<0.3',
    'django-fsm>=2.3,<2.7',
    'django-filter>=1.0.4,<1.2',
    'django-livefield>=2.8,<3.1',
    'django-jsonfield==1.0.1',
    'pycountry>=16.11.08',
    'python-dateutil>=2.6,<2.8',
    'pyvat>=1.3,<1.4',
    'django-model-utils>=3.0,<3.2',
    'django-annoying>=0.10,<0.11',
    'django-autocomplete-light>=3.2,<3.3',
    'pycountry>=16.11.08',
    'python-dateutil>=2.6,<2.8',
    'pyvat>=1.3,<1.4',
    'cryptography>=1.9,<2.4',
    'PyJWT>=1.5,<1.7',
    'furl>=1,<1.3',
    'xhtml2pdf>=0.2,<0.3',
    'PyPDF2>=1.26,<2',
    'pytest==3.1.3',
    'pytest-django==3.1.2',
    'mock==1.0.1',
    'flake8==2.4.1',
    'freezegun==0.3.8',
    'coverage==3.7.1',
    'django-coverage==1.2.4',
    'pytest-django==3.1.2',
    'factory-boy==2.5.2',
    'pep8==1.7.0',
    'Faker==0.7.17',
]

setup_requirements = ['pytest-runner', ]

test_requirements = [
]

setup(
    author=".",
    author_email='.',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'Natural Language :: English',
        "Programming Language :: Python :: 2",
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
    ],
    description="A django app that houses all the billing functionality you've come to know and love. What About February™?",
    entry_points={
        'console_scripts': [
            'antikythera=antikythera.cli:main',
            # This is basically just django-admin but with our own
            # stuff.
            'antikythera-manage=antikythera.manage:main',
        ],
    },
    install_requires=requirements,
    long_description=readme + '\n\n' + history,
    include_package_data=True,
    keywords='antikythera',
    name='antikythera',
    packages=find_packages(include=['antikythera']),
    setup_requires=setup_requirements,
    test_suite='tests',
    tests_require=test_requirements,
    url='.',
    version='0.1.1',
    zip_safe=False,
)
