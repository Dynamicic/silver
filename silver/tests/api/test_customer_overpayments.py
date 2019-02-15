from __future__ import absolute_import

import pytest

from decimal import Decimal
import datetime as dt

import json

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.six import StringIO

from mock import patch

from silver.tests.utils import build_absolute_test_url

from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework.reverse import reverse

from silver.tests.fixtures import (TriggeredProcessor,
                                   PAYMENT_PROCESSORS,
                                   triggered_processor)

from silver.models import (Proforma,
                           DocumentEntry,
                           Invoice,
                           PaymentMethod,
                           BillingDocumentBase,
                           Transaction,
                           Subscription,
                           Customer,
                           Plan,
                           BillingLog)

from silver.tests.factories import (CustomerFactory,
                                    AdminUserFactory,
                                    DocumentEntryFactory,
                                    InvoiceFactory,
                                    MeteredFeatureFactory,
                                    MeteredFeatureUnitsLogFactory,
                                    PaymentMethodFactory,
                                    PlanFactory,
                                    ProformaFactory,
                                    ProviderFactory,
                                    SubscriptionFactory,
                                    TransactionFactory)


import logging
logging.basicConfig(level=logging.WARNING)


from rest_framework.reverse import reverse as _reverse
def reverse(*args, **kwargs):
    """ Fix URLs to remove http://testserver/, which breaks tests.
    """
    return build_absolute_test_url(_reverse(*args, **kwargs))

class TestCustomerEndpoints(APITestCase):
    """ Test that the endpoints work with balance modifications.
    """

    def setUp(self):
        admin_user = AdminUserFactory.create()
        self.client.force_authenticate(user=admin_user)
        self.complete_data = {
            "customer_reference": "123456",
            "first_name": "Bruce",
            "last_name": "Wayne",
            "company": "Wayne Enterprises",
            "email": "bruce@wayneenterprises.com",
            "address_1": "Batcave St.",
            "address_2": "Some other address info",
            "city": "Gotham",
            "state": "SomeState",
            "zip_code": "1111",
            "country": "US",
            "phone": "+40000000000",
            "currency": "USD",
            "extra": "What is there more to say?",
            "sales_tax_number": "RO5555555",
            "sales_tax_name": "VAT",
            "sales_tax_percent": '3.00',
            "payment_due_days": 5,
            "consolidated_billing": False,
            "meta": {'water': ['plants', '5']},
            "payment_methods": build_absolute_test_url(
                reverse('payment-method-list', kwargs={'customer_pk': 1})
            ),
            "transactions": build_absolute_test_url(
                reverse('transaction-list', kwargs={'customer_pk': 1})
            )
        }

    def test_create_post_customer(self):
        url = reverse('customer-list')

        response = self.client.post(url, json.dumps(self.complete_data),
                                    content_type='application/json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        response = self.client.get(reverse('customer-detail', args=[1]))
        assert response.data.get('balance', False) == Decimal(0)

    @pytest.mark.django_db
    def test_create_invoice_overpayment_transaction(self):
        """ Confirm that the balance property is updating automatically
        through the REST API as well. """

        # 0 for easy asserting.
        customer = CustomerFactory(sales_tax_percent=0, currency='USD')
        entry = DocumentEntryFactory(quantity=1, unit_price=150)
        invoice = InvoiceFactory.create(invoice_entries=[entry], customer=customer)
        invoice.issue()

        customer = invoice.customer
        payment_method = PaymentMethodFactory.create(
            payment_processor=triggered_processor,
            customer=customer,
            canceled=False
        )

        transaction = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            amount=invoice.total_in_transaction_currency * 2,
            # NB:
            overpayment=True,
            state=Transaction.States.Initial
        )

        transaction.settle()
        transaction.save()
        invoice.pay()

        response = self.client.get(reverse('customer-detail', args=[1]))
        assert response.data.get('balance', False) == Decimal(150)

