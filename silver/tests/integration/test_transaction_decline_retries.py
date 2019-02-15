from __future__ import absolute_import

from decimal import Decimal
import datetime as dt
import pytest
import pytz

from django.core import mail
from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.test import SimpleTestCase, override_settings
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
        assert len(c) == 1

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
        assert len(c) == 1

        # payment method is not configured to allow retry attempts.
        attempts.check(billing_date=timezone.now())

        assert proforma.transactions.count() == 1
        assert invoice.transactions.count() == 1

    @pytest.mark.django_db
    def test_cannot_issue_new_transaction_while_pending(self):
        """ The TransactionRetryAttempter should only be able to issue
        transactions while there are no pending re-attempted Transactions
        with state Issued. """

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

        # Spam some attempts
        attempts.check(billing_date=retry_begins)
        attempts.check(billing_date=retry_begins)
        attempts.check(billing_date=retry_begins)
        attempts.check(billing_date=retry_begins)

        assert trx.invoice.transactions.count() == 2

        # Spam some attempts with force. 
        attempts.check(billing_date=retry_begins, force=True)
        attempts.check(billing_date=retry_begins, force=True)
        attempts.check(billing_date=retry_begins, force=True)
        attempts.check(billing_date=retry_begins, force=True)

        assert trx.invoice.transactions.count() == 2

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

        # NB: payment method is not configured to allow retry attempts.
        attempts.check(billing_date=initial_try)
        assert trx.invoice.transactions.count() == 1

        attempts.check(billing_date=retry_begins)
        assert trx.invoice.transactions.count() == 2

    @pytest.mark.django_db
    def test_management_command(self):
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

        call_command('retry_failed_transactions',
                     billing_date=initial_try,
                     stdout=self.output)

        assert trx.invoice.transactions.count() == 1

        call_command('retry_failed_transactions',
                     billing_date=retry_begins,
                     stdout=self.output)

        assert trx.invoice.transactions.count() == 2

    @pytest.mark.django_db
    def test_rerun_declined_transactions_for_pair(self):
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

        # payment method is not configured to allow retry attempts.
        attempts.check(billing_date=initial_try)
        assert trx.invoice.transactions.count() == 1

        attempts.check(billing_date=retry_begins)
        assert trx.invoice.transactions.count() == 2

    @override_settings(EMAIL_ON_TRANSACTION_FAIL=True,
                       MANAGERS=(('Admin', 'admin@example.com')))
    def test_transaction_failure_sends_emails(self):
        """
            * EMAIL_ON_TRANSACTION_FAIL = True
            * SERVER_EMAIL
            * EMAIL_SUBJECT_PREFIX
            * MANAGERS must be set
        """

        transaction = TransactionFactory.create(
            state=Transaction.States.Pending
        )
        transaction.fail()
        transaction.save()

        self.assertEqual(len(mail.outbox), 1)


    @pytest.mark.skip
    def test_subscription_failed_payment_retry(self):
        """ A subscription creates an invoice, the attempt fails.
        """

        pass

    @pytest.mark.skip
    def test_subscription_failed_payment_retries_after_canceled(self):
        """ Do we want to be able to issue repayment attempts on a
        subscription where a failed transaction has lead to subscription
        cancellation?

        Also: need to test that subscriptions won't be cancelled if
        there is a payment attempt in progress when the customer payment
        grace period ends.

        """

        pass

