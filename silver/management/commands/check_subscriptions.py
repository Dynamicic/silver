from __future__ import absolute_import

import logging
import argparse

from datetime import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import translation

from silver.subscription_checker import SubscriptionChecker
from silver.models import Subscription


logger = logging.getLogger(__name__)


def date(date_str):
    try:
        return dt.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        msg = "Not a valid date: '{date_str}'. "\
              "Expected format: YYYY-MM-DD.".format(date_str=date_str)
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):
    help = 'Checks subscriptions for documents that are unpaid after customer grace period.'

    def add_arguments(self, parser):
        parser.add_argument('--subscription',
                            action='store', dest='subscription_id', type=int,
                            help='The id of ths subscription to be billed.')
        parser.add_argument('--date',
                            action='store', dest='billing_date', type=date,
                            help='The billing date (format YYYY-MM-DD).')

    def handle(self, *args, **options):
        translation.activate('en-us')

        billing_date = options['billing_date']

        subscription_check = SubscriptionChecker()
        if options['subscription_id']:
            try:
                subscription_id = options['subscription_id']
                logger.info('Checking subscription with id=%s; '
                            'billing_date=%s.', subscription_id,
                            billing_date)

                subscription = Subscription.objects.get(id=subscription_id)
                subscription_check.check(subscription=subscription,
                                         billing_date=billing_date)
                self.stdout.write('Done.')
            except Subscription.DoesNotExist:
                msg = 'The subscription with the provided id does not exist.'
                self.stdout.write(msg)
        else:
            logger.info('Checking all the available subscriptions; '
                        'billing_date=%s.', billing_date)

            subscription_checker.check(billing_date=billing_date)
            self.stdout.write('Done.')

