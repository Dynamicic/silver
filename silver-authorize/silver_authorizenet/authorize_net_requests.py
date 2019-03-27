import logging
import authorizenet

from datetime import datetime, timedelta
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

from .authorize_net_exceptions import *

logger = logging.getLogger(__name__)

class AuthorizeNetRequestHelpers(object):
    """ Helper functions for constructing transaction requests to
    Authorize.net. """

    # NOTES: for more information on response codes:
    #   https://developer.authorize.net/api/reference/index.html
    #   https://developer.authorize.net/api/reference/responseCodes.html
    #   https://developer.authorize.net/api/reference/dist/json/responseCodes.json

    # 1 -- Approved
    # 2 -- Declined
    # 3 -- Error
    # 4 -- Held for Review

    failed_statuses = [
        '2',
        '3',
        # - Held for Review - should be pending '4', # TODO: this might be a 'pending' status instead
        # '5',
        '54',
    ]

    void_statuses = [
        '234',
        '310',
    ]

    settled_statuses = [
        '1',
        '304',
        '327',
        '50',
    ]

    @property
    def merchantAuth(self):
        conf = settings.PAYMENT_PROCESSORS.get('AuthorizeNetTriggered').get('setup_data')

        # Create a merchantAuthenticationType object with authentication
        # details retrieved from the constants file
        _merchantAuth = apicontractsv1.merchantAuthenticationType()
        _merchantAuth.name = conf.get('api_login')
        _merchantAuth.transactionKey = conf.get('transaction_key')

        return _merchantAuth

    def _create_credit_card(self, customer):
        """ Create a Credit Card element that can be applied to an
        Authorize.net Transaction Request.

        :param customer: A silver customer.
        :returns apicontractsv1.creditCardType instance:
        """

        cc                = apicontractsv1.creditCardType()
        cc.cardNumber     = customer.meta.get('cardNumber')
        cc.expirationDate = customer.meta.get('expirationDate')
        cc.cardCode       = customer.meta.get('cardCode')

        return cc

    def _create_bill_to(self, customer):
        """ Create a Bill To element that can be applied to an
        Authorize.net Transaction Request.

        :param customer: A silver customer.
        :returns apicontractsv1.customerAddressType instance:
        """
        billTo           = apicontractsv1.customerAddressType()

        billTo.firstName = customer.first_name
        billTo.lastName  = customer.last_name
        billTo.company   = customer.company
        billTo.address   = customer.address_1
        billTo.city      = customer.city
        billTo.state     = customer.state
        billTo.zip       = customer.zip_code
        billTo.country   = customer.country

        return billTo

    def _create_transaction_settings(self):
        """ Create transaction settings for an Authorize.net request.
        """

        # Ensure that no duplicate transaction can be submitted for 600
        # seconds.

        duplicateWindowSetting              = apicontractsv1.settingType()
        duplicateWindowSetting.settingName  = "duplicateWindow"
        duplicateWindowSetting.settingValue = "600"

        settings = apicontractsv1.ArrayOfSetting()
        settings.setting.append(duplicateWindowSetting)

        return settings

