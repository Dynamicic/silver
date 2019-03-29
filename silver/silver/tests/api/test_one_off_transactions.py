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

import json
import pytest
import datetime

from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from silver.models import Customer
from silver.tests.factories import AdminUserFactory, CustomerFactory
from silver.tests.utils import build_absolute_test_url


class TestCustomerEndpoints(APITestCase):

    def setUp(self):
        admin_user = AdminUserFactory.create()
        self.client.force_authenticate(user=admin_user)
        # self.complete_data = {
        #     "customer_reference": "123456",
        #     "first_name": "Bruce",
        #     "last_name": "Wayne",
        #     "company": "Wayne Enterprises",
        #     "email": "bruce@wayneenterprises.com",
        #     "address_1": "Batcave St.",
        #     "address_2": "Some other address info",
        #     "city": "Gotham",
        #     "state": "SomeState",
        #     "zip_code": "1111",
        #     "country": "US",
        #     "phone": "+40000000000",
        #     "currency": "USD",
        #     "extra": "What is there more to say?",
        #     "sales_tax_number": "RO5555555",
        #     "sales_tax_name": "VAT",
        #     "sales_tax_percent": '3.00',
        #     "payment_due_days": 5,
        #     "consolidated_billing": False,
        #     "meta": {'water': ['plants', '5']},
        #     "payment_methods": build_absolute_test_url(reverse('payment-method-list',
        #                                                        kwargs={'customer_pk': 1})),
        #     "transactions": build_absolute_test_url(reverse('transaction-list',
        #                                                     kwargs={'customer_pk': 1}))
        # }

    @pytest.mark.skip
    def test_get_customer(self):

        customers = self.client.client.customers.customers_list()

        custs = customers.response()


        assert len(custs.incoming_response.text) > 1
        assert len(custs.result) > 1

    @pytest.mark.skip
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


    @pytest.mark.django_db
    @pytest.mark.skip
    def test_create_post_customer(self):
        url = reverse('payment-method-transaction-one-off')

        response = self.client.post(url, json.dumps({"data": "test"}), # json.dumps(self.complete_data),
                                    content_type='application/json')

        print(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)


    @pytest.mark.django_db
    def test_create_customer(self):
        from datetime import datetime as dt

        url = reverse('payment-method-transaction-one-off')

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

        one_off_intry = {
            "description": "Charcoal Latte",
            "unit": "Cup",
            "unit_price": "25.0000",
            "quantity": "2.0000",
            "total_before_tax": "50.0",
        }

        new_invoice =  {
            "due_date": "2019-02-01",
            "issue_date": "2019-01-15",
            "sales_tax_name": "sales tax",
            "sales_tax_percent": "0.05",
        }

        req = json.dumps({
            "customer": new_cust,
            "invoice": new_invoice,
            "entry": one_off_intry,
            "amount": 25.0
        })

        response = self.client.post(url, req,
                                    content_type='application/json')

        assert float( response.data.get('transaction').get('amount', "-1")) == 25.0
        assert response.data.get('customer').get('account_id', False) != False

    @pytest.mark.django_db
    def test_create_customer_try_reuse(self):
        from datetime import datetime as dt

        url = reverse('payment-method-transaction-one-off')

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

        one_off_intry = {
            "description": "Charcoal Latte",
            "unit": "Cup",
            "unit_price": "25.0000",
            "quantity": "2.0000",
            "total_before_tax": "50.0",
        }

        new_invoice =  {
            "due_date": "2019-02-01",
            "issue_date": "2019-01-15",
            "sales_tax_name": "sales tax",
            "sales_tax_percent": "0.05",
        }

        req = json.dumps({
            "customer": new_cust,
            "invoice": new_invoice,
            "entry": one_off_intry,
            "amount": 25.0
        })

        response = self.client.post(url, req,
                                    content_type='application/json')

        account_id = response.data.get('customer').get('account_id', False)
        assert account_id != False

        assert Customer.objects.all().count() == 1


        existing_customer = {
            "account_id": account_id,
        }

        update_req = json.dumps({
            "customer": existing_customer,
            "invoice": new_invoice,
            "entry": one_off_intry,
            "amount": 25.0
        })

        response = self.client.post(url, update_req,
                                    content_type='application/json')

        new_account_id = response.data.get('customer').get('account_id', False)

        assert account_id == new_account_id
        assert Customer.objects.filter(account_id=account_id).count() == 1

