from __future__ import absolute_import

import datetime as dt
from datetime import timedelta

import logging

from decimal import Decimal

from django.utils import timezone

from silver.models import (Customer, DocumentEntry, Subscription,
                           Proforma, Invoice, Provider, BillingLog)
from silver.utils.dates import ONE_DAY


logger = logging.getLogger(__name__)


class OverpaymentChecker(object):

    @property
    def default_provider(self):
        """ Returns the default provider. Locally caches so query runs
        only once per instance. """

        if not hasattr(self, '_provider'):
            self._provider = self._default_provider()

        return self._provider

    def _default_provider(self):
        """ Search for and return a default provider.  Create a default
        provider if none exists. The default provider will be created
        with a Provider.meta field containing an `overpayment_checker`
        value of `True`.

        The provider may be customized in any way, as long as this meta
        value remains set. Alternatively, use an existing provider and
        set the same Provider.meta field.
        """

        _meta = {'overpayment_checker': True}

        provider_defaults = {
            'invoice_starting_number': 1,
            'name': 'Default OverpaymentChecker Provider',
            'flow': Provider.FLOWS.INVOICE,
            'invoice_series': 'OverpaymentInvoice',
        }

        try:
            provider = Provider.objects.get(meta=_meta)
        except Provider.DoesNotExist:
            provider = Provider.objects.create(meta=_meta,
                                               **provider_defaults)
            provider.save()

        return provider

    def check(self, customer=None, billing_date=None, customers=None,
              provider=None):
        """
        The `public` method called when one wants to check customer
        overpayment balances, and issue invoices to adjust.

        :param customers: the customers that will be checked
        :param provider: the invoice provider. If none, a default
            provider will be used
        :param billing_date: the date used as billing date. most likely
            this is timezone.now().date()
        :param customers: the customers that will be checked

        :note
            If `customer` is passed, only the documents for that
            customer are generated, use `customers` to specify a
            batch. Default behavior is to check all customers.
        """

        # TODO: this may be overcomplex, depending on how management
        # tasks call this, so simplify to passing `customers` only.
        # Single customer is just [customer].

        # TODO: although this is dependent on billing_date to issue an
        # invoice, the balance search isn't sensitive to the date:
        # making it sensitive to date may be important.

        if not provider:
            provider = self.default_provider

        if not customer:
            customers = customers or Customer.objects.all()
            self._check_all(billing_date=billing_date,
                            customers=customers, provider=provider)
        else:
            self._check_for_single_customer(customer=customer,
                                            billing_date=billing_date,
                                            provider=provider)

    def _check_all(self, billing_date, customers, provider):
        """
        Generates the invoices/proformas for all the subscriptions that should
        be billed.
        """

        billing_date = billing_date or timezone.now().date()

        for customer in customers:
            self._check_for_single_customer(
                customer, billing_date, provider
            )

    def _log_customer_adjustment(self, customer, invoice):
        logger.debug('Cancelling unpaid subscription: %s', {
            'customer': customer,
            'document': invoice,
            'number': invoice.number,
            'provider': invoice.provider,
        })

    def _does_customer_have_existing_pending_repayment(self, customer,
                                                       current_balance,
                                                       provider):
        if current_balance != 0:
            any_invoices = Invoice.objects.filter(customer=customer,
                                                  provider=provider,
                                                  state__in=[Invoice.STATES.DRAFT,
                                                             Invoice.STATES.ISSUED])
            if any_invoices.count() > 0:
                return True
        return False


    def _check_for_single_customer(self, customer, billing_date, provider):
        """
        Generates the billing documents for all the subscriptions of a customer
        who does not use consolidated billing.
        """

        current_balance = customer.balance_on_date(billing_date)

        if self._does_customer_have_existing_pending_repayment(customer,
                                                               current_balance,
                                                               provider):
            return

        desc = "Adjusting for an overpayment to a previous invoice."
        entry = DocumentEntry.objects.create(quantity=1,
                                             unit_price=-current_balance,
                                             description=desc)

        invoice = Invoice.objects.create(customer=customer,
                                         provider=provider,
                                         issue_date=billing_date,
                                         # due_date=billing_date,
                                         sales_tax_percent=0,
                                         currency='USD')
        invoice.invoice_entries.add(entry)
        invoice.issue()
        invoice.save()

        # TODO: when customer has no payment methods, no transactions
        # will be created; is this a problem?

        self._log_customer_adjustment(customer, invoice)

