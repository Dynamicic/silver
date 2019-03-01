from bravado_core.spec import Spec
from bravado_core.formatter import SwaggerFormat

class URI(object):

    def __init__(self, uri):
        """
        :param uri: URI in string form.
        """
        self.uri = uri

def validate_uri(uri_string):
    if '/' not in uri_string:
        raise SwaggerValidationError('URI {0} is invalid'.format(uri_string))

uri_format = SwaggerFormat(
    # name of the format as used in the Swagger spec
    format='uri',
    description="Representation of Django Rest Framework's URI Primary key thing",

    # Callable to convert a python CIDR object to a string
    to_wire=lambda uri_object: uri_object.uri,

    # Callable to convert a string to a python CIDR object
    to_python=lambda uri_string: URI(uri_string),

    # Callable to validate the uri in string form
    validate=validate_uri
)


# All the formats we define
as_list = [
    uri_format,
]
