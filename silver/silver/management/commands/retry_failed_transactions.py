from __future__ import absolute_import

import logging
import argparse

from datetime import datetime as dt

from django.core.management.base import BaseCommand
from django.utils import translation

from silver.transaction_retries import TransactionRetryAttempter
from silver.models import Customer, Provider, Invoice


logger = logging.getLogger(__name__)


def date(date_str):
    try:
        return dt.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        msg = "Not a valid date: '{date_str}'. "\
              "Expected format: YYYY-MM-DD.".format(date_str=date_str)
        raise argparse.ArgumentTypeError(msg)


class Command(BaseCommand):
    help = 'Checks unpaid documents for failed transactions and re-issues.'

    def add_arguments(self, parser):
        parser.add_argument('--document',
                            action='store', dest='invoice_id', type=int,
                            help='The id of ths document to be checked.')
        parser.add_argument('--date',
                            action='store', dest='billing_date', type=date,
                            help='The billing date (format YYYY-MM-DD).')
        parser.add_argument('--force',
                            action='store', dest='force', type=bool,
                            help='Ignore the datetime check')

    def handle(self, *args, **options):
        translation.activate('en-us')

        billing_date = options['billing_date']

        failed_check = TransactionRetryAttempter()
        if options['invoice_id']:
            try:
                invoice_id = options['invoice_id']
                logger.info('Checking document with id=%s; '
                            'billing_date=%s.', invoice_id,
                            billing_date)

                document = Invoice.objects.get(id=invoice_id)
                failed_check.check(document=document,
                                   billing_date=billing_date,
                                   force=options['force'])
                self.stdout.write('Done.')
            except Invoice.DoesNotExist:
                msg = 'A document with the provided id does not exist.'
                self.stdout.write(msg)
        else:
            logger.info('Checking all the available documents; '
                        'billing_date=%s.', billing_date)

            failed_check.check(document=None, documents=None,
                               billing_date=billing_date,
                               force=options['force'])
            self.stdout.write('Done.')



