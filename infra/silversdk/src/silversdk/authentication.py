from bravado.client import SwaggerClient
from bravado.http_client import HttpClient
from bravado.requests_client import RequestsClient, Authenticator

import os, sys
import requests

class TokenAuthenticator(Authenticator):
    """
    This authenticator adds an API key via the Authorization header.

    :param host: Host to authenticate for.
    :param api_key: API key.
    :param param_name: Query parameter specifying the API key.
    :param param_in: How to send the API key. Can be 'query' or 'header'.
    """

    def __init__(
        self,
        host,  # type: str
        token,  # type: typing.Text
        param_name=u'Authorization',  # type: typing.Text
        param_in=u'header',  # type: typing.Text
    ):
        # type: (...) -> None
        super(TokenAuthenticator, self).__init__(host)
        self.param_name = param_name
        self.param_in = param_in
        self.token = "Token %s" % token

    def apply(self, request):
        # type: (requests.Request) -> requests.Request
        if self.param_in == 'header':
            request.headers.setdefault(self.param_name, self.token)
        else:
            request.params[self.param_name] = self.token
        request.headers['Content-Type'] = 'application/json'
        return request

    def matches(self, uri):
        return True

class RequestsClient(RequestsClient):

    """ A wrapper around the RequestsClient that provides the
    authentication header. """

    def authenticated_request(self, request_params):
        return self.apply_authentication(requests.Request(**request_params))

