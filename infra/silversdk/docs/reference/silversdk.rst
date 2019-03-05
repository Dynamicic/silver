silversdk
=========

.. testsetup::

    from silversdk import *


silversdk.client
----------------

The main interface for creating something with the client is through the
following. `SWAGGER_CONFIG` contains reasonable defaults, but you can
override these and pass them to `SilverClient`. 

.. automodule:: silversdk.client
    :members: SWAGGER_CONFIG, create_client, SilverClient

