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
        #
        customer = CustomerFactory.create(sales_tax_percent=Decimal('0.00'),
                                          payment_due_days=3)
        PaymentMethodFactory.create(
            payment_processor=triggered_processor, customer=customer,
            canceled=False,
            verified=True,
        )

        # Create a metered feature
        #
        mf_price = Decimal('2.5')
        metered_feature = MeteredFeatureFactory(
            included_units_during_trial=Decimal('0.00'),
            price_per_unit=mf_price)
        currency = 'USD'

        # Crate a plan with metered features. Generate the invoice after
        # the 5 day trial period, the plan will be billed every 30 days.
        # 
        generate_after = 5
        plan = PlanFactory.create(interval=Plan.INTERVALS.DAY,
                                  interval_count=30,
                                  generate_after=generate_after,
                                  enabled=True,
                                  amount=Decimal('20.00'),
                                  trial_period_days=5,
                                  metered_features=[metered_feature],
                                  currency=currency)
        start_date = dt.date(2019, 1, 1)

        # Subscribe the customer
        #
        subscription = SubscriptionFactory.create(
            plan=plan, start_date=start_date, customer=customer)
        subscription.activate()
        subscription.save()

        # Log some metered usage
        consumed_1 = Decimal('5.00')
        consumed_2 = Decimal('5.00')
        mf_log = MeteredFeatureUnitsLogFactory.create(
            subscription=subscription,
            metered_feature=metered_feature,
            start_date=dt.date(2019, 1, 10),
            end_date=subscription.trial_end,
            consumed_units=consumed_1)

        prev_billing_date = generate_docs_date('2019-01-03')  # During trial period
        curr_billing_date = subscription.trial_end + ONE_DAY
        billing_grace_exp = subscription.trial_end + (ONE_DAY * (5 + 30))

        # Generate the docs
        call_command('generate_docs', billing_date=prev_billing_date, stdout=self.output)

        proforma = Proforma.objects.first()

        assert proforma.proforma_entries.count() != 0
        assert Subscription.objects.all().count() == 1
        assert Invoice.objects.all().count() == 0
        assert Proforma.objects.all()[0].total == Decimal('0.00')

        # Consume more units
        mf_log.consumed_units += consumed_2
        mf_log.save()

        call_command('generate_docs', billing_date=billing_grace_exp, stdout=self.output)

        assert Proforma.objects.all().count() != 0
        assert Invoice.objects.all().count() == 0

        for pf in Proforma.objects.all():
            # # Issue the proforma to generate transactions
            # proforma = Proforma.objects.all()[1]
            pf.issue()
            pf.save()

            self.assertEqual(pf.state, Proforma.STATES.ISSUED)
            # Fail the transaction
            for tx in pf.transactions:
                # tx = proforma.transactions[0]
                tx.fail()
                tx.save()
                self.assertEqual(tx.state, Transaction.States.Failed)

        assert Transaction.objects.all().count() != 0

        call_command('check_subscriptions', billing_date=billing_grace_exp, stdout=self.output)
        subscr = Subscription.objects.first()
        # Scan for subscriptions with unpaid documents
        logging.debug("subscr %s" % subscr)
        self.assertEqual(subscr.state, Subscription.STATES.CANCELED)


    def test_subscription_transaction_declined_suspend_after_grace(self):
        """ Confirm that a transaction can fail. """
        pass

