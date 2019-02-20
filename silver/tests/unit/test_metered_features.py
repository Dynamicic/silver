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
                                    ProviderFactory,
                                    SubscriptionFactory,
                                    TransactionFactory)


import logging
logging.basicConfig(level=logging.WARNING)

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
            # TODO: doc. For now it's basic:
            #  multiply
            #  add
            #  subtract
            included_units_calculation="multiply")

        # Create the plan
        plan = PlanFactory.create(interval=Plan.INTERVALS.MONTH,
                                  interval_count=1,
                                  generate_after=30,
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

