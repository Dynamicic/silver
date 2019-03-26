import logging
from datetime import datetime, timedelta

import authorizenet

import dateutil.parser
from django_fsm import TransitionNotAllowed

from django.conf import settings

from silver.models import Transaction
from silver.payment_processors import PaymentProcessorBase, get_instance
from silver.payment_processors.forms import GenericTransactionForm
from silver.payment_processors.mixins import TriggeredProcessorMixin

from silver_authorizenet.models import AuthorizeNetPaymentMethod
from silver_authorizenet.models.customer_data import CustomerData
from silver_authorizenet.views import AuthorizeNetTransactionView

from authorizenet import apicontractsv1
from authorizenet.apicontrollers import (createTransactionController,
                                         createCustomerProfileController,
                                         getCustomerPaymentProfileController,
                                         getTransactionDetailsController,
                                         createCustomerPaymentProfileController)

from .authorize_net_requests import *

logger = logging.getLogger(__name__)

class AuthorizeNetTriggeredBase(AuthorizeNetRequests,
                                PaymentProcessorBase,
                                TriggeredProcessorMixin):

    """ This contains the base methods that are necessary to create a
    payment gateway within Silver. """

    payment_method_class   = AuthorizeNetPaymentMethod
    transaction_view_class = AuthorizeNetTransactionView
    form_class             = GenericTransactionForm
    _has_been_setup        = False

    def is_payment_method_recurring(self, payment_method):
        raise NotImplementedError

    def __init__(self, name, *args, **kwargs):
        super(AuthorizeNetTriggeredBase, self).__init__(name)

        # if self._has_been_setup:
        #     return

        self.environment = kwargs.pop('environment', None)
        AuthorizeNetTriggeredBase._has_been_setup = True

    @property
    def merchantId(self):
        # TODO:
        return "MerchantID-0001"

    def create_customer_profile(self, customer):
        """ Create all the customer payment profiles needed within
        Authorize.net to authorize a transaction by payment profile.

        :parameter customer: A Silver Customer instance
        :return True if successful, False otherwise:
        """

        customer_data            = CustomerData.objects.get_or_create(customer = customer)[0]
        customer_authorizenet_id = customer_data.get('id')

        _cust         = self._create_customer_profile(customer, customer_data)
        _cust_payment = self._create_customer_payment_profile(customer, _cust)

        if _cust_payment:
            return True

        return False

    def client_token(self, customer):
        """ Return the client token for a given customer.

        :param customer: A Silver customer
        :returns customer_payment_profile_id:
        """

        customer_data = CustomerData.objects.get_or_create(customer=customer)[0]

        customer_id                 = customer_data.get('id')
        customer_profile_id         = customer_data.get('profile_id')
        customer_payment_profile_id = customer_data.get('payment_id')

        if customer_payment_profile_id is not None:
            return customer_payment_profile_id

        getCustomerPaymentProfile                          = apicontractsv1.getCustomerPaymentProfileRequest()
        getCustomerPaymentProfile.merchantAuthentication   = self.merchantAuth
        getCustomerPaymentProfile.customerProfileId        = customer_profile_id
        getCustomerPaymentProfile.customerPaymentProfileId = customer_payment_profile_id

        controller = getCustomerPaymentProfileController(getCustomerPaymentProfile)
        controller.execute()

        response = controller.getresponse()

        resp_okay = response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok

        if resp_okay:
            self._update_customer(
                customer,
                {'id': customer_id,
                 'payment_id': str(response.customerPaymentProfileId)}
            )
            # TODO: update token on user profile
            return response.customerPaymentProfileId
        else:
            logger.warning(
                'Couldn\'t obtain Authorize.net client_token %s', {
                    'customer_id': customer_authorizenet_id,
                    'exception': str(e)
                }
            )

    def refund_transaction(self, transaction, payment_method=None):
        """ Refund a transaction

        :param transaction: A Silver transaction with a AuthorizeNet payment method.
        :param payment_method: The payment method used to authorize the original transaction
        :returns True if the state transition was successful, False otherwise.
        """
        payment_processor = get_instance(transaction.payment_processor)

        if not payment_processor == self:
            return False

        transId = str(transaction.data.get('authorizenet_id'))

        payment            = apicontractsv1.paymentType()
        payment.creditCard = self._create_credit_card(transaction.payment_method.customer)

        tr_req                 = apicontractsv1.transactionRequestType()
        tr_req.transactionType = "refundTransaction"
        tr_req.amount          = transaction.amount
        tr_req.refTransId      = transId
        tr_req.payment         = payment

        create_req                        = apicontractsv1.createTransactionRequest()
        create_req.merchantAuthentication = self.merchantAuth
        create_req.refId                  = self.merchantId
        create_req.transactionRequest     = tr_req

        controller = createTransactionController(create_req)

        try:
            controller.execute()
        except Exception as e:
            logger.warning(
                'Error executing request to refund transaction %s', {
                    'transaction_id': transId,
                    'exception': str(e)
                }
            )

        response = controller.getresponse()

        have_resp = response is not None

        if have_resp:
            status, resp_okay = self._get_authorizenet_transaction_status(response)
            t_resp = response.transactionResponse

            if resp_okay:
                transaction.external_reference = t_resp.transId

            # TODO: wrong object for `response`?
            return self._transition_silver_transaction_to(transaction,
                                                          response,
                                                          status,
                                                          transaction.States.Refunded)
        else:
            logger.warning(
                'Couldn\'t refund transaction %s', {
                    'transaction_id': transId,
                    'messages': response.messages.message[0]['text'].text
                }
            )
            return False

    def cancel_transaction(self, transaction, payment_method=None):
        return self.void_transaction(transaction, payment_method)

    def void_transaction(self, transaction, payment_method=None):
        """ Void a transaction
        :param transaction: A Silver transaction with a AuthorizeNet payment method.
        :param payment_method: The payment method used to authorize the original transaction
        :returns True if the state transition was successful, False otherwise.
        """
        payment_processor = get_instance(transaction.payment_processor)

        if not payment_processor == self:
            return False

        transId = str(transaction.data.get('authorizenet_id'))

        req = apicontractsv1.transactionRequestType()
        req.transactionType = "voidTransaction"
        req.refTransId = transId

        t_req                        = apicontractsv1.createTransactionRequest()
        t_req.merchantAuthentication = self.merchantAuth
        t_req.refId                  = self.merchantId

        t_req.transactionRequest = req

        controller = createTransactionController(t_req)

        try:
            controller.execute()
        except Exception as e:
            logger.warning(
                'Error executing request to void transaction %s', {
                    'transaction_id': transId,
                    'exception': str(e)
                }
            )

        response = controller.getresponse()

        have_resp = response is not None

        if have_resp:
            status, resp_ok = self._get_authorizenet_transaction_status(response)

            return self._transition_silver_transaction_to(transaction,
                                                          response,
                                                          status,
                                                          transaction.States.Canceled)
        else:
            logger.warning(
                'Couldn\'t void transaction %s', {
                    'transaction_id': transId,
                    'messages': response.messages.message[0]['text'].text
                }
            )
            return False

    def execute_transaction(self, transaction, charge_profile=False):
        """
        :param transaction: A Silver transaction with a AuthorizeNet payment method, in Initial state.
        :return: True if the transaction was successfully sent to processing, False otherwise.
        """

        payment_processor = get_instance(transaction.payment_processor)

        if not payment_processor == self:
            return False

        if transaction.state != transaction.States.Pending:
            return False

        return self._charge_transaction(transaction, charge_profile=charge_profile)

    def recover_lost_transaction_id(self, transaction):
        """
        :param transaction: A Silver transaction with a AuthorizeNet payment method.
        :return: True if the transaction ID was recovered, False otherwise.
        """

        raise NotImplementedError

    def fetch_transaction_status(self, transaction):
        """
        Query payment processor for a transaction, and update the status
        of the silver transaction accordingly.

        :param transaction: A Silver transaction with a AuthorizeNet payment method, in Pending state.
        :return: True if the transaction status was updated, False otherwise.
        """

        logger.info("transaction data: %s", transaction.data)

        payment_processor = get_instance(transaction.payment_processor)

        if not payment_processor == self:
            return False

        if transaction.state != transaction.States.Pending:
            return False

        tx_id = transaction.data.get('authorizenet_id')

        logger.info('tx id %s', {'tx_id': tx_id})

        if not self.test_transaction_id_valid(tx_id):
            logger.warning(
                'Transaction id %s is invalid. API does not support recovering lost transactions, will need to be manually entered.', {
                    'authorizenet_id': tx_id,
                }
            )

            return False

        req                        = apicontractsv1.getTransactionDetailsRequest()
        req.merchantAuthentication = self.merchantAuth
        req.transId                = str(transaction.data.get('authorizenet_id'))

        status = transaction.data.get('status')

        transaction_controller = getTransactionDetailsController(req)

        try:
            transaction_controller.execute()
        except Exception as e:
            logger.warning(
                'Error in request create transaction %s', {
                    'exception': str(e)
                }
            )

        response = transaction_controller.getresponse()

        have_resp = response is not None
        resp_okay = response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok

        if have_resp:
            t_resp = response.transaction
            t_resp_msgs = hasattr(t_resp, 'messages') is True

            if resp_okay:
                status = str( t_resp.responseCode )
            else:
                if t_resp_msgs:
                    status = response.messages.message[0]['code'].text

        transaction.data.update({
            'status': status,
        })
        transaction.save()

        return self._transition_silver_transaction_state(transaction, response, status)

class AuthorizeNetTriggered(AuthorizeNetTriggeredBase):
    def is_payment_method_recurring(self, payment_method):
        return False

class AuthorizeNetTriggeredRecurring(AuthorizeNetTriggeredBase):
    def is_payment_method_recurring(self, payment_method):
        return True
