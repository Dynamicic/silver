=====
Usage
=====

Quickstart
----------

After installing the library, set up your environment: copy `dotenv-in`
to `.env` and configure your environment variables. These will be loaded
via dotenv.

To check that it's working, run the following and observe that API
endpoints display.

::

    silversdk --endpoints

If everything works you should be able to use the library. The main
point of entry to using the library is `silversdk.client.SilverClient`,
which handles authentication and provides access to a `bravado` client
instance via `SilverClient.client`.

`SilverClient` will also contain some helpful shortcuts for things
beyond the base `client` API.

API Documentation 
-----------------

The full `API documentation`_  is available through Swagger.

.. _API documentation: http://dev.billing.dynamicic.com/swagger/

Doing things
------------

Here's a quick minimal example of something that works.

::
    from silversdk import SilverClient

    # Initialize the client. If things break here your environment is
    # not set up.
    silver = SilverClient()

    customers_list = silver.client.customers.customers_list()
    customers = customers_list.response()
    print(customers.result[0])


