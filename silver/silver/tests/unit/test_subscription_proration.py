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

import datetime
import datetime as dt

from decimal import Decimal

from django.core.management import call_command

from freezegun import freeze_time
from mock import patch, PropertyMock, MagicMock

from django.test import TestCase

from silver.management.commands.generate_docs import date as generate_docs_date

from silver.models import Plan, Subscription, BillingLog
from silver.tests.factories import (SubscriptionFactory, MeteredFeatureFactory,
                                    PlanFactory)

from django.utils import timezone

import pytest

from silver.tests.fixtures import (TriggeredProcessor,
                                   PAYMENT_PROCESSORS,
                                   triggered_processor)

from silver.models import (Proforma,
                           DocumentEntry,
                           Invoice,
                           PaymentMethod,
                           Provider,
                           BillingDocumentBase,
                           Transaction,
                           MeteredFeatureUnitsLog,
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
                                    ProductCodeFactory,
                                    ProviderFactory,
                                    SubscriptionFactory,
                                    TransactionFactory)

from django.utils.six import StringIO

NOW = timezone.now()


def print_entries(doc):
        print("--")
        print(" state: ", doc.state)
        print(" issue: ", doc.issue_date)
        print("   due: ", doc.due_date)
        for entr in doc.invoice_entries.all():
            print("entry: ", entr)
        print("--")
        print(doc.total)
        print("--")
        print("--")

