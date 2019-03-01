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

def list_endpoints(silverclient):
    """ List all the endpoints.
    """

    sp = ''
    for namespace in dir(silverclient.client):
        print('namespace: ' + namespace)
        for endpoint in dir(getattr(silverclient.client, namespace)):
            print('    ' + endpoint)
        print(' ')

def test_client(silverclient):
    """ Test a request with some default settings.
    """
    from itertools import chain

    # a request to create a new pet
    customers = silverclient.client.customers.customers_list()

    custs = customers.response()

    print(custs.result[0])

    assert len(custs.incoming_response.text) > 1
    assert len(custs.result) > 1

@click.command()
@click.option('--test-client', 'testclient', default=False, flag_value=True, required=False)
@click.option('--endpoints', default=False, flag_value=True, required=False)
def main(testclient, endpoints):
    client = SilverClient()

    if testclient:
        test_client(client)

    if endpoints:
        list_endpoints(client)
