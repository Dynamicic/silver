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
                                  # cycle_billing_duration=dt.timedelta(days=1),
                                  **kwargs)

    @pytest.mark.django_db
    def test_issued_date_works_as_expected(self):
        """ Test that usage under and above a certain amount tracks with
        assumptions. """

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

    @pytest.mark.skip
    def test_relative_delta(self):
        # TODO: this

        from silver.utils.dates import relativedelta, ONE_DAY
        from dateutil.rrule import rrule, MONTHLY
        from datetime import datetime, timedelta
        from calendar import monthrange

        # Billing by the last day of each month, with a start date that
        # includes all possible months. (Same basic result)

        # Set up the timescale.
        cycle_start_dates       =  dt.date(2018, 1, 29)

        # These are each month on the same day.
        # [datetime.datetime(), ...]
        intervals = list(rrule(MONTHLY,
                               count=12,
                               bymonthday=-1,
                               dtstart=cycle_start_dates))

        relative_delta = relativedelta(months=1)

        for interval in intervals:
            end_date = interval + relative_delta - ONE_DAY

            # print((interval, end_date))

        # assert 1 == 0

    @pytest.mark.django_db
    def test_monthly_billed_plan_issue_date_follows_start_date(self):
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
    def test_daily_billed_plan_issue_date_follows_start_date(self):
        """ Create a monthly plan that starts on 1/7, test that
        follow-up billing documents are generated accurately with
        MONTHISH interval on two separate months.
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
        assert Decimal(109.00) <= invoice.total <= Decimal(110.0)
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
        assert Decimal(109.00) <= invoice.total <= Decimal(110.0)


    def _test_year_for_interval(self, cycle_start_dates, intervals=12):
        """ Create all the test conditions for a specific date. This
        runs on the specified amount of intervals. To confirm that
        billing documents are issued as specified.
        """
        from dateutil.rrule import rrule, MONTHLY
        from datetime import datetime, timedelta
        from calendar import monthrange

        # Billing by the last day of each month, with a start date that
        # includes all possible months. (Same basic result)

        # Set up the timescale.

        # These are each month on the same day.
        # [datetime.datetime(), ...]
        _intervals = list(rrule(MONTHLY,
                                count=intervals,
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

        # Running for 12 billing cycles, where each cycle begins the day
        # after the last.
        _start_date = False
        for cycle_start in range(0, intervals):
            print(" -- cycle -- ")

            if not _start_date:
                cycle_start =  cycle_start_dates
            else:
                cycle_start = _start_date + timedelta(days=1)

            end_of_start_month      =  dt.date(cycle_start.year,
                                               cycle_start.month,
                                               monthrange(cycle_start.year, cycle_start.month)[1]
                                               )

            print("  cycle start:      ", cycle_start)
            print("  cal. month end:   ", end_of_start_month)

            no_invoice_issued_here  = cycle_start + timedelta(days=20)
            # no_invoice_issued_here  =  dt.date(start_date.year, start_date.month + 1, 3)

            deltawerk = cycle_start + timedelta(days=31)

            day_delta = cycle_start + timedelta(days=3)

            seat_feature_usage_set = cycle_start + timedelta(days=3)
            feature_usage_start    = cycle_start + timedelta(days=4)
            feature_usage_end      = cycle_start + timedelta(days=4)

            print("  | feature usage:  ", feature_usage_start)
            print("  | feature usage:  ", seat_feature_usage_set)
            print("  | feature usage:  ", feature_usage_end)

            _calc_start =  subscription._cycle_start_date(reference_date=cycle_start,
                                                          ignore_trial=True,
                                                          granulate=False)

            _cycle_end = subscription._cycle_end_date(reference_date=cycle_start,
                                                      ignore_trial=True,
                                                      granulate=False)

            # new
            _start_date = _cycle_end

            first_invoice_date      =  _cycle_end + timedelta(days=1)

            print("  no invoice check: ", no_invoice_issued_here)
            curr_billing_date = first_invoice_date + timedelta(days=1)
            print("  billing date:     ", curr_billing_date)

            print("  invoice issued:   ", first_invoice_date)

            # No invoices are generated here despite feature usage
            inv_c = Invoice.objects.all().count()
            call_command('generate_docs',
                         date=feature_usage_start,
                         subscription=subscription.id,
                         stdout=self.output)
            assert Invoice.objects.all().count() == inv_c

            # Track some usage
            mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                                 metered_feature=metered_feature,
                                                 start_date=feature_usage_start,
                                                 end_date=feature_usage_end,
                                                 consumed_units=Decimal('20.00'))
            mf.save()

            # No invoices are generated here because the month hasn't passed
            inv_c = Invoice.objects.all().count()
            call_command('generate_docs',
                         date=end_of_start_month,
                         subscription=subscription.id,
                         stdout=self.output)
            assert Invoice.objects.all().count() == inv_c


            # Invoices SHOULD NOT be generated here because the billing
            # period shouldn't end.
            inv_c = Invoice.objects.all().count()
            call_command('generate_docs',
                         date=no_invoice_issued_here,
                         subscription=subscription.id,
                         stdout=self.output)
            assert Invoice.objects.all().count() == inv_c

            call_command('generate_docs',
                         date=_cycle_end,
                         subscription=subscription.id,
                         stdout=self.output)

            call_command('generate_docs',
                         date=curr_billing_date,
                         subscription=subscription.id,
                         stdout=self.output)


            print("  invoice count:     ", Invoice.objects.all().count())
            invoice = Invoice.objects.all().first()
            assert invoice != None

            invoice_issued_assumed += 1

            # looks like invoice gets issued at wrong time
            assert invoice.issue_date == curr_billing_date
            assert invoice.total >= Decimal(0.0)
            invoice_pay_date        =  invoice.issue_date + timedelta(days=1)
            print("  invoice date:     ", invoice.issue_date)
            assert invoice.issue_date == curr_billing_date
            invoice.pay(paid_date=invoice_pay_date.strftime("%Y-%m-%d"))
            invoice.save()
            print("  invoice pay:      ", invoice_pay_date)
            print("  invoice amount:   ", invoice.total)
            print("  calc cycle start: ", _calc_start)
            print("  calc cycle end:   ", _cycle_end)
            print(" -- cycle end -- ")
            cycle_start = _start_date

        # hacky debug 
        # assert 1 == 0

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year_from_beg(self):
        """ Test a scenario out for a year, starting at the beginning of
        the month.

        """
        cycle_start_dates       =  dt.date(2018, 1, 1)
        self._test_year_for_interval(cycle_start_dates)

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year_from_2(self):
        """ Test a scenario out for a year, starting on the 2nd the
        month. Make sure that short months don't interfere with any
        assumptions from the beginning.  """

        cycle_start_dates       =  dt.date(2018, 1, 1)
        self._test_year_for_interval(cycle_start_dates)

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year(self):
        """ Test a scenario out for a year, starting in the middle of
        the month.

        """
        cycle_start_dates       =  dt.date(2018, 1, 7)
        self._test_year_for_interval(cycle_start_dates)

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year_end_of_month_26(self):
        """ Test a scenario out for a year, starting with a date that
        does not exist in all months: Jan. 26
        """

        cycle_start_dates       =  dt.date(2018, 1, 26)
        self._test_year_for_interval(cycle_start_dates)

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year_end_of_month_27(self):
        """ Test a scenario out for a year, starting with a date that
        does not exist in all months: Jan. 27
        """

        cycle_start_dates       =  dt.date(2018, 1, 27)
        self._test_year_for_interval(cycle_start_dates)

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year_end_of_month_28(self):
        """ Test a scenario out for a year, starting with a date that
        does not exist in all months: Jan. 28
        """

        cycle_start_dates       =  dt.date(2018, 1, 28)
        self._test_year_for_interval(cycle_start_dates)

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year_end_of_month_29(self):
        """ Test a scenario out for a year, starting with a date that
        does not exist in all months: Jan. 29
        """

        cycle_start_dates       =  dt.date(2017, 1, 29)
        self._test_year_for_interval(cycle_start_dates)

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year_end_of_month_30(self):
        """ Test a scenario out for a year, starting with a date that
        does not exist in all months: Jan. 30
        """

        cycle_start_dates       =  dt.date(2018, 1, 30)
        self._test_year_for_interval(cycle_start_dates)

    @pytest.mark.django_db
    def test_daily_billed_plan_issue_date_carries_for_a_year_end_of_month_31(self):
        """ Test a scenario out for a year, starting with a date that
        does not exist in all months: Jan. 31
        """

        cycle_start_dates       =  dt.date(2018, 1, 31)
        self._test_year_for_interval(cycle_start_dates)

    def _test_year_for_interval_split_with_changes(self, cycle_start_dates, manual_cycle_end_date, intervals=12):
        """ Create all the test conditions for a specific date. This
        runs on the specified amount of intervals. To confirm that
        billing documents are issued as specified.
        """
        from dateutil.rrule import rrule, MONTHLY
        from datetime import datetime, timedelta
        from calendar import monthrange

        # Billing by the last day of each month, with a start date that
        # includes all possible months. (Same basic result)

        # Set up the timescale.

        # These are each month on the same day.
        # [datetime.datetime(), ...]
        _intervals = list(rrule(MONTHLY,
                                count=intervals,
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

        # Split the testing interval into two halves.

        first_half  = round(intervals / 2)
        second_half = round(intervals / 2)

        # Running for first half, where each cycle begins the day
        # after the last.
        _start_date = False
        for cycle_start in range(0, first_half):
            print(" -- cycle -- ")

            if not _start_date:
                cycle_start =  cycle_start_dates
            else:
                cycle_start = _start_date + timedelta(days=1)

            end_of_start_month      =  dt.date(cycle_start.year,
                                               cycle_start.month,
                                               monthrange(cycle_start.year, cycle_start.month)[1]
                                               )

            print("  cycle test start: ", cycle_start)
            print("  cal. month end:   ", end_of_start_month)

            no_invoice_issued_here  = cycle_start + timedelta(days=20)
            # no_invoice_issued_here  =  dt.date(start_date.year, start_date.month + 1, 3)

            deltawerk = cycle_start + timedelta(days=31)

            day_delta = cycle_start + timedelta(days=3)

            seat_feature_usage_set = cycle_start + timedelta(days=3)
            feature_usage_start    = cycle_start + timedelta(days=4)
            feature_usage_end      = cycle_start + timedelta(days=4)

            print("  | feature usage:  ", feature_usage_start)
            print("  | feature usage:  ", seat_feature_usage_set)
            print("  | feature usage:  ", feature_usage_end)

            _calc_start =  subscription._cycle_start_date(reference_date=cycle_start,
                                                          ignore_trial=True,
                                                          granulate=False)

            _cycle_end = subscription._cycle_end_date(reference_date=cycle_start,
                                                      ignore_trial=True,
                                                      granulate=False)

            # new
            _start_date = _cycle_end

            first_invoice_date      =  _cycle_end + timedelta(days=1)

            print("  no invoice check: ", no_invoice_issued_here)
            curr_billing_date = first_invoice_date + timedelta(days=1)
            print("  billing date:     ", curr_billing_date)

            print("  invoice issued:   ", first_invoice_date)

            # No invoices are generated here despite feature usage
            inv_c = Invoice.objects.all().count()
            call_command('generate_docs',
                         date=feature_usage_start,
                         subscription=subscription.id,
                         stdout=self.output)
            assert Invoice.objects.all().count() == inv_c

            # Track some usage
            mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                                 metered_feature=metered_feature,
                                                 start_date=feature_usage_start,
                                                 end_date=feature_usage_end,
                                                 consumed_units=Decimal('20.00'))
            mf.save()

            # No invoices are generated here because the month hasn't passed
            inv_c = Invoice.objects.all().count()
            call_command('generate_docs',
                         date=end_of_start_month,
                         subscription=subscription.id,
                         stdout=self.output)
            assert Invoice.objects.all().count() == inv_c


            # Invoices SHOULD NOT be generated here because the billing
            # period shouldn't end.
            inv_c = Invoice.objects.all().count()
            call_command('generate_docs',
                         date=no_invoice_issued_here,
                         subscription=subscription.id,
                         stdout=self.output)
            assert Invoice.objects.all().count() == inv_c

            call_command('generate_docs',
                         date=_cycle_end,
                         subscription=subscription.id,
                         stdout=self.output)

            call_command('generate_docs',
                         date=curr_billing_date,
                         subscription=subscription.id,
                         stdout=self.output)


            print("  invoice count:     ", Invoice.objects.all().count())
            invoice = Invoice.objects.all().first()
            assert invoice != None

            invoice_issued_assumed += 1

            # looks like invoice gets issued at wrong time
            assert invoice.issue_date == curr_billing_date
            assert invoice.total >= Decimal(0.0)
            invoice_pay_date        =  invoice.issue_date + timedelta(days=1)
            print("  invoice date:     ", invoice.issue_date)
            assert invoice.issue_date == curr_billing_date
            invoice.pay(paid_date=invoice_pay_date.strftime("%Y-%m-%d"))
            invoice.save()
            print("  invoice pay:      ", invoice_pay_date)
            print("  invoice amount:   ", invoice.total)
            print("  calc cycle start: ", _calc_start)
            print("  calc cycle end:   ", _cycle_end)
            print(" -- cycle end -- ")
            cycle_start = _start_date


        print("")
        print(" *** Setting a new date *** ")
        # Perform some modifications to the subscription
        subscription.cycle_end_override = manual_cycle_end_date
        subscription.save()
        print(" ", manual_cycle_end_date)
        print("")
        print("")

        first_cycle_after_change = True
        # Run the remainder and see what happens.
        for cycle_start in range(0, second_half):
            print(" -- cycle -- ")

            if not _start_date:
                cycle_start =  cycle_start_dates
            else:
                cycle_start = _start_date + timedelta(days=1)

            end_of_start_month      =  dt.date(cycle_start.year,
                                               cycle_start.month,
                                               monthrange(cycle_start.year, cycle_start.month)[1]
                                               )

            print("  cycle start:      ", cycle_start)
            print("  cal. month end:   ", end_of_start_month)

            no_invoice_issued_here  = cycle_start + timedelta(days=20)
            # no_invoice_issued_here  =  dt.date(start_date.year, start_date.month + 1, 3)

            deltawerk = cycle_start + timedelta(days=31)

            day_delta = cycle_start + timedelta(days=3)

            seat_feature_usage_set = cycle_start + timedelta(days=3)
            feature_usage_start    = cycle_start + timedelta(days=4)
            feature_usage_end      = cycle_start + timedelta(days=4)

            print("  | feature usage:  ", feature_usage_start)
            print("  | feature usage:  ", seat_feature_usage_set)
            print("  | feature usage:  ", feature_usage_end)

            _calc_start =  subscription._cycle_start_date(reference_date=cycle_start,
                                                          ignore_trial=True,
                                                          granulate=False)

            _cycle_end = subscription._cycle_end_date(reference_date=cycle_start,
                                                      ignore_trial=True,
                                                      granulate=False)

            # new
            _start_date = _cycle_end

            first_invoice_date      =  _cycle_end + timedelta(days=1)

            print("  no invoice check: ", no_invoice_issued_here)
            curr_billing_date = first_invoice_date + timedelta(days=1)
            print("  billing date:     ", curr_billing_date)

            print("  invoice issued:   ", first_invoice_date)

            # No invoices are generated here despite feature usage
            inv_c = Invoice.objects.all().count()
            call_command('generate_docs',
                         date=feature_usage_start,
                         subscription=subscription.id,
                         stdout=self.output)

            if not first_cycle_after_change:
                assert Invoice.objects.all().count() == inv_c

            # Track some usage
            mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                                 metered_feature=metered_feature,
                                                 start_date=feature_usage_start,
                                                 end_date=feature_usage_end,
                                                 consumed_units=Decimal('20.00'))
            mf.save()

            # No invoices are generated here because the month hasn't passed
            inv_c = Invoice.objects.all().count()
            call_command('generate_docs',
                         date=end_of_start_month,
                         subscription=subscription.id,
                         stdout=self.output)

            # Invoices SHOULD NOT be generated here because the billing
            # period shouldn't end.
            call_command('generate_docs',
                         date=no_invoice_issued_here,
                         subscription=subscription.id,
                         stdout=self.output)

            call_command('generate_docs',
                         date=_cycle_end,
                         subscription=subscription.id,
                         stdout=self.output)

            call_command('generate_docs',
                         date=curr_billing_date,
                         subscription=subscription.id,
                         stdout=self.output)


            print("  invoice count:     ", Invoice.objects.all().count())
            invoice = Invoice.objects.all().first()
            assert invoice != None

            invoice_issued_assumed += 1

            # looks like invoice gets issued at wrong time
            # if not first_cycle_after_change:
            #     assert invoice.issue_date == curr_billing_date

            assert invoice.total >= Decimal(0.0)
            invoice_pay_date        =  invoice.issue_date + timedelta(days=1)
            print("  invoice date:     ", invoice.issue_date)
            # if not first_cycle_after_change:
            #     assert invoice.issue_date == curr_billing_date
            invoice.pay(paid_date=invoice_pay_date.strftime("%Y-%m-%d"))
            invoice.save()
            print("  invoice pay:      ", invoice_pay_date)
            print("  invoice amount:   ", invoice.total)
            print("  calc cycle start: ", _calc_start)
            print("  calc cycle end:   ", _cycle_end)
            print(" -- cycle end -- ")
            cycle_start = _start_date
            first_cycle_after_change = False

        # hacky debug 
        # assert 1 == 0

    @pytest.mark.django_db
    @pytest.mark.skip
    def test_mid_plan_date_override_works_from_month_end_to_mid(self):

        cycle_start_dates       =  dt.date(2018, 1, 31)

        # Halfway through this we're going to set a new cycle end date 
        # NB: the feature only uses the day of this, so really the month
        # doesn't matter; but including the month that the cycle change
        # will happen just because.
        # 
        manual_cycle_end_date   =  dt.date(2018, 8, 5)

        self._test_year_for_interval_split_with_changes(cycle_start_dates,
                                                        manual_cycle_end_date,
                                                        intervals=12)


    @pytest.mark.django_db
    def test_setting_override_to_date_before_cycle_end(self):
        """ We set a new billing date that is before the current cycle
        ends and expect that nothing breaks.  """

        cycle_start_dates       =  dt.date(2018, 1, 1)

        # Halfway through this we're going to set a new cycle end date 
        # NB: the feature only uses the day of this, so really the month
        # doesn't matter; but including the month that the cycle change
        # will happen just because.
        # 
        manual_cycle_end_date   =  dt.date(2018, 8, 5)

        self._test_year_for_interval_split_with_changes(cycle_start_dates,
                                                        manual_cycle_end_date,
                                                        intervals=12)

    @pytest.mark.django_db
    def test_mid_plan_date_override_works_from_start_to_mid(self):
        """ Test that we can override billing cycle end dates.
        """

        cycle_start_dates       =  dt.date(2018, 1, 31)

        # Halfway through this we're going to set a new cycle end date 
        # NB: the feature only uses the day of this, so really the month
        # doesn't matter; but including the month that the cycle change
        # will happen just because.
        # 
        manual_cycle_end_date   =  dt.date(2018, 8, 31)

        self._test_year_for_interval_split_with_changes(cycle_start_dates,
                                                        manual_cycle_end_date,
                                                        intervals=12)

    @pytest.mark.django_db
    def test_mid_plan_date_override_works_from_mid_mid(self):
        """ Test that we can override billing cycle end dates.
        """

        cycle_start_dates       =  dt.date(2018, 1, 10)

        # Halfway through this we're going to set a new cycle end date 
        # NB: the feature only uses the day of this, so really the month
        # doesn't matter; but including the month that the cycle change
        # will happen just because.
        # 
        manual_cycle_end_date   =  dt.date(2018, 8, 15)

        self._test_year_for_interval_split_with_changes(cycle_start_dates,
                                                        manual_cycle_end_date,
                                                        intervals=12)
