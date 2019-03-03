from __future__ import absolute_import

import pytest

from decimal import Decimal
import datetime as dt

import json

from django.core.management import call_command
from silver.management.commands.generate_docs import date as generate_docs_date
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


import logging
logging.basicConfig(level=logging.WARNING)

def print_entries(doc):
        print("--")
        for entr in doc.invoice_entries.all():
            print("entry: ", entr)
        print("--")
        print(doc.total)
        print("--")
        print("--")

@override_settings(PAYMENT_PROCESSORS=PAYMENT_PROCESSORS)
class SubscriptionBillingDates(TestCase):

    # TODO: use the year-long test case to work out some other options
    # with different start dates. Need to make sure 1/31 can generate a
    # year with the correct periods despite feb lacking 31. 

    def __init__(self, *args, **kwargs):
        super(SubscriptionBillingDates, self).__init__(*args, **kwargs)
        self.output = StringIO()


    ### Some shared objects

    @property
    def provider(self):
        return ProviderFactory.create(flow=Provider.FLOWS.INVOICE,
                                      default_document_state=Provider.DEFAULT_DOC_STATE.ISSUED)

    @property
    def customer(self):
        return CustomerFactory.create(consolidated_billing=False,
                                      sales_tax_percent=Decimal('0.00'))

    @property
    def seat_feature(self):
        return MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('0.0'))

    @property
    def metered_feature(self):
        return MeteredFeatureFactory(name="Charcoal Base Units",
                                     unit="Barrels (per seat)",
                                     included_units=Decimal('0.00'),
                                     included_units_during_trial=Decimal('0.00'),
                                     product_code=ProductCodeFactory(value="charc-base"),
                                     price_per_unit= Decimal('5.00'),)
    def plan(self, **kwargs):
        return PlanFactory.create(
                                  generate_after=0,
                                  enabled=True,
                                  product_code=ProductCodeFactory(value="monthly-deliv-plan"),
                                  amount=Decimal('10.00'),
                                  prebill_plan=False,
                                  currency='USD',
                                  trial_period_days=None,
                                  cycle_billing_duration=dt.timedelta(days=1),
                                  **kwargs)

    @pytest.mark.django_db
    def test_that_issued_date_works_as_expected(self):
        """ Test that usage under and above a certain amount tracks with
        assumptions.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        first_invoice_date = dt.date(2018, 2, 1)

        prev_billing_date = generate_docs_date('2018-01-01')
        period_end_date   = generate_docs_date('2018-01-30')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = self.provider
        customer = self.customer
        currency = 'USD'

        seat_feature = self.seat_feature
        seat_feature.save()

        metered_feature = self.metered_feature
        metered_feature.save()

        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=1,
                                  generate_after=0,
                                  enabled=True,
                                  provider=provider,
                                  product_code=ProductCodeFactory(value="monthly-deliv-plan"),
                                  amount=Decimal('10.00'),
                                  prebill_plan=False,
                                  currency=currency,
                                  trial_period_days=None,
                                  cycle_billing_duration=dt.timedelta(days=1),
                                  metered_features=[metered_feature])
        plan.save()

        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        call_command('generate_docs',
                     date=feature_usage_start,
                     stdout=self.output)

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        assert invoice.issue_date == next_billing_date
        assert invoice.total == Decimal(110.0)

    def test_rrule_monthly_for_various_dates(self):
        # Testing some assumptions on rrule.
        # https://dateutil.readthedocs.io/en/stable/rrule.html
        from dateutil.rrule import rrule, MONTHLY
        from datetime import datetime

        r = list(rrule(freq=MONTHLY,
                       count=4,
                       dtstart=datetime(2017, 1, 1)
                      ))
        assert len(r) == 4
        d = r[1] - r[0]
        assert d.days == 31

        # This will skip months that don't contain a 31 ... 
        r = list(rrule(freq=MONTHLY,
                       count=4,
                       dtstart=datetime(2017, 1, 31)
                      ))
        assert len(r) == 4
        d = r[1] - r[0]
        assert d.days == 59

        # This will skip months that don't contain a 30 ... 
        r = list(rrule(freq=MONTHLY,
                       count=4,
                       dtstart=datetime(2017, 1, 30)
                      ))
        assert len(r) == 4
        d = r[1] - r[0]
        # A month is skipped because february does not contain 30 days
        assert d.days == 59

        # Billing by the last day of each month, with a start date that
        # excludes some months
        r = list(rrule(MONTHLY, count=4, bymonthday=-1,
                        dtstart=datetime(2017, 1, 31)))
        print(r)
        assert len(r) == 4
        d = r[1] - r[0]
        assert d.days == 28

        # Billing by the last day of each month, with a start date that
        # includes all possible months. (Same basic result)
        r = list(rrule(MONTHLY, count=4, bymonthday=-1,
                        dtstart=datetime(2017, 1, 27)))
        print(r)
        assert len(r) == 4
        d = r[1] - r[0]
        assert d.days == 28


        # Billing by the last day of each month, with a start date that
        # includes all possible months. (Same basic result)
        r = list(rrule(MONTHLY, count=4, bymonthday=6,
                        dtstart=datetime(2017, 1, 6)))
        assert len(r) == 4
        d = r[1] - r[0]
        assert d.days == 31

    @pytest.mark.django_db
    def test_that_monthly_billed_plan_issue_date_follows_start_date(self):
        """ Create a monthly plan starting on 1/7, with the MONTHISH
        setting. Confirm that billing happens on 2/8.  """

        # Set up the timescale.
        start_date              =  dt.date(2018, 1, 7)
        end_of_start_month      =  dt.date(2018, 1, 31)
        no_invoice_issued_here  =  dt.date(2018, 2, 3)
        first_invoice_date      =  dt.date(2018, 2, 7)

        curr_billing_date = generate_docs_date('2018-02-08')

        seat_feature_usage_set = dt.date(2018, 1, 8)
        feature_usage_start    = dt.date(2018, 1, 9)
        feature_usage_end      = dt.date(2018, 1, 10)

        provider = self.provider
        customer = self.customer

        seat_feature = self.seat_feature
        seat_feature.save()

        metered_feature = self.metered_feature
        metered_feature.save()

        plan = self.plan(interval=Plan.INTERVALS.MONTHISH,
                         interval_count=1,
                         metered_features=[metered_feature],
                         provider=provider,)
        plan.save()

        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        call_command('generate_docs',
                     date=feature_usage_start,
                     stdout=self.output)

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        # No invoices are generated here because the month hasn't passed
        call_command('generate_docs',
                     date=end_of_start_month,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        # Invoices SHOULD NOT be generated here because the billing
        # period shouldn't end.
        call_command('generate_docs',
                     date=no_invoice_issued_here,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        call_command('generate_docs',
                     date=curr_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        assert invoice.issue_date == curr_billing_date
        assert invoice.total > Decimal(10.0)

    @pytest.mark.django_db
    def test_that_daily_billed_plan_issue_date_follows_start_date(self):
        """ Create a monthly plan that starts on 1/7, test that
        follow-up billing documents are generated accurately with
        MONTHISH interval on two separate months.

        TODO: reproduce this test using roughly the same rrules instance
        that the plan creates, run through a year of dates and make sure
        they line up.

        TODO: seats do or don't carry over?
        """

        # Set up the timescale.
        start_date              =  dt.date(2018, 1, 7)
        end_of_start_month      =  dt.date(2018, 1, 31)
        no_invoice_issued_here  =  dt.date(2018, 2, 3)
        first_invoice_date      =  dt.date(2018, 2, 7)

        curr_billing_date = generate_docs_date('2018-02-08')

        seat_feature_usage_set = dt.date(2018, 1, 8)
        feature_usage_start    = dt.date(2018, 1, 9)
        feature_usage_end      = dt.date(2018, 1, 9)

        provider = self.provider
        customer = self.customer

        seat_feature = self.seat_feature
        seat_feature.save()

        metered_feature = self.metered_feature
        metered_feature.save()

        plan = self.plan(metered_features=[metered_feature],
                         interval_count=1,
                         interval=Plan.INTERVALS.MONTHISH,
                         provider=provider,)
        plan.save()

        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        call_command('generate_docs',
                     date=feature_usage_start,
                     stdout=self.output)

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        # No invoices are generated here because the month hasn't passed
        call_command('generate_docs',
                     date=end_of_start_month,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        # Invoices SHOULD NOT be generated here because the billing
        # period shouldn't end.
        call_command('generate_docs',
                     date=no_invoice_issued_here,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        call_command('generate_docs',
                     date=curr_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        assert invoice.issue_date == curr_billing_date
        assert invoice.total >= Decimal(110.0)
        invoice.pay(paid_date='2018-02-09')
        invoice.save()

        call_command('generate_docs',
                     date=generate_docs_date('2018-02-10'),
                     stdout=self.output)

        # Next period
        start_date              =  dt.date(2018, 2, 7) # + 30 days = 3/7/2018
        end_of_start_month      =  dt.date(2018, 2, 28)
        no_invoice_issued_here  =  dt.date(2018, 3, 3)
        first_invoice_date      =  dt.date(2018, 3, 7)

        curr_billing_date = generate_docs_date('2018-03-10')

        # seat_feature_usage_set = dt.date(2018, 2, 8)
        feature_usage_start    = dt.date(2018, 2, 12)
        feature_usage_end      = dt.date(2018, 2, 12)

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        call_command('generate_docs',
                     date=no_invoice_issued_here,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        call_command('generate_docs',
                     date=curr_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 2
        invoice = Invoice.objects.all().first()

        assert subscription.state == Subscription.STATES.ACTIVE
        assert invoice.issue_date == curr_billing_date
        assert invoice.total >= Decimal(110.0)



    @pytest.mark.django_db
    def test_that_daily_billed_plan_issue_date_carries_for_a_year(self):
        """ Test a scenario out for a year

        """
        from dateutil.rrule import rrule, MONTHLY
        from datetime import datetime, timedelta
        from calendar import monthrange

        # Billing by the last day of each month, with a start date that
        # includes all possible months. (Same basic result)

        # Set up the timescale.
        cycle_start_dates       =  dt.date(2018, 1, 7)

        # These are each month on the same day.
        # [datetime.datetime(), ...]
        intervals = list(rrule(MONTHLY,
                               count=12,
                               bymonthday=cycle_start_dates.day,
                               dtstart=cycle_start_dates))

        provider = self.provider
        customer = self.customer

        seat_feature = self.seat_feature
        seat_feature.save()

        metered_feature = self.metered_feature
        metered_feature.save()

        plan = self.plan(metered_features=[metered_feature],
                         interval_count=1,
                         interval=Plan.INTERVALS.MONTHISH,
                         provider=provider,)
        plan.save()

        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=cycle_start_dates,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        invoice_issued_assumed = 0
        for cycle_start in intervals:

            print(" -- cycle -- ")
            start_date              =  cycle_start.date()
            end_of_start_month      =  dt.date(start_date.year,
                                               start_date.month,
                                               monthrange(start_date.year, start_date.month)[1]
                                               )

            print("  month start:      ", start_date)
            print("  month end (cal.): ", end_of_start_month)

            no_invoice_issued_here  = start_date + timedelta(days=20)
            # no_invoice_issued_here  =  dt.date(start_date.year, start_date.month + 1, 3)
            first_invoice_date      =  start_date + timedelta(days=30)

            print("  no invoice check: ", no_invoice_issued_here)
            print("  first invoice:    ", first_invoice_date)

            deltawerk = start_date + timedelta(days=31)

            curr_billing_date = start_date + timedelta(days=31)

            print("  cur. billing date:", curr_billing_date)
            day_delta = start_date + timedelta(days=3)

            seat_feature_usage_set = dt.date(start_date.year, start_date.month, day_delta.day)
            feature_usage_start    = dt.date(start_date.year, start_date.month, day_delta.day + 1)
            feature_usage_end      = dt.date(start_date.year, start_date.month, day_delta.day + 1)

            print("  feature usage:    ", feature_usage_start)
            print("                -   ", seat_feature_usage_set)
            print("                -   ", feature_usage_end)

            call_command('generate_docs',
                         date=feature_usage_start,
                         stdout=self.output)

            # Track some usage
            mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                                 metered_feature=metered_feature,
                                                 start_date=feature_usage_start,
                                                 end_date=feature_usage_end,
                                                 consumed_units=Decimal('20.00'))
            mf.save()

            # No invoices are generated here because the month hasn't passed
            call_command('generate_docs',
                         date=end_of_start_month,
                         stdout=self.output)

            assert Invoice.objects.all().count() == invoice_issued_assumed


            # Invoices SHOULD NOT be generated here because the billing
            # period shouldn't end.
            call_command('generate_docs',
                         date=no_invoice_issued_here,
                         stdout=self.output)

            assert Invoice.objects.all().count() == invoice_issued_assumed

            call_command('generate_docs',
                         date=curr_billing_date,
                         stdout=self.output)

            invoice_issued_assumed += 1

            assert Invoice.objects.all().count() == invoice_issued_assumed
            invoice = Invoice.objects.all().first()

            assert invoice.issue_date == curr_billing_date
            assert invoice.total >= Decimal(110.0)
            invoice_pay_date        =  invoice.issue_date + timedelta(days=1)
            invoice.pay(paid_date=invoice_pay_date.strftime("%Y-%m-%d"))
            invoice.save()
            print("  invoice pay:      ", invoice_pay_date)
            print(" -- cycle end -- ")

        # hacky debug 
        # assert 1 == 0



    @pytest.mark.django_db
    def test_that_daily_billed_plan_issue_date_carries_for_a_year_end_of_month(self):
        """ Test a scenario out for a year, starting with a date that
        does not exist in all months.

        """
        from dateutil.rrule import rrule, MONTHLY
        from datetime import datetime, timedelta
        from calendar import monthrange

        # Billing by the last day of each month, with a start date that
        # includes all possible months. (Same basic result)

        # Set up the timescale.

        # works
        # cycle_start_dates       =  dt.date(2018, 1, 28)

        # breaks
        cycle_start_dates       =  dt.date(2018, 1, 29)

        # breaks
        # cycle_start_dates       =  dt.date(2018, 1, 30)

        # breaks
        # cycle_start_dates       =  dt.date(2018, 1, 31)

        # These are each month on the same day.
        # [datetime.datetime(), ...]
        intervals = list(rrule(MONTHLY,
                               count=12,
                               bymonthday=cycle_start_dates.day,
                               dtstart=cycle_start_dates))

        provider = self.provider
        customer = self.customer

        seat_feature = self.seat_feature
        seat_feature.save()

        metered_feature = self.metered_feature
        metered_feature.save()

        plan = self.plan(metered_features=[metered_feature],
                         interval_count=1,
                         interval=Plan.INTERVALS.MONTHISH,
                         provider=provider,)
        plan.save()

        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=cycle_start_dates,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        invoice_issued_assumed = 0
        for cycle_start in intervals:

            print(" -- cycle -- ")
            start_date              =  cycle_start.date()
            end_of_start_month      =  dt.date(start_date.year,
                                               start_date.month,
                                               monthrange(start_date.year, start_date.month)[1]
                                               )

            print("  month start:      ", start_date)
            print("  month end (cal.): ", end_of_start_month)

            no_invoice_issued_here  = start_date + timedelta(days=20)
            # no_invoice_issued_here  =  dt.date(start_date.year, start_date.month + 1, 3)
            first_invoice_date      =  start_date + timedelta(days=31)

            print("  no invoice check: ", no_invoice_issued_here)
            print("  first invoice:    ", first_invoice_date)

            deltawerk = start_date + timedelta(days=31)

            curr_billing_date = start_date + timedelta(days=32)

            print("  cur. billing date:", curr_billing_date)
            day_delta = start_date + timedelta(days=3)

            seat_feature_usage_set = start_date + timedelta(days=3)
            feature_usage_start    = start_date + timedelta(days=4)
            feature_usage_end      = start_date + timedelta(days=4)

            print("  feature usage:    ", feature_usage_start)
            print("                -   ", seat_feature_usage_set)
            print("                -   ", feature_usage_end)

            call_command('generate_docs',
                         date=feature_usage_start,
                         stdout=self.output)

            # Track some usage
            mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                                 metered_feature=metered_feature,
                                                 start_date=feature_usage_start,
                                                 end_date=feature_usage_end,
                                                 consumed_units=Decimal('20.00'))
            mf.save()

            # No invoices are generated here because the month hasn't passed
            call_command('generate_docs',
                         date=end_of_start_month,
                         stdout=self.output)

            assert Invoice.objects.all().count() == invoice_issued_assumed
            # debugging: invoice generated here, which is 2018-01-31,
            # despite start date being 2018-01-29


            # Invoices SHOULD NOT be generated here because the billing
            # period shouldn't end.
            call_command('generate_docs',
                         date=no_invoice_issued_here,
                         stdout=self.output)

            assert Invoice.objects.all().count() == invoice_issued_assumed

            call_command('generate_docs',
                         date=curr_billing_date,
                         stdout=self.output)

            invoice_issued_assumed += 1

            assert Invoice.objects.all().count() == invoice_issued_assumed
            invoice = Invoice.objects.all().first()

            assert invoice.issue_date == curr_billing_date
            assert invoice.total >= Decimal(100.0)
            invoice_pay_date        =  invoice.issue_date + timedelta(days=1)
            invoice.pay(paid_date=invoice_pay_date.strftime("%Y-%m-%d"))
            invoice.save()
            print("  invoice pay:      ", invoice_pay_date)
            print(" -- cycle end -- ")

        # hacky debug 
        # assert 1 == 0
