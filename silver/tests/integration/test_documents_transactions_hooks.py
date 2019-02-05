# Copyright (c) 2017 Presslabs SRL
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

from decimal import Decimal
import datetime as dt

from django.core.management import call_command
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from silver.models import Invoice, Proforma, Transaction
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


@override_settings(PAYMENT_PROCESSORS=PAYMENT_PROCESSORS)
class TestDocumentsTransactionSubscriptions(TestCase):

    def __init__(self, *args, **kwargs):
        super(TestDocumentsTransactionSubscriptions, self).__init__(*args, **kwargs)
        self.output = StringIO()

    def test_pay_documents_on_transaction_fail(self):
        """ Confirm that a transaction can fail. """

        transaction = TransactionFactory.create(
            state=Transaction.States.Pending
        )
        transaction.fail()
        transaction.save()

        proforma = transaction.proforma
        invoice = transaction.invoice

        self.assertNotEqual(proforma.state, proforma.STATES.PAID)
        self.assertNotEqual(invoice.state, invoice.STATES.PAID)

    def test_subscription_transaction_declined_suspend(self):
        """ Confirm that a failed transaction can trigger a subscription
        to suspend. """

        # Create a customer
        customer = CustomerFactory.create(sales_tax_percent=Decimal('0.00'))
        PaymentMethodFactory.create(
            payment_processor=triggered_processor, customer=customer,
            canceled=False,
            verified=True,
        )

        # Create a metered feature
        mf_price = Decimal('2.5')
        metered_feature = MeteredFeatureFactory(
            included_units_during_trial=Decimal('0.00'),
            price_per_unit=mf_price)
        currency = 'USD'

        # Crate a plan with metered features
        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=1, generate_after=25,
                                  enabled=True, amount=Decimal('20.00'),
                                  trial_period_days=5,
                                  metered_features=[metered_feature],
                                  currency=currency)
        start_date = dt.date(2019, 1, 1)

        # Create the prorated subscription
        subscription = SubscriptionFactory.create(
            plan=plan, start_date=start_date, customer=customer)
        subscription.activate()
        subscription.save()

        # Log some metered usage
        consumed_1 = Decimal('5.00')
        consumed_2 = Decimal('5.00')
        mf_log = MeteredFeatureUnitsLogFactory.create(
            subscription=subscription, metered_feature=metered_feature,
            start_date=dt.date(2019, 1, 10), end_date=subscription.trial_end,
            consumed_units=consumed_1)

        prev_billing_date = generate_docs_date('2019-01-03')  # During trial period
        curr_billing_date = subscription.trial_end + ONE_DAY

        # Generate the docs
        call_command('generate_docs', billing_date=prev_billing_date, stdout=self.output)

        proforma = Proforma.objects.first()
        # Expect 2 entries:
        # - prorated plan trial (+-) first month
        # - prorated plan trial (+-) next month
        assert proforma.proforma_entries.count() == 2

        assert Invoice.objects.all().count() == 0

        assert Proforma.objects.all()[0].total == Decimal('0.00')

        # Consume more units
        mf_log.consumed_units += consumed_2
        mf_log.save()

        call_command('generate_docs', billing_date=curr_billing_date, stdout=self.output)

        assert Proforma.objects.all().count() == 2
        assert Invoice.objects.all().count() == 0

        # Issue the proforma to generate transactions
        proforma = Proforma.objects.all()[1]
        proforma.issue()
        assert Transaction.objects.all().count() != 0

        # Fail the transaction
        transaction = proforma.transactions[0]
        transaction.fail()
        transaction.save()

        # Confirm that nothing has been paid, and the transaction fails.
        self.assertEqual(proforma.state, proforma.STATES.ISSUED)
        self.assertEqual(transaction.state, Transaction.States.Failed)

        # TODO: after grace period of 5 days, suspend the plan
        #  - hardcode grace period for now? 
        #  - generate documents again +5 days, fail another transaction,
        #  cancel?

        # this needs to be in a signal somewhere:
        # need a periodic management task that runs to see if declined
        # transactions are associated with active plans. if active, and
        # unpaid +5 days after billing period, then cancel the
        # subscription.
        subscription.cancel(when="now")
        self.assertEqual(subscription.state, Subscription.STATES.CANCELED)


    def test_subscription_transaction_declined_suspend_after_grace(self):
        """ Confirm that a transaction can fail. """
        pass

