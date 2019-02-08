from __future__ import absolute_import

import logging
import argparse

from datetime import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import translation

from silver.overpayment_checker import OverpaymentChecker
from silver.models import Customer, Provider


logger = logging.getLogger(__name__)


def date(date_str):
    try:
        return dt.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        msg = "Not a valid date: '{date_str}'. "\
              "Expected format: YYYY-MM-DD.".format(date_str=date_str)
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):
    help = 'Checks customers for overpaid balances and issues an invoice to correct.'

    def add_arguments(self, parser):
        parser.add_argument('--customer',
                            action='store', dest='customer_id', type=int,
                            help='The id of ths customer to be checked.')
        parser.add_argument('--date',
                            action='store', dest='billing_date', type=date,
                            help='The billing date (format YYYY-MM-DD).')

    def handle(self, *args, **options):
        translation.activate('en-us')

        billing_date = options['billing_date']

        overpayment_check = OverpaymentChecker()
        if options['customer_id']:
            try:
                customer_id = options['customer_id']
                logger.info('Checking customer with id=%s; '
                            'billing_date=%s.', customer_id,
                            billing_date)

                customer = Customer.objects.get(id=customer_id)
                overpayment_check.check(customer=customer,
                                        billing_date=billing_date)
                self.stdout.write('Done.')
            except Customer.DoesNotExist:
                msg = 'A customer with the provided id does not exist.'
                self.stdout.write(msg)
        else:
            logger.info('Checking all the available customers; '
                        'billing_date=%s.', billing_date)

            customers = Customer.objects.all()
            overpayment_check.check(customers=customers,
                                    billing_date=billing_date)
            self.stdout.write('Done.')