class AuthorizeNetRequests(AuthorizeNetRequestHelpers):
    """ Methods for interacting with Authorize.net """

    def test_transaction_id_valid(self, transaction_id):
        """ Validate that a Transaction ID is not missing. There will be more cases than this

        :param transaction_id: An authorize.net transaction id string
        :return True if valid, False otherwise:

        """
        if str(transaction_id) == "None" or transaction_id is None:
            return False
        else:
            return True

    def _create_customer_profile(self, customer, customer_data):
        """ Run a request to create a customer profile with
        Authorize.Net, from customer data including credit card info.

        :param customer: A Silver customer instance
        :param customer_data: A CustomerData instance
        :returns True if successful, False if otherwise:
        """
        customer_id = customer_data.get('id')

        ## Create a customer profile

        createCustomerProfile = apicontractsv1.createCustomerProfileRequest()
        createCustomerProfile.merchantAuthentication = self.merchantAuth
        createCustomerProfile.profile = apicontractsv1.customerProfileType(
            customer_id,
            customer.last_name + ' ' + customer.first_name,
            customer.email
        )

        controller = createCustomerProfileController(createCustomerProfile)

        try:
            controller.execute()
        except Exception as e:
            logger.warning(
                'Error in request to create Authorize.net customer profile %s', {
                    'customer_id': customer_id,
                    'exception': str(e)
                }
            )

        profile_response = controller.getresponse()

        if (profile_response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok):
            return self._update_customer(
                customer,
                {'id': customer_id,
                 'profile_id': str(profile_response.customerProfileId)}
            )
        else:
            logger.warning(
                'Couldn\'t create Authorize.net customer profile %s', {
                    'customer_id': customer_id,
                    'messages': profile_response.messages.message[0]['text'].text
                }
            )

        return False

    def _create_customer_payment_profile(self, customer, customer_data):
        """ Run a request to create a customer payment profile with
        Authorize.Net, from customer data including credit card info.

        :param customer: A Silver customer instance
        :param customer_data: A CustomerData instance
        :returns True if successful, False if otherwise:
        """

        customer_id                 = customer_data.get('id')
        customer_profile_id         = customer_data.get('profile_id')

        if customer_profile_id is None:
            logger.warning(
                'Couldn\'t create Authorize.net customer payment profile %s, customer profile does not exist', {
                    'customer_id': customer_id,
                }
            )
            return False

        payment            = apicontractsv1.paymentType()
        payment.creditCard = self._create_credit_card(customer)

        profile         = apicontractsv1.customerPaymentProfileType()
        profile.payment = payment
        profile.billTo  = self._create_bill_to(customer)

        createCustomerPaymentProfile                        = apicontractsv1.createCustomerPaymentProfileRequest()
        createCustomerPaymentProfile.merchantAuthentication = self.merchantAuth
        createCustomerPaymentProfile.paymentProfile         = profile
        createCustomerPaymentProfile.customerProfileId      = str(customer_profile_id)

        controller = createCustomerPaymentProfileController(createCustomerPaymentProfile)

        try:
            controller.execute()
        except Exception as e:
            logger.warning(
                'Error in request to create Authorize.net customer payment profile %s', {
                    'customer_id': customer_id,
                    'exception': str(e)
                }
            )

        response = controller.getresponse()

        if response is None:
            logger.warning(
                'No response returned', {
                    'customer_id': customer_id,
                    'messages': response.messages.message[0]['text'].text
                }
            )
            return False

        if (response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok):
            return self._update_customer(
                customer,
                {'id': customer_id,
                 'payment_id': str(response.customerPaymentProfileId)}
            )
        else:
            logger.warning(
                'Couldn\'t create Authorize.net customer profile %s', {
                    'customer_id': customer_id,
                    'messages': response.messages.message[0]['text'].text
                }
            )

        return False

    def _update_payment_method(self, payment_method, result_details,
                               instrument_type):
        """
        :param payment_method: A AuthorizeNetPaymentMethod.
        :param result_details: A (part of) authorizenet result(response)
                               containing payment method information.
        :param instrument_type: The type of the instrument (payment method);
                                see AuthorizeNetPaymentMethod.Types.
        :description: Updates a given payment method's data with data from a
                      authorizenet result payment method.
        """
        raise NotImplementedError

    def _transition_silver_transaction_state(self, transaction, resp, status):
        """ Transition the silver transaction's state with the
        transaction response status.

        :param transaction: A silver Transaction object
        :param status: A string representing the authorize.net transaction response status code.
        :returns True if the state transition was successful, False otherwise.
        """

        target_state = None

        if status in self.failed_statuses:
            target_state = transaction.States.Failed
            if transaction.state != target_state:
                logger.info("failed_status found: %s" % {'transaction': transaction, 'status': status, 'current_state': transaction.state})
                # wrong transaction obj, need response from auth.net
                fail_code = self._get_silver_fail_code(resp)
                fail_reason, status_ok = self._get_authorizenet_transaction_status(resp)
                transaction.fail(fail_code=fail_code, fail_reason=fail_reason)
                transaction.save()
                return False

        elif status == self.void_statuses:
            target_state = transaction.States.Canceled
            if transaction.state != target_state:
                transaction.cancel()
                transaction.save()
                return False

        elif status in self.settled_statuses:
            target_state = transaction.States.Settled
            if transaction.state != target_state:
                transaction.settle()
                transaction.save()
                return True
        else:
            return True

    def _transition_silver_transaction_to(self, transaction, resp, status,
                                          success):
        """ Transition the silver transaction's state with the
        transaction response status with a suggested success status.
        E.g. a successful void == 1, a successful transaction == 1, and
        a successful refund == 1, which does not map on a 1:1 basis to
        silver transaction transitions.

        :param transaction: A silver Transaction object
        :param status: A string representing the authorize.net transaction response status code.
        :param success: A Transaction State representing what the Authorize.net "success" code (1) means
        :returns True if the state transition was successful, False otherwise.
        """

        target_state = None
        res = self._transition_silver_transaction_state(transaction, resp, status)

        if res == True:
            if success == transaction.States.Refunded:
                transaction.refund()

            if success == transaction.States.Canceled:
                transaction.cancel()

            return True

        return res

    def _update_silver_transaction_status(self, transaction, result_transaction):
        """
        :param transaction: A Silver transaction with a AuthorizeNet payment method.
        :param result_transaction: A transaction from an authorizenet
                                   result(response).
        :description: Updates a given transaction's data with data from a
                      authorizenet result payment method.
        :returns True if the state transition was successful, False otherwise.
        """

        if not transaction.data:
            transaction.data = {}

        have_resp = result_transaction is not None
        resp_okay = result_transaction.messages.resultCode == apicontractsv1.messageTypeEnum.Ok

        auth_id = None
        status = "Null response."

        # NOTES: 
        #   https://developer.authorize.net/api/reference/index.html
        #   https://developer.authorize.net/api/reference/responseCodes.html
        #
        #   https://developer.authorize.net/api/reference/dist/json/responseCodes.json

        if have_resp:
            t_resp = result_transaction.transactionResponse

            if resp_okay:
                t_resp_msgs = hasattr(t_resp, 'messages') is True

                if t_resp_msgs:
                    transaction.external_reference = t_resp.transId
                    logger.info("Got status %s", {'responseCode': t_resp.responseCode})
                    logger.info("Got transaction id %s", {'transId': t_resp.transId})
                    logger.info("Got ref transaction id %s", {'transId': t_resp.refTransID})
                    auth_id = t_resp.transId
                    status = str(t_resp.responseCode)
                    # note there are also:
                    # avsResultCode
                    # cvvResultCode
                    # cavvResultCode
                    logger.info("messages: %s" % {
                        'desc': t_resp.messages.message[0].description,
                        'msg': t_resp.messages.message[0].code,
                    })
                else:
                    status = str(t_resp.errors.error[0].errorCode)
                    logger.info("errors: %s" % {
                        'err': t_resp.errors
                    })
            # Response returned is an error
            else:
                if result_transaction.messages.resultCode == 'Error':
                    result_msg = result_transaction.messages.message[0].code
                    result_txt = result_transaction.messages.message[0].text

                    status =  False
                    try:
                        status = str(t_resp.errors.error[0].errorCode) + \
                                ": " + \
                                 str(t_resp.errors.error[0].errorText)
                    except:
                        pass

                    if result_msg == 'E00007':
                        raise AuthNetInvalidCreds
                    else:
                        raise AuthNetException(str(result_msg) + ": " + str(status or result_txt))
                else:
                    raise Exception("Unknown error")

        transaction.data.update({
            'status': status,
            'authorizenet_id': str(auth_id),
        })
        try:
            transaction.save()
        except Exception as e:
            logger.warning("Could not save transaction data %s", transaction.data)
            raise e

        return self._transition_silver_transaction_state(transaction, result_transaction, status)

    def _update_customer(self, customer, result_details):
        """ :param result_details.id:
            :param result_details.profile_id:
            :param result_details.payment_id:
            :return customer_data:
        """
        customer_data = CustomerData.objects.get_or_create(customer=customer)[0]
        if 'id' not in customer_data:
            customer_data['id'] = result_details.id
            customer_data.save()
        if 'profile_id' not in customer_data and 'profile_id' in result_details:
            customer_data['profile_id'] = result_details['profile_id']
            customer_data.save()
        if 'payment_id' not in customer_data and 'payment_id' in result_details:
            customer_data['payment_id'] = result_details['payment_id']
            customer_data.save()
        return customer_data

    def _get_authorizenet_transaction_status(self, response):
        """ TODO: doc
        """

        # TODO: is there any need to return cavv, avs or cvv codes too?
        have_resp = response is not None
        resp_okay = response.messages.resultCode == apicontractsv1.messageTypeEnum.Ok

        if have_resp:

            t_resp = response.transactionResponse

            if resp_okay:
                t_resp_msgs = hasattr(response, 'messages') is True
                if t_resp_msgs:
                    status = str(t_resp.responseCode)
                    resptext = t_resp.messages.message[0].description
                    # logger.info("code: %s - %s", status, resptext)
                else:
                    status = str(t_resp.errors.error[0].errorCode)
                    # logger.info("code: %s - %s", status, t_resp.errors.error[0].errorText)
            else:
                status = str(t_resp.errors.error[0].errorCode)
                # logger.info("code: %s - %s", status, t_resp.errors.error[0].errorText)

        return status, resp_okay

    def _get_silver_fail_code(self, result_transaction):
        """ Convert a transaction result into a silver-internal fail
        code.

        :param result_transaction: A Silver transaction response
        :return: A string representing the silver transaction type
        """
        t_resp = result_transaction.transactionResponse

        authorizenet_fail_code, status_ok = self._get_authorizenet_transaction_status(
            result_transaction)

        if not authorizenet_fail_code:
            return 'default'

        try:
            authorizenet_fail_code = int(authorizenet_fail_code)
        except (TypeError, ValueError):
            return 'default'

        TODO = "zomg"

        # Map codes to these
        if authorizenet_fail_code in [TODO]:
            return 'insufficient_funds'
        elif authorizenet_fail_code in [TODO]:
            return 'expired_payment_method'
        elif authorizenet_fail_code in [TODO]:
            return 'expired_card'
        elif authorizenet_fail_code in [TODO]:
            return 'invalid_payment_method'
        elif authorizenet_fail_code in [TODO]:
            return 'invalid_card'
        elif authorizenet_fail_code in [TODO]:
            return 'limit_exceeded'
        elif authorizenet_fail_code in [TODO]:
            return 'transaction_declined_by_bank'
        elif authorizenet_fail_code in [TODO]:
            return 'transaction_hard_declined'
        elif authorizenet_fail_code in [TODO]:
            return 'transaction_hard_declined_by_bank'

        # TODO: remove
        logger.info("Mapping authnet to silver: %s", authorizenet_fail_code)

        return 'default'

    def _create_transaction_request_for_profile(self, transaction,
                                                customer_profile,
                                                payment_profile):

        """ Create an authorize.net transaction request object to a
        customer id

        :param transaction: A Silver transaction with a AuthorizeNet payment method.
        :param customer_profile: The authorize.net customer profile ID
        :param payment_profile: The authorize.net customer payment profile ID
        :return: An authorize.net TransactionRequest

        """

        profile_to_charge                                 = apicontractsv1.customerProfilePaymentType()
        profile_to_charge.customerProfileId               = customer_profile
        profile_to_charge.paymentProfile                  = apicontractsv1.paymentProfile()
        profile_to_charge.paymentProfile.paymentProfileId = payment_profile

        payment            = apicontractsv1.paymentType()
        payment.profile    = profile_to_charge

        # Create order information
        order               = apicontractsv1.orderType()
        order.invoiceNumber = transaction.document.series
        order.description   = "\n".join(map(str, transaction.document.entries))

        # Set the customer's identifying information
        customerData       = apicontractsv1.customerDataType()
        customerData.type  = "individual"
        customerData.id    = transaction.customer.id # TODO: right id field?
        customerData.email = transaction.customer.email

        settings = self._create_transaction_settings()

        _tx_request                     = apicontractsv1.transactionRequestType()
        _tx_request.transactionType     = "authCaptureTransaction"
        _tx_request.amount              = transaction.amount
        _tx_request.payment             = payment
        _tx_request.order               = order
        # _tx_request.billTo              = customerAddress
        _tx_request.customer            = customerData
        _tx_request.transactionSettings = settings
        # _tx_request.lineItems         = line_items

        _request = apicontractsv1.createTransactionRequest()
        _request.merchantAuthentication = self.merchantAuth

        _request.refId = self.merchantId
        _request.transactionRequest = _tx_request

        return _request

    def _create_transaction_request(self, transaction):
        """ Create an authorize.net transaction request object from
        whatever silver is passing over.

        :param transaction: A Silver transaction with a AuthorizeNet payment method.
        :return: An authorize.net TransactionRequest

        """
        logger.info("creating transaction request")

        payment            = apicontractsv1.paymentType()
        payment.creditCard = self._create_credit_card(transaction.payment_method.customer)

        # Create order information
        order               = apicontractsv1.orderType()
        order.invoiceNumber = transaction.document.series
        if len(transaction.document.entries) > 0:
            dsc = "\n".join(map(str, transaction.document.entries))
        else:
            dsc = ""
        if len(dsc) > 40:
            dsc = dsc[0:40]
        order.description   = dsc

        # Set the customer's identifying information
        customerData       = apicontractsv1.customerDataType()
        customerData.type  = "individual"
        customerData.id    = str(transaction.customer.id)
        customerData.email = transaction.customer.email

        settings = self._create_transaction_settings()

        _tx_request                     = apicontractsv1.transactionRequestType()
        _tx_request.transactionType     = "authCaptureTransaction"
        _tx_request.amount              = transaction.amount
        _tx_request.payment             = payment
        _tx_request.order               = order
        _tx_request.billTo              = self._create_bill_to(transaction.customer)
        _tx_request.customer            = customerData
        _tx_request.transactionSettings = settings

        _request = apicontractsv1.createTransactionRequest()
        _request.merchantAuthentication = self.merchantAuth

        _request.refId = self.merchantId
        _request.transactionRequest = _tx_request

        return _request

    def _charge_transaction(self, transaction, charge_profile=False):
        """

        :param transaction: The Silver transaction to be charged. Must have a usable AuthorizeNet
                            payment_method.
        :return: True on success, False on failure.
        """

        payment_method = transaction.payment_method

        if payment_method.canceled:
            try:
                transaction.fail(fail_reason='Payment method was canceled.')
                transaction.save()
            finally:
                return False

        # Create a transactionRequestType object and add the previous objects to it.
        # TODO: customerdata for everything
        if charge_profile:
            logger.info("Charging to profile")

            try:
                customer_data = CustomerData.objects.get(customer=transaction.customer)
            except CustomerData.DoesNotExist:
                created = create_customer_profile(transaction.customer)
                if created:
                    logger.info("Created new profile")
            finally:
                customer_data = CustomerData.objects.get(customer=transaction.customer)

            logger.info("Creating request")

            t_reqs = self._create_transaction_request_for_profile(
                transaction,
                customer_data.get('profile_id'),
                customer_data.get('payment_id')
            )
        else:
            logger.info("Charging card")
            t_reqs = self._create_transaction_request(transaction)

        # Create the transaction controller
        transaction_controller = createTransactionController(t_reqs)

        # Set the environment
        transaction_controller.setenvironment(self.environment)

        # Execute the transaction request
        try:
            transaction_controller.execute()
        except Exception as e:
            logger.info(
                'Error in request create transaction %s', {
                    'exception': str(e)
                }
            )

        response = transaction_controller.getresponse()

        try:
            return self._update_silver_transaction_status(transaction,
                                                   response)
        except TransitionNotAllowed:
            # TODO: handle this
            return False



