from bravado.client import SwaggerClient

from bravado.http_client import HttpClient

from dotenv import load_dotenv
import os, sys

import requests

from datetime import datetime as dt
from datetime import timedelta

import silversdk.formats as formats
from silversdk.authentication import *

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
    'validate_requests': True,

    # Validate the swagger spec
    'validate_swagger_spec': False,

    # Use models (Python classes) instead of dicts for #/definitions/{models}
    'use_models': True,

    # List of user-defined formats
    'formats': formats.as_list,
}

def create_client(schema=False, debug=True, config=SWAGGER_CONFIG):
    """ Create a swagger app and REST client.

       :param schema: Provide a schema URL. Defaults to a local testing
           schema.
       :param debug: Extra debug logs

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

    token = os.environ['SILVER_AUTH_TOKEN']
    auth_header = {
        'Authorization': token,
    }

    http = RequestsClient()
    http.authenticator = TokenAuthenticator(host=host, token=token)

    if schema or env_schema:
        client = SwaggerClient.from_url(schema or env_schema,
                                        # request_headers=auth_header,
                                        http_client=http,
                                        config=config)
    else:
        print("No schema provided.")
        sys.exit()

    return client

import simplejson as json

class APIShortcuts(object):

    def __init__(self, client):
        self.client = client

    def model(self, m):
        return self.client.get_model(m)

class SilverClient(object):
    """ This is the main Silver client. It exposes a `Bravado` client
    instance via `self.client`, and has shortcut methods for multi-step
    processes.

        :param schema: An optional alternative schema to use.
        :type schema: bbq
        :param debug: Enable extra debug logs
        :type debug: bool.
        :param config: Config for overriding override SWAGGER_OPTIONS.
        :type config: dict.
    """

    def __init__(self, schema=False, debug=True, config=SWAGGER_CONFIG):
        self.client = create_client(schema=schema, debug=debug, config=config)
        self.shortcuts = APIShortcuts(client=self.client)

