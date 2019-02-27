from pyswagger import App, Security
from pyswagger.contrib.client.requests import Client
from pyswagger.utils import jp_compose
from pyswagger.utils import get_swagger_version

from pyswagger.core import Resolver

from dotenv import load_dotenv
import os, sys

def create_client(schema=False):
    """ Create a swagger app and REST client.

       :param schema: Provide a schema URL. Defaults to a local testing
           schema.

       :returns: pyswagger.App, pyswagger.Client
    """

    load_dotenv()

    try:
        token = os.environ['SILVER_AUTH_TOKEN']
    except KeyError:
        print("Could not read SILVER_AUTH_TOKEN")
        sys.exit()

    if schema:
        app = App.create(schema)
    else:
        app = App.create('./schemas/schema.1.json')

    auth = Security(app)
    auth.update_with('basic', 'Token ' + token)

    # init swagger client
    client = Client(auth)

    return app, client

def list_endpoints(app):
    """ List all the endpoints.
    """

    for e in sorted(app.op.keys()):
        print(e)

def test_client(app, client):
    """ Test a request with some default settings.
    """

    # a request to create a new pet
    client.request(app.op['silver!##!customers_list']())

    # - access an Operation object via App.op when operationId is defined
    # - a request to get the pet back
    req, resp = app.op['silver!##!customers_list']()

    # prefer json as response
    req.produce('application/json')
    customers = client.request((req, resp)).data
    assert len(customers) > 0
