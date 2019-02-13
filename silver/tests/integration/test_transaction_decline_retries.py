from __future__ import absolute_import

from decimal import Decimal
import datetime as dt
import pytest
import pytz

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from silver.models import Invoice, Proforma, Transaction, Subscription
from silver.tests.factories import (PaymentMethodFactory, InvoiceFactory,
                                    ProformaFactory, TransactionFactory,
                                    CustomerFactory)
from silver.tests.fixtures import (PAYMENT_PROCESSORS, triggered_processor)


from silver.management.commands.generate_docs import date as generate_docs_date
from silver.models import (Proforma, DocumentEntry, Invoice, Subscription, Customer, Plan,
                           BillingLog)
from silver.tests.factories import (SubscriptionFactory, PlanFactory,
                                    MeteredFeatureFactory,
                                    MeteredFeatureUnitsLogFactory,
                                    CustomerFactory, ProviderFactory)
from silver.utils.dates import ONE_DAY

from django.utils.six import StringIO

import logging
logging.basicConfig(level=logging.INFO)

@override_settings(PAYMENT_PROCESSORS=PAYMENT_PROCESSORS)
class TestTransactionDeclineRetries(TestCase):

    def __init__(self, *args, **kwargs):
        super(TestTransactionDeclineRetries, self).__init__(*args, **kwargs)
        self.output = StringIO()

    def _create_default_payment_method(self):
        # 0 for easy asserting.
        customer = CustomerFactory(sales_tax_percent=0,
                                   currency='USD',
                                   first_name="Captain",
                                   last_name="Hook")

        # Create customer payment method
        payment_method = PaymentMethodFactory.create(
            payment_processor=triggered_processor,
            customer=customer,
            canceled=False,
            verified=True,
            data={
                # Wait until payment day X to begin retry attempts
                'attempt_retries_after': 2,

                # Stop attempts on day X
                'stop_retry_attempts': 5,
            }
        )

        return customer, payment_method

    @pytest.mark.django_db
    def test_transaction_metadata(self):
        """ Test that basic setup works.
        """

        from silver.overpayment_checker import OverpaymentChecker

        customer, payment_method = self._create_default_payment_method()

        customer.save()
        payment_method.save()

        assert payment_method.data.get('attempt_retries_after') == 2
        assert payment_method.data.get('stop_retry_attempts') == 5

    @pytest.mark.django_db
    def test_pay_documents_on_transaction_fail(self):
        """ Confirm that a transaction can fail, and documents will be
        left unpaid. """

        transaction = TransactionFactory.create(
            state=Transaction.States.Pending
        )
        transaction.fail()
        transaction.save()

        proforma = transaction.proforma
        invoice = transaction.invoice

        self.assertNotEqual(proforma.state, proforma.STATES.PAID)
        self.assertNotEqual(invoice.state, invoice.STATES.PAID)

    @pytest.mark.django_db
    def test_failed_docs_query(self):
        from silver.transaction_retries import TransactionRetryAttempter
        attempts = TransactionRetryAttempter()

        c = list(attempts._query_payment_failures())
        assert len(c) == 0

        b = TransactionFactory(state=Transaction.States.Failed)
        b.save()

        c = list(attempts._query_payment_failures())
        # nb: generates proforma + invoice
        assert len(c) == 2

    @pytest.mark.django_db
    def test_no_new_attempts_for_existing_functionality(self):
        from silver.transaction_retries import TransactionRetryAttempter
        attempts = TransactionRetryAttempter()

        c = list(attempts._query_payment_failures())
        assert len(c) == 0

        b = TransactionFactory(state=Transaction.States.Failed)
        b.save()

        invoice = b.invoice
        proforma = b.proforma

        c = list(attempts._query_payment_failures())
        assert len(c) == 2

        # payment method is not configured to allow retry attempts.
        attempts.check(billing_date=timezone.now())

        assert proforma.transactions.count() == 1
        assert invoice.transactions.count() == 1

    @pytest.mark.django_db
    def test_rerun_declined_transactions_for_invoice(self):
        from silver.transaction_retries import TransactionRetryAttempter
        attempts = TransactionRetryAttempter()

        initial_try  = dt.datetime(2019, 1,  1, 0, 0, 0, 0, tzinfo=pytz.UTC)
        retry_begins = dt.datetime(2019, 1,  3, 0, 0, 0, 0, tzinfo=pytz.UTC)
        retry_ends   = dt.datetime(2019, 1,  5, 0, 0, 0, 0, tzinfo=pytz.UTC)

        customer, payment_method = self._create_default_payment_method()

        customer.save()
        payment_method.save()

        trx = TransactionFactory(state=Transaction.States.Failed,
                                 created_at=initial_try,
                                 updated_at=initial_try,
                                 proforma=None,
                                 payment_method=payment_method)
        trx.save()

        assert trx.invoice.transactions.count() == 1
        # assert trx.proforma.transactions.count() == 1

        # payment method is not configured to allow retry attempts.
        attempts.check(billing_date=initial_try)

        # assert trx.proforma.transactions.count() == 1
        assert trx.invoice.transactions.count() == 1

        attempts.check(billing_date=retry_begins)

        # TODO: 
        # assert trx.proforma.transactions.count() == 2
        assert trx.invoice.transactions.count() == 2


    @pytest.mark.django_db
    @pytest.mark.skip
    def test_rerun_declined_transactions_for_pair(self):
        # TODO: think through: is it the correct behavior that a single
        # transaction represents both a proforma and invoice? When both
        # are associated, a new transaction is created for both the
        # proforma and the invoice, when perhaps one should be created
        # 
        # Test may need to be rewritten from the perspective of a
        # billing doc, not with TransactionFactory handling it all.
        #
        from silver.transaction_retries import TransactionRetryAttempter
        attempts = TransactionRetryAttempter()

        initial_try  = dt.datetime(2019, 1,  1, 0, 0, 0, 0, tzinfo=pytz.UTC)
        retry_begins = dt.datetime(2019, 1,  3, 0, 0, 0, 0, tzinfo=pytz.UTC)
        retry_ends   = dt.datetime(2019, 1,  5, 0, 0, 0, 0, tzinfo=pytz.UTC)

        customer, payment_method = self._create_default_payment_method()

        customer.save()
        payment_method.save()

        trx = TransactionFactory(state=Transaction.States.Failed,
                                 created_at=initial_try,
                                 updated_at=initial_try,
                                 payment_method=payment_method)
        trx.save()

        assert trx.invoice.transactions.count() == 1
        # assert trx.proforma.transactions.count() == 1

        # payment method is not configured to allow retry attempts.
        attempts.check(billing_date=initial_try)

        # assert trx.proforma.transactions.count() == 1
        assert trx.invoice.transactions.count() == 1

        attempts.check(billing_date=retry_begins)

        assert trx.proforma.transactions.count() == 2
        assert trx.invoice.transactions.count() == 2

