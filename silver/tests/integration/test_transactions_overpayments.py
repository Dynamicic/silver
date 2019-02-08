from __future__ import absolute_import

import pytest

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

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

from django.utils.six import StringIO

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
        # TODO: different method needed to settle repayment.
        transaction.settle()
        transaction.save()

        assert invoice.state == Invoice.STATES.PAID
        assert customer.balance == Decimal(0)

