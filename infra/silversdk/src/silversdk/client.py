from bravado.client import SwaggerClient

from bravado.http_client import HttpClient
from bravado.requests_client import RequestsClient, Authenticator

from dotenv import load_dotenv
import os, sys

import requests

SWAGGER_CONFIG = {
    # === bravado config ===

    # What class to use for response metadata
    'response_metadata_class': 'bravado.response.BravadoResponseMetadata',

    # Do not use fallback results even if they're provided
    'disable_fallback_results': False,

    # DEPRECATED: Determines what is returned by HttpFuture.result().
    # Please use HttpFuture.response() for accessing the http response.
    'also_return_response': False,

    # === bravado-core config ====

    # Validate incoming responses
    'validate_responses': False,

    # Validate outgoing requests
    'validate_requests': False,

    # Validate the swagger spec
    'validate_swagger_spec': False,

    # Use models (Python classes) instead of dicts for #/definitions/{models}
    'use_models': False,

    # List of user-defined formats
    # 'formats': [my_super_duper_format],

}


class TokenAuthenticator(Authenticator):
    """?api_key authenticator.
    This authenticator adds an API key via query parameter or header.
    :param host: Host to authenticate for.
    :param api_key: API key.
    :param param_name: Query parameter specifying the API key.
    :param param_in: How to send the API key. Can be 'query' or 'header'.
    """

    def __init__(
        self,
        host,  # type: str
        api_key,  # type: typing.Text
        param_name=u'Authorization',  # type: typing.Text
        param_in=u'header',  # type: typing.Text
    ):
        # type: (...) -> None
        super(TokenAuthenticator, self).__init__(host)
        self.param_name = param_name
        self.param_in = param_in
        self.api_key = api_key

    def apply(self, request):
        # type: (requests.Request) -> requests.Request
        if self.param_in == 'header':
            request.headers.setdefault(self.param_name, self.api_key)
        else:
            request.params[self.param_name] = self.api_key
        request.headers['Content-Type'] = 'application/json'
        return request

    def matches(self, uri):
        return True

class RequestsClient(RequestsClient):
    def authenticated_request(self, request_params):
        return self.apply_authentication(requests.Request(**request_params))


def create_client(schema=False, debug=True):
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

    try:
        env_schema = os.environ['SILVER_HOST_SCHEMA']
    except KeyError:
        env_schema = False

    try:
        host = os.environ['SILVER_HOST']
    except KeyError:
        host = False

    tok = 'Token ' + os.environ['SILVER_AUTH_TOKEN']
    auth_header = {
        'Authorization': tok
    }

    http = RequestsClient()
    http.authenticator = TokenAuthenticator(host=host, api_key=tok)

    if schema or env_schema:
        client = SwaggerClient.from_url(schema or env_schema,
                                        request_headers=auth_header,
                                        http_client=http,
                                        config=SWAGGER_CONFIG)

    return client


class SilverClient(object):

    def __init__(self, schema=False, debug=True):
        self.client = create_client(schema=schema, debug=debug)

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
    customers = silverclient.client.silver.product_codes_list()

    custs = customers.response()
    # print(custs.incoming_response.text)
    assert len(custs.incoming_response.text) > 1
    print(custs.result())


