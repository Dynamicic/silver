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

@override_settings(PAYMENT_PROCESSORS=PAYMENT_PROCESSORS)
class TestTransactionOverpayments(TestCase):


    def __init__(self, *args, **kwargs):
        super(TestTransactionOverpayments, self).__init__(*args, **kwargs)
        self.output = StringIO()

    @pytest.mark.django_db
    def test_create_negative_transaction(self):
        """ Confirm that a transaction can have a negative value. """

        transaction = TransactionFactory.create(
            state=Transaction.States.Pending,
            amount=-150.0
        )
        transaction.settle()
        transaction.save()
        assert Transaction.objects.all().count() == 1

    @pytest.mark.django_db
    def test_create_negative_document(self):
        """ Confirm that an invoice can be issued with a negative value. """

        # 0 for easy asserting.
        customer = CustomerFactory(sales_tax_percent=0, currency='USD')

        entry = DocumentEntryFactory(quantity=1, unit_price=-150)
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
            amount=invoice.total_in_transaction_currency,
            state=Transaction.States.Initial
        )

        assert invoice.transactions.count() == 1
        assert invoice.total_in_transaction_currency == -150
        assert transaction.amount == -150

    @pytest.mark.django_db
    def test_create_invoice_overpayment_transaction(self):
        """ An invoice is issued, and it is paid in two transactions:
            one for half the amount, and another for well over the
            amount. """

        # Create a simple invoice
        entry = DocumentEntryFactory(quantity=1, unit_price=250)
        invoice = InvoiceFactory.create(invoice_entries=[entry])
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
            amount=invoice.total_in_transaction_currency / 2,
            state=Transaction.States.Initial
        )

        transaction.settle()
        transaction.save()

        assert invoice.state != Invoice.STATES.PAID

        transaction_over = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            amount=invoice.total_in_transaction_currency * 2,
            # NB:
            overpayment=True,
            state=Transaction.States.Initial
        )

        transaction_over.settle()
        transaction_over.save()

        assert invoice.state != Invoice.STATES.PAID

        invoice.pay()
        assert invoice.state == Invoice.STATES.PAID

        assert invoice.total_in_transaction_currency != \
                invoice.amount_paid_in_transaction_currency

        # Payment calculation works even with overpayment.
        assert invoice.amount_paid_in_transaction_currency == \
            ((invoice.total_in_transaction_currency / 2) + \
             (invoice.total_in_transaction_currency * 2))

    @pytest.mark.django_db
    def test_customer_balance_calculation_with_overpayments(self):
        """ An invoice is issued, and it is paid in two transactions:
            one for half the amount, and another for well over the
            amount. """
        # 0 for easy asserting.
        customer = CustomerFactory(sales_tax_percent=0, currency='USD',
                                   first_name="Bob", last_name="Smith")
        customer.save()

        payment_method = PaymentMethodFactory.create(
            payment_processor=triggered_processor,
            customer=customer,
            canceled=False
        )

        # Create a simple invoice
        entry = DocumentEntryFactory(quantity=1, unit_price=250)
        invoice = InvoiceFactory.create(invoice_entries=[entry],
                                        customer=customer)
        invoice.issue()

        # Customer underpays by half
        transaction = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            amount=125.00,
            state=Transaction.States.Initial
        )

        transaction.settle()
        transaction.save()

        assert invoice.state != Invoice.STATES.PAID

        # Customer overpays by double
        transaction_over = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            amount=500,
            # NB:
            overpayment=True,
            state=Transaction.States.Initial
        )

        transaction_over.settle()
        transaction_over.save()

        assert invoice.state != Invoice.STATES.PAID

        invoice.pay()
        assert invoice.state == Invoice.STATES.PAID

        # Payment calculation works even with overpayment.
        assert invoice.amount_paid_in_transaction_currency == \
            ((invoice.total_in_transaction_currency / 2) + \
             (invoice.total_in_transaction_currency * 2))

        # Customer paid 625 total, for an invoice of 250
        # Current balance: 375.00
        overpayment = abs(
            invoice.total_in_transaction_currency - \
                ((invoice.total_in_transaction_currency / 2) + \
                 (invoice.total_in_transaction_currency * 2))
        )

        assert invoice.total_in_transaction_currency == 250.00
        assert overpayment == Decimal(375.00)
        assert customer.balance == overpayment

    @pytest.mark.django_db
    def test_correct_overpayment(self):
        """ An invoice is issued, and it is overpaid. A correction is issued
            """

        # 0 for easy asserting.
        customer = CustomerFactory(sales_tax_percent=0, currency='USD',
                                   first_name="Bob", last_name="Smith")
        customer.save()

        payment_method = PaymentMethodFactory.create(
            payment_processor=triggered_processor,
            customer=customer,
            canceled=False
        )

        # Create a simple invoice
        entry = DocumentEntryFactory(quantity=1, unit_price=150)
        invoice = InvoiceFactory.create(invoice_entries=[entry],
                                        customer=customer,
                                        transaction_currency='USD')
        invoice.issue()
        invoice.save()

        assert PaymentMethod.objects.count() == 1
        assert Invoice.objects.count() == 1
        assert BillingDocumentBase.objects.count() == 1

        # Customer overpays by 2x
        transaction = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            overpayment=True,
            amount=300,
            state=Transaction.States.Initial
        )
        transaction.settle()
        transaction.save()

        invoice.pay()

        assert invoice.state == Invoice.STATES.PAID
        assert PaymentMethod.objects.count() == 1
        assert Invoice.objects.count() == 1
        # Proforma issued as well
        assert BillingDocumentBase.objects.count() == 2
        assert customer.balance == Decimal(150)

        # # Create a repayment invoice
        entry = DocumentEntryFactory(quantity=1, unit_price=-150)
        invoice = InvoiceFactory.create(invoice_entries=[entry],
                                        customer=customer,
                                        state=Invoice.STATES.DRAFT,
                                        transaction_currency='USD')
        invoice.save()
        assert customer.balance == Decimal(150)

        invoice.issue()
        invoice.save()
        assert customer.balance == Decimal(150)

        # This is the transaction to correct the balance. We're using
        # .settle() here, but we will need another method (forthcoming).
        transaction = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            overpayment=True,
            amount=-150,
            state=Transaction.States.Initial
        )

        transaction.settle()
        transaction.save()

        assert invoice.state == Invoice.STATES.PAID
        assert customer.balance == Decimal(0)

    def test_transaction_process_credit(self):
        """ Test that transaction states work correctly with
        `Transaction.process_credit`. """

        transaction = TransactionFactory.create(
            amount=-150,
            state=Transaction.States.Initial
        )
        transaction.process_credit()
        assert transaction.state == Transaction.States.Pending

        transaction.settle()
        assert transaction.state == Transaction.States.Settled

    @pytest.mark.django_db
    def test_overpayment_checker_creates_defaults(self):
        from silver.overpayment_checker import OverpaymentChecker

        op = OverpaymentChecker()
        p = op.default_provider

        assert p.meta.get('overpayment_checker') == True

        # Check that this happens only once.
        op = OverpaymentChecker()
        p = op.default_provider
        assert p.meta.get('overpayment_checker') == True

    @pytest.mark.django_db
    def test_overpayment_checker_process(self):
        from silver.overpayment_checker import OverpaymentChecker

        customer = CustomerFactory(sales_tax_percent=0, # 0 for easy asserting.
                                   currency='USD',
                                   first_name="Bob",
                                   last_name="Smith")
        customer.save()

        # Create customer payment method
        #
        payment_method = PaymentMethodFactory.create(
            payment_processor=triggered_processor,
            customer=customer,
            canceled=False
        )
        payment_method.save()

        # Create a simple invoice.
        #
        entry = DocumentEntryFactory(quantity=1, unit_price=150)
        entry.save()
        invoice = InvoiceFactory.create(invoice_entries=[entry],
                                        customer=customer,
                                        transaction_currency='USD')
        invoice.issue()
        invoice.save()

        # Customer overpays by 2x
        #
        transaction = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            overpayment=True,
            amount=300,
            state=Transaction.States.Initial
        )
        transaction.settle()
        transaction.save()

        invoice.pay()

        assert invoice.state == Invoice.STATES.PAID
        assert customer.balance == Decimal(150)

        # Grab the overpayment defaults
        op = OverpaymentChecker()

        # Run the overpayment process
        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        # An invoice has been issued a for the correct amount.
        repayment = Invoice.objects.filter(provider=op.default_provider).first()
        assert Invoice.objects.filter(provider=op.default_provider).count() == 1
        assert repayment.total_in_transaction_currency == -150
        assert repayment.state == Invoice.STATES.ISSUED

        # Customer balance is still the same; payment has not occurred
        # yet.
        #
        assert customer.balance == Decimal(150)

        # Create the repayment transaction, this is supposed to happen
        # somewhere automatically.
        #
        repayment_tx = Transaction.objects.create(invoice=repayment,
                                                  amount=repayment.total_in_transaction_currency,
                                                  overpayment=True,
                                                  state=Transaction.States.Initial,
                                                  payment_method=payment_method)
        repayment_tx.settle()
        repayment_tx.save()

        # There's one transaction issued for this doc, and it has set
        # the state of the invoice to PAID. The customer's balance is
        # now 0.
        #
        assert repayment.state == Invoice.STATES.PAID
        assert repayment.transactions.count() == 1
        assert repayment.amount_paid_in_transaction_currency == -150
        assert repayment.customer.balance == Decimal(0)

    @pytest.mark.django_db
    def test_unsettled_overpayment_credit_does_not_duplicate_on_reruns(self):
        """ Create a negative balance, and rerun the overpayment
        checking process twice. Does this re-issue an overpayment
        correction? """
        from silver.overpayment_checker import OverpaymentChecker

        # 0 for easy asserting.
        customer = CustomerFactory(sales_tax_percent=0, currency='USD',
                                   first_name="Bob", last_name="Smith")
        customer.save()

        # Create customer payment method
        payment_method = PaymentMethodFactory.create(
            payment_processor=triggered_processor,
            customer=customer,
            canceled=False
        )
        payment_method.save()

        # Create a simple invoice
        entry = DocumentEntryFactory(quantity=1, unit_price=150)
        entry.save()
        invoice = InvoiceFactory.create(invoice_entries=[entry],
                                        customer=customer,
                                        transaction_currency='USD')
        invoice.issue()
        invoice.save()

        # Customer overpays by 2x
        transaction = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            overpayment=True,
            amount=300,
            state=Transaction.States.Initial
        )
        transaction.settle()
        transaction.save()

        invoice.pay()

        assert invoice.state == Invoice.STATES.PAID
        assert customer.balance == Decimal(150)

        # Grab the overpayment defaults
        op = OverpaymentChecker()

        # Run the overpayment process
        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        # An invoice has been issued a for the correct amount.
        repayment = Invoice.objects.filter(provider=op.default_provider).first()
        assert Invoice.objects.filter(provider=op.default_provider).count() == 1
        assert repayment.total_in_transaction_currency == -150
        assert repayment.state == Invoice.STATES.ISSUED

        # Customer balance is still the same; payment has not occurred
        # yet.
        assert customer.balance == Decimal(150)

        # Run the overpayment process a couple more times, does it duplicate
        # things?
        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        assert Invoice.objects.filter(provider=op.default_provider).count() == 1
        assert repayment.total_in_transaction_currency == -150
        assert repayment.state == Invoice.STATES.ISSUED

        # Customer balance is still the same; payment has not occurred
        # yet.
        assert customer.balance == Decimal(150)

        # Create the repayment transaction, this is supposed to happen
        # somewhere automatically.
        amt          = repayment.total_in_transaction_currency
        repayment_tx = Transaction.objects.create(invoice=repayment,
                                                  amount=amt,
                                                  overpayment=True,
                                                  state=Transaction.States.Initial,
                                                  payment_method=payment_method)
        repayment_tx.settle()
        repayment_tx.save()

        # There's one transaction issued for this doc, and it has set
        # the state of the invoice to PAID. The customer's balance is
        # now 0.
        assert repayment.state == Invoice.STATES.PAID
        assert repayment.transactions.count() == 1
        assert repayment.amount_paid_in_transaction_currency == -150
        assert repayment.customer.balance == Decimal(0)

    @pytest.mark.django_db
    def test_customer_balance_gte_zero(self):
        """ Create a zero and positive balance, and rerun the
        overpayment process: no invoices should be issued. """

        from silver.overpayment_checker import OverpaymentChecker

        # 0 for easy asserting.
        customer = CustomerFactory(sales_tax_percent=0, currency='USD',
                                   first_name="Bob", last_name="Smith")
        customer.save()

        # Create customer payment method
        payment_method = PaymentMethodFactory.create(
            payment_processor=triggered_processor,
            customer=customer,
            canceled=False
        )
        payment_method.save()

        # Create a simple invoice
        entry = DocumentEntryFactory(quantity=1, unit_price=150)
        entry.save()
        invoice = InvoiceFactory.create(invoice_entries=[entry],
                                        customer=customer,
                                        transaction_currency='USD')
        invoice.issue()
        invoice.save()

        # Customer pays an accurate amount.
        transaction = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            amount=150,
            state=Transaction.States.Initial
        )
        transaction.settle()
        transaction.save()

        assert invoice.state == Invoice.STATES.PAID
        assert Invoice.objects.filter(customer=customer).count() == 1
        assert customer.balance == Decimal(0)

        # Run the overpayment process
        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        provider = OverpaymentChecker().default_provider
        assert Invoice.objects.filter(provider=provider).count() == 0

        # Run the overpayment process a couple more times, does it duplicate
        # things?
        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        assert Invoice.objects.filter(provider=provider).count() == 0

    # @pytest.mark.django_db
    @pytest.mark.skip
    def test_balance_on_date(self):
        import pytz

        start_date   = dt.datetime(2019, 1,  1, 0, 0, 0, 0, tzinfo=pytz.UTC)
        invoice_date = dt.datetime(2019, 1, 15, 0, 0, 0, 0, tzinfo=pytz.UTC)
        payment_date = dt.datetime(2019, 1, 17, 0, 0, 0, 0, tzinfo=pytz.UTC)
        mid_date     = dt.datetime(2019, 1, 20, 0, 0, 0, 0, tzinfo=pytz.UTC)

        from silver.overpayment_checker import OverpaymentChecker

        # 0 for easy asserting.
        customer = CustomerFactory(sales_tax_percent=0, currency='USD',
                                   first_name="Bob", last_name="Smith")
        customer.save()

        assert customer.balance_on_date(date=start_date) == Decimal(0)

        ## Now we create an invoice situation after the start date...

        # Create customer payment method
        payment_method = PaymentMethodFactory.create(
            payment_processor=triggered_processor,
            customer=customer,
            canceled=False
        )
        payment_method.save()

        # Create a simple invoice
        entry = DocumentEntryFactory(quantity=1, unit_price=150)
        entry.save()
        invoice = InvoiceFactory.create(invoice_entries=[entry],
                                        due_date=invoice_date,
                                        customer=customer,
                                        transaction_currency='USD')
        invoice.issue()
        invoice.save()

        # Customer overpays by 2x
        transaction = TransactionFactory.create(
            invoice=invoice,
            payment_method=payment_method,
            created_at=payment_date,
            updated_at=payment_date,
            overpayment=True,
            amount=300,
            state=Transaction.States.Initial
        )
        transaction.settle()
        transaction.save()

        invoice.pay()

        assert invoice.state                               == Invoice.STATES.PAID
        assert customer.balance_on_date(date=start_date)   == Decimal(0)
        assert customer.balance_on_date(date=payment_date) == Decimal(0)
        # This balance should be 150, but it's not yet.
        assert customer.balance_on_date(date=mid_date)     == Decimal(150)
        return

        # Grab the overpayment defaults
        op = OverpaymentChecker()

        # Run the overpayment process
        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        # An invoice has been issued a for the correct amount.
        repayment = Invoice.objects.filter(provider=op.default_provider).first()
        assert Invoice.objects.filter(provider=op.default_provider).count() == 1
        assert repayment.total_in_transaction_currency == -150
        assert repayment.state == Invoice.STATES.ISSUED

        # Customer balance is still the same; payment has not occurred
        # yet.
        assert customer.balance == Decimal(150)

        # Run the overpayment process a couple more times, does it duplicate
        # things?
        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        call_command('check_overpayments',
                     billing_date=timezone.now().date(),
                     stdout=self.output)

        assert Invoice.objects.filter(provider=op.default_provider).count() == 1
        assert repayment.total_in_transaction_currency == -150
        assert repayment.state == Invoice.STATES.ISSUED

        # Customer balance is still the same; payment has not occurred
        # yet.
        assert customer.balance == Decimal(150)

        # Create the repayment transaction, this is supposed to happen
        # somewhere automatically.
        amt          = repayment.total_in_transaction_currency
        repayment_tx = Transaction.objects.create(invoice=repayment,
                                                  amount=amt,
                                                  overpayment=True,
                                                  state=Transaction.States.Initial,
                                                  payment_method=payment_method)
        repayment_tx.settle()
        repayment_tx.save()

        # There's one transaction issued for this doc, and it has set
        # the state of the invoice to PAID. The customer's balance is
        # now 0.
        assert repayment.state == Invoice.STATES.PAID
        assert repayment.transactions.count() == 1
        assert repayment.amount_paid_in_transaction_currency == -150
        assert repayment.customer.balance == Decimal(0)



