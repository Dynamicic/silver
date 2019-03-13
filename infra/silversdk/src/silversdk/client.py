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

    def create_one_off_transaction(self, *args, **kwargs):
        """ A shortcut for creating a one-off invoice. This creates a
        customer, a payment method, a new invoice and a transaction.
        Returns all the created objects as a single JSON response.

         * Create customer
         * Get/create default provider
         * Create invoice with entry
         * issue the invoice
         * return the customer, invoice, and transactions

        """

        kleint = self.client

        ## Create a customer for the one-off transaction

        ## Create a customer payment method

        customer_one_off_defaults = {
            "currency": "USD",
        }

        new_customer = customer_one_off_defaults
        new_customer.update(**kwargs.get('customer'))

        Customer = self.client.get_model('Customer')

        if 'meta' in new_customer:
            new_customer['meta'] = json.dumps(new_customer.get('meta'))

        customer = Customer(**new_customer)
        req = kleint.customers.customers_create(data=customer)
        res = req.response().result


        # URI object
        customer_id = res.id
        customer_url = res.url


        ## Create a customer payment method
        # 
        customer_default_payment_method = {
            # TODO: authorize.net
            "payment_processor_name": "manual",
            "verified": True,
            "canceled": False,
            # time delta: valid for a week?
            "valid_until": dt.now() + timedelta(days=5),
            "display_info": "pytest",
            "data": json.dumps({
                "attempt_retries_after": 2,
                "stop_retry_attempts": 5
            })
        }
        PaymentMethod = self.client.get_model('PaymentMethod')
        new_pm = PaymentMethod(**customer_default_payment_method)
        # new_pm.customer = str(customer_id)
        pm_endpoint = kleint.customers.customers_payment_methods_create
        preq = pm_endpoint(customer_pk=str(customer_id), data=new_pm)
        pmeth = preq.response().result


        ## Get a provider
        # TODO: determine who we want as default
        # 
        providers_list = kleint.providers.providers_list().response().result
        provider = providers_list[0]

        ## Create an invoice
        # Some defaults to save effort from the client user
        # 
        Invoice = self.client.get_model('Invoice')

        invoice_one_off_defaults = {
            "provider": provider.url,
            "series": provider.invoice_series,
            "customer": customer_url,
            "transaction_currency": "USD",
            "transaction_xe_rate": "1.0000",
            # "transaction_xe_date": dt.datetime(2019, 1, 15, 0, 0, 0),
            "proforma": None,
            "currency": "USD",
            "state": "issued",
        }

        invoice_intry_defaults = {
            "start_date": None,
            "end_date": None,
            "prorated": False,
            "product_code": None
        }

        new_entry = invoice_intry_defaults.copy()
        new_entry.update(**kwargs.get('invoice_entry', {}))

        new_invoice = invoice_one_off_defaults.copy()
        new_invoice.update(**kwargs.get('invoice', {}))
        new_invoice['invoice_entries'] = [new_entry]

        inv = Invoice(**new_invoice)

        inv_result = kleint.invoices.invoices_create(data=inv).response().result

        ## Get transactions for the invoice
        trx_req = kleint.customers.customers_transactions_list(customer_pk=str(customer_id))
        trx = trx_req.response().result

        return {
            'customer': res,
            'invoice': inv_result,
            'payment_method': pmeth,
            'transactions': trx,
        }

        return

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

