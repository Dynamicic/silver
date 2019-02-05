from __future__ import absolute_import

import datetime as dt
import logging

from decimal import Decimal

from django.utils import timezone

from silver.models import Customer, Subscription, Proforma, Invoice, Provider, BillingLog
from silver.utils.dates import ONE_DAY


logger = logging.getLogger(__name__)


class SubscriptionChecker(object):
    def check(self, subscription=None, billing_date=None, customers=None,
                 force_generate=False):
        """
        The `public` method called when one wants to check subscriptions are up to date.

        :param subscription: the subscription for which one wants to generate the
            proformas/invoices.
        :param billing_date: the date used as billing date. most likely
            this is timezone.now().date()
        :param customers: the customers for which one wants to generate the
            proformas/invoices.
        :param force_generate: if True, invoices are generated at the date
            indicated by `billing_date` instead of the normal end of billing
            cycle.

        :note
                If `subscription` is passed, only the documents for that subscription are
            generated.
                If the `customers` parameter is passed, only the docments for those customers are
            generated.
                Only one of the `customers` and `subscription` parameters may be passed at a time.
                If neither the `subscription` nor the `customers` parameters are passed, the
                documents for all the customers will be generated.
        """

        if not subscription:
            customers = customers or Customer.objects.all()
            self._check_all(billing_date=billing_date,
                            customers=customers,
                            force_generate=force_generate)
        else:
            self._check_for_single_subscription(subscription=subscription,
                                                billing_date=billing_date,
                                                force_generate=force_generate)

    def _check_all(self, billing_date=None, customers=None, force_generate=False):
        """
        Generates the invoices/proformas for all the subscriptions that should
        be billed.
        """

        billing_date = billing_date or timezone.now().date()
        # billing_date -> the date when the billing documents are issued.

        for customer in customers:
            if customer.consolidated_billing:
                self._check_for_user_with_consolidated_billing(
                    customer, billing_date, force_generate
                )
            else:
                self._check_for_user_without_consolidated_billing(
                    customer, billing_date, force_generate
                )

    def _log_subscription_billing(self, document, subscription):
        logger.debug('Checking subscription: %s', {
            'subscription': subscription.id,
            'state': subscription.state,
            'doc_type': document.provider.flow,
            'number': document.number,
            'provider': document.provider.id,
            'customer': document.customer.id
        })

    def _is_subscription_unpaid_after_grace(self, customer, billing_date, subscription):
        import timedelta

        due_grace_period = timedelta(days=customer.payment_due_days)

        lbl = subscription.last_billing_log

        if lbl.invoice:
            doc = lbl.invoice

        if lbl.proforma:
            doc = lbl.proforma

        # NB: this can also check for failed transactions. 
        # for tx in doc.transactions:
        #     if tx.state == Transaction.States.Failed:

        # Doc is issued
        if doc.state == doc.__class__.STATES.ISSUED:
            # current billing date is greater than the issued date +
            # grace period
            if billing_date > (doc.issued_date + due_grace_period):
                return True

        return False

    def get_subscriptions_with_doc_issued_and_past_grace(self, customer, billing_date, force_generate):
        import timedelta

        due_grace_period = timedelta(days=customer.payment_due_days)

        # Select all the active or canceled subscriptions
        subs_to_bill = []
        criteria = {'state__in': [Subscription.STATES.ACTIVE,
                                  Subscription.STATES.CANCELED]}
        for subscription in customer.subscriptions.filter(**criteria):
            # Find a subscription with billing log items where invoices
            # have failed transactions
            if self._is_subscription_unpaid_after_grace(customer,
                                                        billing_date,
                                                        subscription):
                subs_to_bill.append(subscription)

        return subs_to_bill

    def _bill_subscription_into_document(self, subscription, billing_date, document=None):
        """ TODO: document this
        """

        if not document:
            document = self._create_document(subscription, billing_date)

        self._log_subscription_billing(document, subscription)

        kwargs = subscription.billed_up_to_dates

        kwargs.update({
            'billing_date': billing_date,
            'subscription': subscription,
            subscription.provider.flow: document,
        })
        self.add_subscription_cycles_to_document(**kwargs)

        if subscription.state == Subscription.STATES.CANCELED:
            subscription.end()
            subscription.save()

        return document

    def _check_for_user_with_consolidated_billing(self, customer, billing_date, force_generate):
        """
        Checks the billing documents for all the subscriptions of a customer
        who uses consolidated billing.
        """

        # For each provider there will be one invoice or proforma. The cache is necessary as a
        # certain customer might have more than one subscription
        # => all the subscriptions belonging to the same provider will be added to the same document

        existing_provider_documents = {}
        for subscription in self.get_subscriptions_with_doc_issued_and_past_grace(customer, billing_date,
                                                                                  force_generate):

        for provider, document in existing_provider_documents.items():
            # TODO: suspend subscription if after grace period

            # document = self._bill_subscription_into_document(subscription, billing_date)

            # if provider.default_document_state == Provider.DEFAULT_DOC_STATE.ISSUED:
            #     document.issue()

            raise NotImplementedError
            subscription.cancel(when="now")
            subscription.save()


    def _check_for_user_without_consolidated_billing(self, customer, billing_date,
                                                        force_generate):
        """
        Generates the billing documents for all the subscriptions of a customer
        who does not use consolidated billing.
        """

        # The user does not use consolidated_billing => add each subscription to a separate document
        for subscription in self.get_subscriptions_with_doc_issued_and_past_grace(customer,
                                                                                  billing_date,
                                                                                  force_generate):
            provider = subscription.plan.provider

            # TODO: suspend subscription if after grace period

            # document = self._bill_subscription_into_document(subscription, billing_date)

            # if provider.default_document_state == Provider.DEFAULT_DOC_STATE.ISSUED:
            #     document.issue()
            raise NotImplementedError
            subscription.cancel(when="now")
            subscription.save()

    def _generate_for_single_subscription(self, subscription=None, billing_date=None,
                                          force_generate=False):
        """
        Generates the billing documents corresponding to a single subscription.
        Usually used when a subscription is ended with `when`=`now`.
        """

        billing_date = billing_date or timezone.now().date()

        provider = subscription.provider

        if not subscription.should_be_billed(billing_date) or force_generate:
            return

        # TODO: suspend subscription if after grace period
        # document = self._bill_subscription_into_document(subscription, billing_date)
        if self._is_subscription_unpaid_after_grace(customer,
                                                    billing_date,
                                                    subscription):

            raise NotImplementedError
            subscription.cancel(when="now")
            subscription.save()

        # if provider.default_document_state == Provider.DEFAULT_DOC_STATE.ISSUED:
        #     document.issue()

