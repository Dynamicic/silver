# -*- encoding: utf-8 -*-

import os

import versioneer
from setuptools import setup, find_packages

from silver_authorizenet import __version__ as version

install_requires = [
    'authorizenet'
]


def read(fname):
    try:
        return open(os.path.join(os.path.dirname(__file__), fname)).read()
    except IOError:
        return ''

setup(
    name="silver-authorizenet",
    version=version,
    cmdclass=versioneer.get_cmdclass(),
    description=read('DESCRIPTION'),
    long_description=read('README.md'),
    license='Apache 2.0',
    platforms=['OS Independent'],
    keywords='django, app, reusable, billing, invoicing, api',
    author='TODO',
    author_email='TODO@TODO.com',
    url='TODO.com',
    packages=find_packages(),
    include_package_data=True,
    install_requires=install_requires,
    classifiers=[
        'Environment :: Web Environment',
        'Framework :: Django :: 1.8',
        'Development Status :: 5 - Production/Stable',
        'License :: OSI Approved :: Apache Software License',
        'Programming Language :: Python :: 2.7'
    ]
)
