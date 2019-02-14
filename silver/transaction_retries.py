from __future__ import absolute_import

import datetime as dt
from datetime import timedelta

import logging

from decimal import Decimal
from itertools import chain

from django.utils import timezone
from django.db.models import Q
from django.apps import apps

from silver.models import (Customer, DocumentEntry, Subscription,
                           Proforma, Invoice, Provider, BillingLog)
from silver.utils.dates import ONE_DAY


logger = logging.getLogger(__name__)


class TransactionRetryAttempter(object):

    def _query_payment_failures(self):
        Doc         = apps.get_model('silver.BillingDocumentBase')
        Invoice     = apps.get_model('silver.Invoice')
        Proforma    = apps.get_model('silver.Proforma')
        Transaction = apps.get_model('silver.Transaction')

        # The query will be the result of an exclusion, to make most use
        # of Field lookups. So, we want to exclude successful
        # transaction states.
        # 
        trx_successful_states = [
            # - Transaction.States.Failed,
            Transaction.States.Initial,
            Transaction.States.Pending,
            Transaction.States.Settled,
            Transaction.States.Canceled,
            Transaction.States.Refunded,
        ]

        doc_successful_states = [
            # - Doc.STATES.ISSUED,
            Doc.STATES.DRAFT,
            Doc.STATES.PAID,
            Doc.STATES.CANCELED,
        ]

        payment_failures = Q(state__in=doc_successful_states)

        inv_transactions = \
            Q(invoice_transactions__state__in=trx_successful_states)

        pro_transactions = \
            Q(proforma_transactions__state__in=trx_successful_states)

        inv = Invoice.objects.exclude(payment_failures & inv_transactions)

        # NB: excluding proformas from this flow for now.
        # pro = Proforma.objects.exclude(payment_failures & pro_transactions)
        # chain(inv, pro)

        return inv

    def check(self, document=None, documents=None, billing_date=None, force=None):
        """ The `public` method called when one wants to check unpaid
        billing docs for failed attempts, and then retry them based on
        payment method settings.

        :param document:  the document that will be checked
        :param documents: the documents that will be checked
        :param force:     If True, ignores the time check and issues payments.
        :param billing_date: the date used as billing date. most likely
            this is timezone.now()

        :note
            If `document` is passed, only that document will be checked,
            use `documents` to specify a batch. Default behavior is to
            query and check all existing documents.
        """

        billing_date = billing_date or timezone.now()

        if not document:
            if not documents:
                documents = self._query_payment_failures()

            self._check_all(documents=documents,
                            billing_date=billing_date, force=force)
        else:
            self._check_for_single_document(document=document,
                                            billing_date=billing_date,
                                            force=force)

    def _check_all(self, documents, billing_date, force):
        """ Issue new transactions for all documents.
        """
        if billing_date:
            assert type(billing_date) == type(timezone.now())

        for document in documents:
            self._check_for_single_document(
                document, billing_date, force
            )

    def _log_document(self, document, transaction):
        msg = 'Retrying document with failed transaction, and retry attempts: %s'
        logger.debug(msg, {
            'document': transaction,
            'transaction': transaction,
        })

    def _get_last_failed_for_doc(self, document):
        """ Return the last failed transaction for a document.
        """

        Transaction = apps.get_model('silver.Transaction')

        # The query will be the result of an exclusion, to make most use
        # of Field lookups. So, we want to exclude successful
        # transaction states.
        # 
        trx_successful_states = [
            # - Transaction.States.Failed,
            Transaction.States.Initial,
            Transaction.States.Pending,
            Transaction.States.Settled,
            Transaction.States.Canceled,
            Transaction.States.Refunded,
        ]

        transaction = document.transactions\
                .exclude(state__in=trx_successful_states)\
                .order_by('updated_at')\
                .first()

        return transaction

    def _can_make_payment_attempts(self, document, billing_date):
        """ Check that we can make new payment attempts for the
        document.

        :returns Boolean:
        """

        transaction    = self._get_last_failed_for_doc(document)
        if transaction is None:
            return False

        payment_method = transaction.payment_method

        # TODO: document that endless retries are disallowed
        if not payment_method.data.get('attempt_retries_after') and \
           not payment_method.data.get('stop_retry_attempts'):
            return False

        _attempt_retries_after = payment_method.data.get('attempt_retries_after')
        _stop_retry_attempts   = payment_method.data.get('stop_retry_attempts')

        attempt_retries_after = timedelta(days=_attempt_retries_after)
        stop_retry_attempts   = timedelta(days=_stop_retry_attempts)

        trx_allow_retries   = transaction.created_at + attempt_retries_after
        trx_no_more_retries = transaction.created_at + stop_retry_attempts

        can_make_attempts = trx_allow_retries <= billing_date and \
                            billing_date <= trx_no_more_retries

        return can_make_attempts

    def _check_for_single_document(self, document, billing_date, force):
        """ For a single document that has no successful payments, issue
        a new transaction.
        """
        from datetime import timedelta

        def create_transaction_for_document(doc, method):
            """ Create transactions for documents, for the payment
            methods that allow it.
            """
            # get a usable, recurring payment_method for the customer
            PaymentMethod = apps.get_model('silver.PaymentMethod')
            Transaction = apps.get_model('silver.Transaction')

            if method.verified and not method.canceled:
                try:
                    return Transaction.objects.create(document=doc,
                                                      payment_method=method)
                except ValidationError:
                    pass

            return None

        if not force:
            if not self._can_make_payment_attempts(document, billing_date):
                return

        # TODO: only create once if transaction has .proforma &
        # .invoice.
        transaction    = self._get_last_failed_for_doc(document)
        if transaction is None:
            return None
        payment_method = transaction.payment_method

        updated = create_transaction_for_document(document, payment_method)
        updated.save()

        self._log_document(document, updated)


