"""
Module that contains the command line app.

Why does this file exist, and why not put this in __main__?

  You might be tempted to import things from __main__ later, but that will cause
  problems: the code will get executed twice:

  - When you run `python -msilversdk` python will execute
    ``__main__.py`` as a script. That means there won't be any
    ``silversdk.__main__`` in ``sys.modules``.
  - When you import __main__ it will get executed again (as a module) because
    there's no ``silversdk.__main__`` in ``sys.modules``.

  Also see (1) from http://click.pocoo.org/5/setuptools/#setuptools-integration
"""
import click

from .client import *

@click.command()
@click.option('--test-client', 'testclient', default=False, flag_value=True, required=False)
@click.option('--endpoints', default=False, flag_value=True, required=False)
def main(testclient, endpoints):
    _app, _client = create_client()

    if testclient:
        test_client(_app, _client)

    if endpoints:
        list_endpoints(_app)