class TestSubscriptionProrationCalculation(TestCase):
    """ Tests to make sure that
    Subscription._get_proration_status_and_percent functions in a sane
    way.
    """

    def __init__(self, *args, **kwargs):
        super(TestSubscriptionProrationCalculation, self).__init__(*args, **kwargs)
        self.output = StringIO()

    def create_basic_plan(self, start_date, end_date, interval=Plan.INTERVALS.YEAR):
        self.provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        self.customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        self.currency = 'USD'

        self.plan = PlanFactory.create(interval=interval,
                                       interval_count=1,
                                       generate_after=0,
                                       enabled=True,
                                       provider=self.provider,
                                       product_code=ProductCodeFactory(value="yearly-seat-plan"),
                                       amount=Decimal('10.00'),
                                       prebill_plan=False,
                                       currency=self.currency,
                                       trial_period_days=None,
                                       cycle_billing_duration=dt.timedelta(days=1),)
        self.plan.save()


        # Create the prorated subscription
        self.subscription = SubscriptionFactory.create(plan=self.plan,
                                                       start_date=start_date,
                                                       customer=self.customer)
        self.subscription.activate()
        self.subscription.save()

    @pytest.mark.django_db
    def test_half_month_proration(self):
        from django.db.models import Q

        # Set up the timescale.
        # Using november because that is happily divisible.
        start_date        = dt.date(2018, 11, 1)
        end_date        = dt.date(2018, 11, 15)
        interval        = Plan.INTERVALS.MONTH
        self.create_basic_plan(start_date, end_date, interval)

        is_pro, pro_amt = self.subscription._get_proration_status_and_percent(start_date,
                                                                              end_date)
        assert pro_amt == .50

    @pytest.mark.django_db
    def test_half_monthish_proration(self):
        from django.db.models import Q

        # Set up the timescale.
        # November is easily divisble by two. 
        # 
        # All these options should result in 50% proration, regardless
        # of where in the month they fall.
        start_date = dt.date(2018, 11, 15)
        end_date   = dt.date(2018, 11, 30)
        interval   = Plan.INTERVALS.MONTHISH

        self.create_basic_plan(start_date, end_date, interval)

        is_pro, pro_amt = self.subscription._get_proration_status_and_percent(start_date,
                                                                              end_date)
        assert pro_amt == .50

        start_date      = dt.date(2018, 11, 10)
        end_date        = dt.date(2018, 11, 25)
        is_pro, pro_amt = self.subscription._get_proration_status_and_percent(start_date,
                                                                              end_date)
        assert pro_amt == .50

        # Also we can span over months.
        start_date      = dt.date(2018, 11, 20)
        end_date        = dt.date(2018, 12, 5)
        is_pro, pro_amt = self.subscription._get_proration_status_and_percent(start_date,
                                                                              end_date)
        assert pro_amt == .50

    @pytest.mark.django_db
    def test_yearly_proration_percent_full_year(self):
        from django.db.models import Q

        # Set up the timescale.
        start_date = dt.date(2018, 1, 1)
        end_date   = dt.date(2018, 12, 31)
        interval   = Plan.INTERVALS.YEAR

        self.create_basic_plan(start_date, end_date, interval)

        is_pro, pro_amt = self.subscription._get_proration_status_and_percent(start_date,
                                                                              end_date)
        assert pro_amt == 1.00

    @pytest.mark.django_db
    def test_yearly_proration_percent_less(self):
        # Set up the timescale.
        start_date = dt.date(2018, 1, 1)
        end_date   = dt.date(2018, 12, 30)
        interval   = Plan.INTERVALS.YEAR

        self.create_basic_plan(start_date, end_date, interval)

        is_pro, pro_amt = self.subscription._get_proration_status_and_percent(start_date,
                                                                              end_date)
        assert .99 < pro_amt < 1.0

    @pytest.mark.django_db
    def test_half_year(self):
        from django.db.models import Q

        # Set up the timescale.
        start_date = dt.date(2018, 1, 1)
        end_date   = dt.date(2018, 7, 1)
        interval   = Plan.INTERVALS.YEAR

        self.create_basic_plan(start_date, end_date, interval)

        is_pro, pro_amt = self.subscription._get_proration_status_and_percent(start_date,
                                                                              end_date)

        assert .49 < pro_amt and pro_amt < .50

    @pytest.mark.django_db
    def test_subscription_yearly_proration_isnt_borked(self):
        from django.db.models import Q

        # Set up the timescale.
        start_date         = dt.date(2018, 1, 1)
        end_date           = dt.date(2018, 12, 31)
        first_billing_date = generate_docs_date('2018-01-01')
        end_billing_date   = generate_docs_date('2019-12-31')

        feature_usage_set       = dt.date(2018, 1, 1)
        fst_feature_usage_start = dt.date(2018, 1, 2)
        snd_feature_usage_end   = dt.date(2018, 1, 30)

        feature_increment       = dt.date(2018, 3, 1)
        snd_feature_usage_start = dt.date(2018, 3, 2)
        snd_feature_usage_end   = dt.date(2018, 3, 30)

        ## Lots of test setup {{{

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        plan = PlanFactory.create(interval=Plan.INTERVALS.YEAR,
                                       interval_count=1,
                                       generate_after=0,
                                       enabled=True,
                                       provider=provider,
                                       product_code=ProductCodeFactory(value="yearly-seat-plan"),
                                       amount=Decimal('10.00'),
                                       prebill_plan=False,
                                       currency=currency,
                                       trial_period_days=None,
                                       cycle_billing_duration=dt.timedelta(days=1),)
        plan.save()


        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                       start_date=start_date,
                                                       customer=customer)
        subscription.activate()
        subscription.save()

        ## }}}

        ## First test billing phase {{{
        call_command('generate_docs',
                     date=fst_feature_usage_start,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        call_command('generate_docs',
                     date=end_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        print("  END OF YEAR  ")
        year_invoice  = Invoice.objects.first()
        print_entries(year_invoice)

        # Final year total should be 10 for the whole base plan.
        assert year_invoice.total == Decimal(10.0)

    @pytest.mark.django_db
    def test_subscription_yearly_proration_isnt_borked_half(self):
        from django.db.models import Q

        # Set up the timescale.
        start_date         = dt.date(2018, 1, 1)
        end_date           = dt.date(2018, 7, 1)
        freezer            = freeze_time('2018-07-01')
        first_billing_date = generate_docs_date('2018-01-01')
        end_billing_date   = generate_docs_date('2018-07-02')

        feature_usage_set       = dt.date(2018, 1, 1)
        fst_feature_usage_start = dt.date(2018, 1, 2)
        snd_feature_usage_end   = dt.date(2018, 1, 30)

        feature_increment       = dt.date(2018, 3, 1)
        snd_feature_usage_start = dt.date(2018, 3, 2)
        snd_feature_usage_end   = dt.date(2018, 3, 30)

        ## Lots of test setup {{{

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        plan = PlanFactory.create(interval=Plan.INTERVALS.YEAR,
                                       interval_count=1,
                                       generate_after=0,
                                       enabled=True,
                                       provider=provider,
                                       product_code=ProductCodeFactory(value="yearly-seat-plan"),
                                       amount=Decimal('10.00'),
                                       prebill_plan=False,
                                       currency=currency,
                                       trial_period_days=None,
                                       cycle_billing_duration=dt.timedelta(days=1),)
        plan.save()


        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                       start_date=start_date,
                                                       customer=customer)
        subscription.activate()
        subscription.save()

        ## }}}

        ## First test billing phase {{{
        call_command('generate_docs',
                     date=fst_feature_usage_start,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        # zomg time travel so l33t 
        with freeze_time('2018-07-01') as T:
            subscription.cancel(when='now')
            subscription.save()

        call_command('generate_docs',
                     date=end_billing_date,
                     force_generate=True,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        print("  END OF YEAR  ")
        year_invoice  = Invoice.objects.first()
        print_entries(year_invoice)

        # Final year total should be 10 for the whole base plan.
        assert Decimal(4.98) <= year_invoice.total <= Decimal(5.00)


