from __future__ import absolute_import

from decimal import Decimal
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from silver.tests.fixtures import (TriggeredProcessor,
                                   PAYMENT_PROCESSORS,
                                   triggered_processor)

from silver.models import (Proforma,
                           DocumentEntry,
                           Invoice,
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
logging.basicConfig(level=logging.INFO)

@override_settings(PAYMENT_PROCESSORS=PAYMENT_PROCESSORS)
class TestTransactionOverpayments(TestCase):

    def __init__(self, *args, **kwargs):
        super(TestTransactionOverpayments, self).__init__(*args, **kwargs)
        self.output = StringIO()

    def test_create_negative_transaction(self):
        """ Confirm that a transaction can fail. """

        transaction = TransactionFactory.create(
            state=Transaction.States.Pending,
            amount=-150.0
        )
        transaction.save()


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

    def test_customer_balance_calculation_with_overpayments(self):
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

        # Payment calculation works even with overpayment.
        assert invoice.amount_paid_in_transaction_currency == \
            ((invoice.total_in_transaction_currency / 2) + \
             (invoice.total_in_transaction_currency * 2))

        overpayment = abs(
            invoice.total_in_transaction_currency - \
                ((invoice.total_in_transaction_currency / 2) + \
                 (invoice.total_in_transaction_currency * 2))
        )

        assert invoice.total_in_transaction_currency == 252.50
        assert overpayment == Decimal(378.75)

        assert customer.balance == Decimal(overpayment)


