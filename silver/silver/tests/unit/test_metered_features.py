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
        print(" state: ", doc.state)
        print(" issue: ", doc.issue_date)
        print("   due: ", doc.due_date)
        for entr in doc.invoice_entries.all():
            print("entry: ", entr)
        print("--")
        print(doc.total)
        print("--")
        print("--")

@override_settings(PAYMENT_PROCESSORS=PAYMENT_PROCESSORS)
class TestMeteredFeatures(TestCase):

    def __init__(self, *args, **kwargs):
        super(TestMeteredFeatures, self).__init__(*args, **kwargs)
        self.output = StringIO()

    @pytest.mark.django_db
    def test_metered_feature_calculations(self):
        """ Confirm that a transaction can have a negative value. """

        from django.db.models import F, Subquery, DecimalField

        # Timeframes
        start_date = dt.date(2019, 1, 1)

        # We log some seat changes
        seat_increment_usage_start_date = dt.date(2019, 1, 2)
        seat_increment_usage_end_date   = dt.date(2019, 1, 3)

        # Feature usage begins
        feature_usage_start_date = dt.date(2019, 1, 5)
        feature_usage_end_date   = dt.date(2019, 1, 6)

        first_billing_check = dt.date(2019, 1, 15)
        first_invoice_out   = dt.date(2019, 2, 10)

        # Set it up
        customer = CustomerFactory.create(sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        # Set up our base metered feature. This contains an amount of
        # included units, hopefully the customer won't be billed for
        # usage under that limit.
        # 
        seat_price = Decimal('0.0')
        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            price_per_unit=seat_price)

        mf_price = Decimal('2.0')
        metered_feature = MeteredFeatureFactory(
            name="Charcoal Base Units",
            unit="Barrels (per seat)",
            included_units=Decimal('5.00'),
            price_per_unit=mf_price,
            linked_feature=seat_feature,
            included_units_calculation="multiply")

        # Create the plan
        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=1,
                                  generate_after=1,
                                  enabled=True,
                                  amount=Decimal('10.00'),
                                  trial_period_days=0,
                                  metered_features=[metered_feature,
                                                    seat_feature],
                                  currency=currency)

        # Subscribe the customer
        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        # Log some usage
        # Add some seats
        one_seat = Decimal('1.0')
        seat_log = MeteredFeatureUnitsLogFactory.create(
                                                subscription=subscription,
                                                metered_feature=seat_feature,
                                                start_date=seat_increment_usage_start_date,
                                                end_date=seat_increment_usage_start_date,
                                                consumed_units=one_seat)

        # We up the increment here to prove that changing the value
        # doesn't mess up a calculation.
        two_seats = Decimal('1.0')
        seat_log = MeteredFeatureUnitsLogFactory.create(
                                                subscription=subscription,
                                                metered_feature=seat_feature,
                                                start_date=seat_increment_usage_end_date,
                                                end_date=seat_increment_usage_end_date,
                                                consumed_units=two_seats)

        consumed = Decimal('15.00')
        mf_log = MeteredFeatureUnitsLogFactory.create(
                                                subscription=subscription,
                                                metered_feature=metered_feature,
                                                start_date=feature_usage_start_date,
                                                end_date=feature_usage_end_date,
                                                consumed_units=consumed)


        call_command('generate_docs',
                     billing_date=first_billing_check,
                     stdout=self.output)


        # Now that we have docs generated, we can check the outcome.

        # Billing period hasn't ended yet, so there's only a proforma.
        # 
        proforma = Proforma.objects.first()
        assert proforma.proforma_entries.count() == 1
        assert Invoice.objects.all().count() == 0
        assert Proforma.objects.all()[0].total == Decimal('10.00')


        # Test after another date
        call_command('generate_docs',
                     billing_date=first_invoice_out,
                     stdout=self.output)

        # 
        proforma = Proforma.objects.first()
        assert proforma.proforma_entries.count() == 1
        assert Invoice.objects.all().count() == 0
        assert Proforma.objects.all()[0].total == Decimal('10.00')
        metered_entry = proforma.proforma_entries.first()

        # Get our logged features
        # 
        features_log = MeteredFeatureUnitsLog.objects.filter(
            subscription=subscription)
        assert features_log.count() == 3

        _metered = features_log.filter(metered_feature=metered_feature)
        assert _metered.count() == 1

    @pytest.mark.django_db
    def test_interval_validation_fix(self):
        """ Discovered that it's possible to trigger a bug in
        rrule.rrule where the generator runs indefinitely and never
        exits, by setting the interval count to 0. This tests a couple
        kinds of validation to ensure that doesn't happen. """

        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 13)
        feature_usage_start    = dt.date(2018, 1, 15)
        feature_usage_end      = dt.date(2018, 1, 16)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_price = Decimal('0.0')
        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            price_per_unit=seat_price)

        mf_price = Decimal('5.00')
        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                # linked_feature=seat_feature,
                                                # included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                price_per_unit=mf_price,)

        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=0,
                                  generate_after=1,
                                  enabled=True,
                                  amount=Decimal('0.00'),
                                  currency=currency,
                                  trial_period_days=0,
                                  metered_features=[seat_feature, metered_feature])

        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        try:
            call_command('generate_docs',
                         date=curr_billing_date,
                         stdout=self.output)
        except Exception as e:
            if 'interval_count' in str(e):
                pass
            else:
                raise e

        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=0,
                                  generate_after=1,
                                  enabled=True,
                                  amount=Decimal('0.00'),
                                  currency=currency,
                                  trial_period_days=0,
                                  metered_features=[seat_feature, metered_feature])
        plan.save()

    @pytest.mark.django_db
    @pytest.mark.skip
    def test_prorated_subscription_with_consumed_mfs_overflow(self):
        """ Test that stuff doesn't break because of the new features.

            TODO: something's weird here, so fix this.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 13)
        feature_usage_start    = dt.date(2018, 1, 15)
        feature_usage_end      = dt.date(2018, 1, 16)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_price = Decimal('0.0')
        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            price_per_unit=seat_price)

        mf_price = Decimal('5.00')
        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                # linked_feature=seat_feature,
                                                # included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                price_per_unit=mf_price,)

        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=1,
                                  generate_after=1,
                                  enabled=True,
                                  amount=Decimal('0.00'),
                                  currency=currency,
                                  trial_period_days=0,
                                  metered_features=[seat_feature, metered_feature])

        # Create the prorated subscription
        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        call_command('generate_docs',
                     date=curr_billing_date,
                     stdout=self.output)

        assert Proforma.objects.all().count() == 1
        assert Invoice.objects.all().count() == 0

        proforma = Proforma.objects.all()[0]
        assert proforma.total == Decimal(14 / 28.0) * plan.amount

        # Add a seat
        mfl = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('1.00'))
        mfl.save()

        # Track some usage
        mfl = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('60.00'))
        mfl.save()

        call_command('generate_docs',
                     date=curr_billing_date,
                     stdout=self.output)

        assert Proforma.objects.all().count() == 1
        assert Invoice.objects.all().count() == 0
        assert proforma.total == Decimal('0.00')

    @pytest.mark.django_db
    def test_metered_feature_usage_under_included_units(self):
        """ Test that usage under and above a certain amount tracks with
        assumptions.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('0.0'))
        seat_feature.save()

        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                included_units=Decimal('0.00'),
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('5.00'),)
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

        assert Invoice.objects.all().count() == 0

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        assert invoice.total == Decimal(110.0)

    @pytest.mark.django_db
    def test_linked_features_no_linked_usage(self):
        """ Test that usage under and above a certain amount tracks with
        assumptions.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('0.0'))
        seat_feature.save()

        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('5.00'),)
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
                                  metered_features=[seat_feature, metered_feature])
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

        assert Invoice.objects.all().count() == 0

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        # There should be no metered feature charges for this plan, with
        # an unlogged metered feature value
        assert invoice.total == Decimal(10.0)

    @pytest.mark.django_db
    def test_linked_features_with_linked_usage(self):
        """ Test that usage under and above a certain amount tracks with
        assumptions.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('0.0'))
        seat_feature.save()

        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('5.00'),)
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
                                  metered_features=[seat_feature, metered_feature])
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

        assert Invoice.objects.all().count() == 0

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('1.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        # Including 20 units per seat, and one seat, which means 20
        # units are included.
        print_entries(invoice)
        assert invoice.total == Decimal(10.0)

    @pytest.mark.django_db
    def test_linked_features_with_linked_usage(self):
        """ Test that usage under and above a certain amount tracks with
        assumptions.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('0.0'))
        seat_feature.save()

        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('5.00'),)
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
                                  metered_features=[seat_feature, metered_feature])
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

        assert Invoice.objects.all().count() == 0

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('2.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('40.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        # Including 20 units per seat, and two seats, which means 40
        # units are included.
        print_entries(invoice)
        assert invoice.total == Decimal(10.0)

    @pytest.mark.django_db
    def test_linked_features_with_linked_usage_and_linked_cost(self):
        """ Test that usage under and above a certain amount tracks with
        assumptions, and incrementing the seats feature should increase
        cost of the overall plan.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('10.0'))
        seat_feature.save()

        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('5.00'),)
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
                                  metered_features=[seat_feature, metered_feature])
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

        assert Invoice.objects.all().count() == 0

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('2.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('40.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        # Including 20 units per seat, and two seats, which means 40
        # units are included.
        print_entries(invoice)
        assert invoice.total == Decimal(30.0)



    @pytest.mark.django_db
    def test_prebilled_metered_feature_units(self):
        """ Mark a feature as pre-billed and confirm that the total
        calculates as intended. """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('10.0'))
        seat_feature.save()

        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('40.00'),
                                                prebill_included_units=True,
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('1.00'),)
        metered_feature.save()

        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=1,
                                  generate_after=0,
                                  enabled=True,
                                  provider=provider,
                                  product_code=ProductCodeFactory(value="monthly-deliv-plan"),
                                  amount=Decimal('0.00'),
                                  prebill_plan=False,
                                  currency=currency,
                                  trial_period_days=None,
                                  cycle_billing_duration=dt.timedelta(days=1),
                                  metered_features=[seat_feature, metered_feature])
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

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('1.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        invoice = Invoice.objects.all().first()

        # print_entries(invoice)

        # Including 40 units per seat, at $1 per unit, and $10 per seat.
        # 20 units are consumed by the end of the period (=$40), and one seat
        # is added (=$10), so our total is $50.00
        #
        assert invoice.total == Decimal(50.0)

    def test_prebilled_metered_feature_units_and_add_overage(self):
        """ Mark a feature as pre-billed, and charge some overage.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('10.0'))
        seat_feature.save()

        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('40.00'),
                                                prebill_included_units=True,
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit=Decimal('1.00'),)
        metered_feature.save()

        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=1,
                                  generate_after=0,
                                  enabled=True,
                                  provider=provider,
                                  product_code=ProductCodeFactory(value="monthly-deliv-plan"),
                                  amount=Decimal('0.00'),
                                  prebill_plan=False,
                                  currency=currency,
                                  trial_period_days=None,
                                  cycle_billing_duration=dt.timedelta(days=1),
                                  metered_features=[seat_feature, metered_feature])
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

        assert Invoice.objects.all().count() == 0

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('1.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('60.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        print_entries(invoice)
        # Including 40 units per seat, at $1 per unit, and $10 per seat.
        # 60 units are consumed (20 units over) by the end of the period
        # (=$20), and one seat is added (=$10), so our total is $70.00
        #
        assert invoice.total == Decimal(70.0)

    def test_prebilled_metered_feature_units_and_add_overage_at_separate_rate(self):
        """ Mark a feature as pre-billed, and charge some overage.
        """
        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('10.0'))
        seat_feature.save()

        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('40.00'),
                                                prebill_included_units=True,
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(
                                                    value="charc-base"),
                                                price_per_unit=Decimal('1.00'),)
        metered_feature.save()

        charcoal_overage = MeteredFeatureFactory(name="Charcoal Base Units",
                                                 unit="Barrels (per seat)",
                                                 linked_feature=seat_feature,
                                                 included_units_calculation="multiply",
                                                 included_units=Decimal('0.00'),
                                                 prebill_included_units=True,
                                                 included_units_during_trial=Decimal('0.00'),
                                                 product_code=ProductCodeFactory(
                                                     value="charc-overage"),
                                                 price_per_unit=Decimal('2.00'),)
        charcoal_overage.save()

        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=1,
                                  generate_after=0,
                                  enabled=True,
                                  provider=provider,
                                  product_code=ProductCodeFactory(value="monthly-deliv-plan"),
                                  amount=Decimal('0.00'),
                                  prebill_plan=False,
                                  currency=currency,
                                  trial_period_days=None,
                                  cycle_billing_duration=dt.timedelta(days=1),
                                  metered_features=[seat_feature,
                                                    metered_feature,
                                                    charcoal_overage])
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

        assert Invoice.objects.all().count() == 0

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('1.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('40.00'))
        mf.save()

        # Add some overage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=charcoal_overage,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('20.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        invoice = Invoice.objects.all().first()

        print_entries(invoice)
        # Including 40 units per seat, at $1 per unit, and $10 per seat.
        # 60 units are consumed (20 units over) by the end of the
        # period. The units that are over are tracked on a separate
        # feature for an overage rate of $2/unit (=$40).
        # One seat is added (=$10), so our total is $90.00
        #
        assert invoice.total == Decimal(90.0)

# LinkedSubscriptions
@override_settings(PAYMENT_PROCESSORS=PAYMENT_PROCESSORS)
class TestLinkedSubscriptions(TestCase):

    def __init__(self, *args, **kwargs):
        super(TestLinkedSubscriptions, self).__init__(*args, **kwargs)
        self.output = StringIO()

    @pytest.mark.django_db
    @pytest.mark.skip
    def test_horrible_customers(self):
        assert 1 == 0

    @pytest.mark.django_db
    def test_linked_subscriptions_with_linked_usage_and_linked_cost(self):
        """ Create two plans and two subscriptions, assigning separate
        features to each. Test that linked calculation can work across
        plans.  """

        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('10.0'))
        seat_feature.save()

        seat_plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                       interval_count=1,
                                       generate_after=0,
                                       enabled=True,
                                       provider=provider,
                                       product_code=ProductCodeFactory(value="monthly-seat-plan"),
                                       amount=Decimal('10.00'),
                                       prebill_plan=False,
                                       currency=currency,
                                       trial_period_days=None,
                                       cycle_billing_duration=dt.timedelta(days=1),
                                       metered_features=[seat_feature])
        seat_plan.save()


        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('5.00'),)
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
        seat_subscription = SubscriptionFactory.create(plan=seat_plan,
                                                       start_date=start_date,
                                                       customer=customer)
        seat_subscription.activate()
        seat_subscription.save()

        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  linked_subscription=seat_subscription,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        call_command('generate_docs',
                     date=feature_usage_start,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=seat_subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('2.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('40.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 2
        seat_invoice = Invoice.objects.all().first()
        char_invoice  = Invoice.objects.all().last()

        # Including 20 units per seat, and two seats, which means 40
        # units are included.
        for i in Invoice.objects.all():
            print(i.total)
            print_entries(i)

        assert seat_invoice.total == Decimal(30.0)
        assert char_invoice.total == Decimal(30.0)


    @pytest.mark.django_db
    def test_linked_subscriptions_with_linked_usage_and_linked_cost_separate_interval(self):
        """ Create two plans and two subscriptions with separate billing
        intervals, assigning separate features to each. Test that linked
        calculation can work across plans.  """

        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=ProductCodeFactory(value="charc-seats"),
            price_per_unit=Decimal('10.0'))
        seat_feature.save()

        seat_plan = PlanFactory.create(interval=Plan.INTERVALS.YEAR,
                                       generate_after=0,
                                       enabled=True,
                                       provider=provider,
                                       product_code=ProductCodeFactory(value="yearly-seat-plan"),
                                       amount=Decimal('10.00'),
                                       prebill_plan=False,
                                       currency=currency,
                                       trial_period_days=None,
                                       # cycle_billing_duration=dt.timedelta(days=1),
                                       metered_features=[seat_feature])
        seat_plan.save()


        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('5.00'),)
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
        seat_subscription = SubscriptionFactory.create(plan=seat_plan,
                                                       start_date=start_date,
                                                       customer=customer)
        seat_subscription.activate()
        seat_subscription.save()

        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  linked_subscription=seat_subscription,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        call_command('generate_docs',
                     date=feature_usage_start,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=seat_subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('2.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('40.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        char_invoice  = Invoice.objects.all().last()

        # Including 20 units per seat, and two seats, which means 40
        # units are included.
        for i in Invoice.objects.all():
            print(i.total)
            print_entries(i)

        assert char_invoice.total == Decimal(10.0)

    @pytest.mark.django_db
    def test_linked_subscriptions_with_seat_interval_changes(self):
        """ Follow the plan structure of above, but with extra steps to
        increment seats upwards after the first round of billing to
        ensure costs are as predicted.  """
        from django.db.models import Q

        # Set up the timescale.
        start_date        = dt.date(2018, 1, 1)
        prev_billing_date = generate_docs_date('2018-01-01')
        curr_billing_date = generate_docs_date('2018-01-31')
        next_billing_date = generate_docs_date('2018-02-01')
        thrd_billing_date = generate_docs_date('2018-04-01')
        end_date        = dt.date(2019, 1, 1)
        end_billing_date  = generate_docs_date('2019-01-15')

        seat_feature_usage_set = dt.date(2018, 1, 1)
        feature_usage_start    = dt.date(2018, 1, 2)
        feature_usage_end      = dt.date(2018, 1, 30)

        seat_feature_increment  = dt.date(2018, 3, 1)
        snd_feature_usage_start = dt.date(2018, 3, 2)
        snd_feature_usage_end   = dt.date(2018, 3, 30)

        ## Lots of test setup madness. {{{

        provider = ProviderFactory.create(flow=Provider.FLOWS.INVOICE)

        customer = CustomerFactory.create(consolidated_billing=False,
                                          sales_tax_percent=Decimal('0.00'))
        currency = 'USD'

        seat_code = ProductCodeFactory(value="charc-seats")
        seat_Q = Q(invoice_entries__product_code=seat_code)
        seat_feature = MeteredFeatureFactory(
            name="Charcoal Users",
            unit="Seats",
            included_units=Decimal('0.00'),
            product_code=seat_code,
            price_per_unit=Decimal('10.0'))
        seat_feature.save()

        seat_plan = PlanFactory.create(interval=Plan.INTERVALS.YEAR,
                                       interval_count=1,
                                       generate_after=0,
                                       enabled=True,
                                       provider=provider,
                                       product_code=ProductCodeFactory(value="yearly-seat-plan"),
                                       amount=Decimal('10.00'),
                                       prebill_plan=False,
                                       currency=currency,
                                       trial_period_days=None,
                                       cycle_billing_duration=dt.timedelta(days=1),
                                       metered_features=[seat_feature])
        seat_plan.save()


        metered_feature = MeteredFeatureFactory(name="Charcoal Base Units",
                                                unit="Barrels (per seat)",
                                                linked_feature=seat_feature,
                                                included_units_calculation="multiply",
                                                included_units=Decimal('20.00'),
                                                included_units_during_trial=Decimal('0.00'),
                                                product_code=ProductCodeFactory(value="charc-base"),
                                                price_per_unit= Decimal('5.00'),)
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
        seat_subscription = SubscriptionFactory.create(plan=seat_plan,
                                                       start_date=start_date,
                                                       customer=customer)
        seat_subscription.activate()
        seat_subscription.save()

        subscription = SubscriptionFactory.create(plan=plan,
                                                  start_date=start_date,
                                                  # end_date=end_date,
                                                  linked_subscription=seat_subscription,
                                                  customer=customer)
        subscription.activate()
        subscription.save()

        ## }}}

        ## First test billing phase {{{
        call_command('generate_docs',
                     date=feature_usage_start,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 0

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=seat_subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_usage_set,
                                             end_date=seat_feature_usage_set,
                                             consumed_units=Decimal('1.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=feature_usage_start,
                                             end_date=feature_usage_end,
                                             consumed_units=Decimal('40.00'))
        mf.save()

        call_command('generate_docs',
                     date=feature_usage_end,
                     stdout=self.output)

        call_command('generate_docs',
                     date=next_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1
        char_invoice  = Invoice.objects.all().last()

        # Including 20 units per seat, and two seats, which means 40
        # units are included.
        for i in Invoice.objects.exclude(seat_Q):
            print(i.total)
            print_entries(i)
            if seat_code in [e.product_code for e in i.entries] or i.state != 'paid':
                continue
            i.issue()
            i.pay()
            i.save()

        assert char_invoice.total == Decimal(110.0)

        ## }}}

        ## second test billing phase {{{
        call_command('generate_docs',
                     date=feature_usage_start,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 1

        # Add a seat
        MeteredFeatureUnitsLogFactory.create(subscription=seat_subscription,
                                             metered_feature=seat_feature,
                                             start_date=seat_feature_increment,
                                             end_date=seat_feature_increment,
                                             consumed_units=Decimal('4.00'))

        # Track some usage
        mf = MeteredFeatureUnitsLogFactory.create(subscription=subscription,
                                             metered_feature=metered_feature,
                                             start_date=snd_feature_usage_start,
                                             end_date=snd_feature_usage_end,
                                             consumed_units=Decimal('80.00'))
        mf.save()

        call_command('generate_docs',
                     date=snd_feature_usage_end,
                     stdout=self.output)


        call_command('generate_docs',
                     date=thrd_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 3
        char_invoice  = Invoice.objects.all().last()

        # Usage during this period doubled to 80 total, and the user
        # also upped the seats to 4.

        # monthly plan -- 
        #   base minute plan: $10 (no matter usage)
        #   rate cost: $5/unit. 
        #   used:   80 
        #   subtotal:  $400

        for i in Invoice.objects.all():
            print(i.total)
            print_entries(i)
            if seat_code in [e.product_code for e in i.entries] or i.state == 'paid':
                continue
            i.issue()
            i.pay()
            i.save()

        # assert char_invoice.total == Decimal(110.0)

        ## }}}

        ## final test billing phase {{{

        # seat_subscription.cancel(end_billing_date)
        # seat_subscription.save()

        call_command('generate_docs',
                     date=end_billing_date,
                     stdout=self.output)

        assert Invoice.objects.all().count() == 5
        print("  END OF YEAR  ")
        year_invoice  = Invoice.objects.filter(seat_Q).first()
        print_entries(year_invoice)

        for e in year_invoice.invoice_entries.all():
            # Cumulatively we used 5 seats over the course
            if e.product_code == seat_code:
                assert e.quantity == Decimal(5.0)

        # Final year total should be 10 for the whole base plan, and
        # 5*10 for consumed units.
        assert year_invoice.total == Decimal(10.0) + Decimal(5*10.0)

        # NB: this process also generates an invoice for all the
        # previous unbilled months because we didn't include those in
        # the test.

        # for i in Invoice.objects.exclude(seat_Q):
        #     if seat_code in [e.product_code for e in i.entries] or i.state == 'paid':
        #         continue
        #     print(i.total)
        #     print_entries(i)

        # yearly plan --
        #   cost per seat: $10/seat
        #   used: 5