@override_settings(PAYMENT_PROCESSORS=PAYMENT_PROCESSORS)
class TestTransactionOvepaymentEndpoint(APITestCase):
    def setUp(self):
        self.user = AdminUserFactory.create()
        self.client.force_authenticate(user=self.user)

    @pytest.mark.django_db
    def test_get_transaction(self):
        """ Test that the endpoint works.
        """
        customer = CustomerFactory.create()
        payment_method = PaymentMethodFactory.create(customer=customer)

        transaction = TransactionFactory.create(payment_method=payment_method)
        expected = self._transaction_data(transaction)

        with patch('silver.utils.payments._get_jwt_token') as mocked_token:
            mocked_token.return_value = 'token'

            url = reverse('transaction-detail',
                          kwargs={'customer_pk': customer.pk,
                                  'transaction_uuid': transaction.uuid})
            response = self.client.get(url, format='json')

            self.assertEqual(response.data, dict(expected))

    def _transaction_data(self, transaction):
        """ Helper to create transaction data
        """
        from django.utils.encoding import force_text
        from collections import OrderedDict
        from silver.utils.payments import get_payment_url

        transaction.refresh_from_db()

        payment_method = transaction.payment_method
        customer = transaction.customer
        provider = transaction.provider
        proforma = transaction.proforma
        invoice = transaction.invoice

        with patch('silver.utils.payments._get_jwt_token') as mocked_token:
            mocked_token.return_value = 'token'

            return OrderedDict([
                ('id', force_text(transaction.uuid)),
                ('url', reverse('transaction-detail',
                                kwargs={'customer_pk': customer.id,
                                        'transaction_uuid': transaction.uuid})),
                ('customer', reverse('customer-detail', args=[customer.pk])),
                ('provider', reverse('provider-detail', args=[provider.pk])),
                ('amount', force_text(Decimal('0.00') + transaction.amount)),
                ('currency', force_text(transaction.currency)),
                ('state', force_text(transaction.state)),
                ('overpayment', False),
                ('proforma', reverse('proforma-detail', args=[proforma.pk])),
                ('invoice', reverse('invoice-detail', args=[invoice.pk])),
                ('can_be_consumed', transaction.can_be_consumed),
                ('payment_processor', payment_method.payment_processor),
                ('payment_method', reverse(
                    'payment-method-detail',
                    kwargs={
                        'customer_pk': customer.id,
                        'payment_method_id': payment_method.id
                    })),
                ('pay_url', build_absolute_test_url(
                    get_payment_url(transaction, None)
                )),
                ('valid_until', None),

                ('updated_at', transaction.updated_at.isoformat()[:-6] + 'Z'),
                ('created_at', transaction.created_at.isoformat()[:-6] + 'Z'),
                ('fail_code', transaction.fail_code),
                ('refund_code', transaction.refund_code),
                ('cancel_code', transaction.cancel_code)
            ])

    def test_add_overpaid_transaction(self):
        """ Test that we can add an overpayment transaction
        """
        from datetime import datetime, timedelta
        from django.utils.encoding import force_text

        customer = CustomerFactory.create()
        payment_method = PaymentMethodFactory.create(customer=customer)

        entry = DocumentEntryFactory(quantity=1, unit_price=200)
        proforma = ProformaFactory.create(customer=customer,
                                          proforma_entries=[entry])
        proforma.issue()
        proforma.create_invoice()
        proforma.refresh_from_db()
        invoice = proforma.related_document

        payment_method_url = reverse('payment-method-detail',
                                     kwargs={'customer_pk': customer.pk,
                                             'payment_method_id': payment_method.id})

        invoice_url = reverse('invoice-detail', args=[invoice.pk])
        proforma_url = reverse('proforma-detail', args=[proforma.pk])

        url = reverse('payment-method-transaction-list',
                      kwargs={'customer_pk': customer.pk,
                              'payment_method_id': payment_method.pk})

        valid_until = datetime.now().replace(microsecond=0) + timedelta(minutes=30)

        currency = invoice.transaction_currency

        data = {
            'payment_method': reverse('payment-method-detail',
                                      kwargs={'customer_pk': customer.pk,
                                              'payment_method_id': payment_method.id}),
            'amount': invoice.total_in_transaction_currency + 100,
            'overpayment': True,
            'invoice': invoice_url,
            'proforma': proforma_url,
            'valid_until': valid_until,
            'currency': currency,
        }

        response = self.client.post(url, format='json', data=data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertNotEqual(response.data['amount'],
                            force_text(invoice.total_in_transaction_currency))
