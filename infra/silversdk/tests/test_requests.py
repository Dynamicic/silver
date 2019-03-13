# Copyright (c) 2015 Presslabs SRL
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import

import pytest
import unittest
import datetime
import json

from silversdk.client import *

class TestClientRequests(unittest.TestCase):

    def setUp(self):
        self.client = SilverClient()

    @pytest.mark.skip
    def test_get_customer(self):

        customers = self.client.client.customers.customers_list()

        custs = customers.response()

        print(custs.result[0])

        assert len(custs.incoming_response.text) > 1
        assert len(custs.result) > 1

    def test_create_provider(self):
        Provider = self.client.client.get_model('Provider')
        new_provider = {
            "name": "Pytest Billing Provider",
            "company": "Jumbo Company",
            "invoice_series": "BPInvoiceSeries",
            "flow": "invoice",
            "email": "",
            "address_1": "1 Mulberry Lane",
            "address_2": "",
            "city": "Pacoima",
            "state": "CA",
            "zip_code": "",
            "country": "US",
            "invoice_starting_number": 1
        }

        exists = self.client.client.providers.providers_list().response().result

        if len(exists) == 0:
            provider = self.client.client.providers.providers_create(data=new_provider).response().result
        else:
            provider = exists[0]

        assert provider.name == new_provider['name']

    def test_create_customer(self):
        from datetime import datetime as dt

        # TODO: flatten meta
        new_cust = {
            "first_name": "PyTest",
            "last_name": "PyTest",
            "company": "Some Jumbo Company",
            "email": "asdf@bbq.com",
            "address_1": "1234 Mulberry Lane",
            "city": "Nantucket",
            "state": "Hawaii",
            "zip_code": "41414",
            "country": "US",
            "currency": "USD",
            "meta": {
                "cardNumber": "4111111111111111",
                "cardCode": "123",
                "expirationDate": "2020-12"
            }
        }

        request_endpoint = self.client.shortcuts.create_one_off_transaction

        one_off_intry = {
            "description": "Charcoal Latte",
            "unit": "Cup",
            "unit_price": "25.0000",
            "quantity": "2.0000",
            "total_before_tax": "50.0",
        }

        new_invoice =  {
            # "provider": "http://dev.billing.dynamicic.com/silver/providers/{% response 'body', 'req_c79d6d1d6b9743bfb8d213be8749efd9', '$.id' %}/",
            # "customer": customer_url,
            "due_date": "2019-02-01",
            "issue_date": datetime.date(2019, 1, 15),
            "sales_tax_name": "sales tax",
            "sales_tax_percent": "0.05",
            "invoice_entries": [
                one_off_intry
            ]
        }

        res = request_endpoint(customer=new_cust,
                               invoice_entry=one_off_intry
                               )
        print(res.get('transactions'))
        assert len(res.get('transactions')) > 0
        # assert res.get('invoice', False) == 0


        req = {
            'customer': new_cust,
            'invoice': new_invoice,
        }
