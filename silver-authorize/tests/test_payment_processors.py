import pytest
from datetime import datetime
from mock import patch, MagicMock

from silver.models import Transaction
from silver.payment_processors import get_instance

from silver_authorizenet.models.customer_data import CustomerData
from silver_authorizenet.payment_processors import (AuthorizeNetTriggered,
                                                 AuthorizeNetTriggeredRecurring)

from silver_authorizenet.tests.factories import (AuthorizeNetTransactionFactory,
                                                 AuthorizeNetPaymentMethodFactory,
                                                 InvoiceFactory,
                                                 EntryFactory,
                                                 AuthorizeNetRecurringPaymentMethodFactory)

from silver.tests.factories import TransactionFactory, CustomerFactory

import logging
logging.basicConfig(level=logging.INFO)


# TODO: implement these 
# https://github.com/silverapp/silver/blob/master/silver/tests/api/test_payment_method.py

class TestAuthorizeNetTransactions:
    # Authorize.net testing guide
    #   https://developer.authorize.net/hello_world/testing_guide/
    # 
    # Summary:
    # 
    # Card numbers exist for different brands.
    # Generating different card responses is via zip code.
    #  - 46282 - Declined. Resp code 2 
    # 
    # Generating different Address Verification Service responses
    # via zip code.
    #  - 46203 - Invalid or not allowed. AVS Status: E
    # 
    # Testing CVV responses via special CVVs.
    #  - 900 - Successful match. CVV Code: M
    #  - 901 - Does not match. CVV Code: N
    #
    # And much more...

    # AuthorizeNetTriggered._has_been_setup = True
    # AuthorizeNetTriggeredRecurring._has_been_setup = True

    def setup_method(self):

        customer            = MagicMock()
        customer.id         = 1
        customer.first_name = "Ellen"
        customer.last_name  = "Johnson"
        customer.company    = "Souveniropolis"
        customer.address    = "14 Main Street"
        customer.city       = "Pecan Springs"
        customer.state      = "TX"
        # customer.zip_code   = "44628"
        customer.country    = "USA"
        customer.email      = "bbq@omg.com"

        # TODO: putting this here for now. we will test silver and
        # strategize a little about the overall process. Thinking in the
        # interest of best practices, whatever frontend app we have can
        # collect this once, run it through the authorize.net backend to
        # create a customer profile + payment profile, we'll store those
        # and not need to store card numbers at all. 

        customer.meta = {
            "cardNumber": "4111111111111111",
            "expirationDate": "2020-12",
            "cardCode": "123",
        }

        transaction = MagicMock()
        transaction.amount = 25.00
        transaction.currency = "USD"
        # transaction.status = AuthorizeNetTransaction.Status.Initial
        # transaction.id = '1234'
        # transaction.processor_response_code = 1
        transaction.credit_card_details = customer.credit_card_details
        transaction.customer            = customer

        self.transaction = transaction
        self.customer    = customer

    def teardown_method(self):
        AuthorizeNetTriggered._has_been_setup = False
        AuthorizeNetTriggeredRecurring._has_been_setup = False

    @pytest.mark.django_db
    def test_process_create_customer_profile(self):
        customer      = CustomerFactory.create()
        customer.meta = self.customer.meta

        customer_data = CustomerData.objects.create(
            customer=customer, data={
                'id': '1235',
            }
        )

        payment_method = AuthorizeNetRecurringPaymentMethodFactory.create(
            payment_processor='AuthorizeNetTriggered',
            customer=customer,
        )

        transaction = AuthorizeNetTransactionFactory.create(
            state=Transaction.States.Initial,
            data={
                'id': '1235',
            },
            payment_method=payment_method
        )

        payment_processor = get_instance(transaction.payment_processor)
        resp = payment_processor.create_customer_profile(customer)

        assert resp == True
        tok = payment_processor.client_token(customer)

        customer_data = CustomerData.objects.get(customer=customer)

        assert tok == customer_data.get('payment_id')

    @pytest.mark.django_db
    def test_process_transaction_from_customer_profile(self):
        # TODO:
        return

        customer      = CustomerFactory.create()
        customer.meta = self.customer.meta

        customer_data = CustomerData.objects.create(
            customer=customer, data={
                'id': '1235',
            }
        )

        payment_method = AuthorizeNetRecurringPaymentMethodFactory.create(
            payment_processor='AuthorizeNetTriggered',
            customer=customer,
        )

        transaction = AuthorizeNetTransactionFactory.create(
            state=Transaction.States.Initial,
            data={
                'id': '1235',
            },
            payment_method=payment_method
        )

        payment_processor = get_instance(transaction.payment_processor)
        resp = payment_processor.execute_transaction(transaction, charge_profile=True)

        assert resp == True
        tok = payment_processor.client_token(customer)

        customer_data = CustomerData.objects.get(customer=customer)

        assert tok == customer_data.get('payment_id')


    @pytest.mark.django_db
    def test_process_transaction_with_credit_card(self):

        customer      = CustomerFactory.create()
        customer.meta = self.customer.meta

        payment_method = AuthorizeNetRecurringPaymentMethodFactory.create(
            payment_processor='AuthorizeNetTriggered',
            customer=customer
        )

        transaction = AuthorizeNetTransactionFactory.create(
            state=Transaction.States.Initial,
            data={
                'id': '1235',
                'status': None,
                'authorizenet_id': None,
            },
            payment_method=payment_method,
        )

        assert transaction.state == transaction.States.Initial

        payment_processor = get_instance(transaction.payment_processor)
        status = payment_processor.process_transaction(transaction)

        assert status == True
        assert transaction.state == transaction.States.Pending

    @pytest.mark.django_db
    def test_process_transaction_with_credit_card_is_success(self):

        customer      = CustomerFactory.create()
        customer.meta = self.customer.meta

        entry   = EntryFactory.create()
        invoice = InvoiceFactory.create(
            series          = "pytest",
            customer        = customer,
            invoice_entries = [entry],
            state           = 'issued',
        )

        payment_method = AuthorizeNetRecurringPaymentMethodFactory.create(
            payment_processor='AuthorizeNetTriggered',
            customer=customer
        )

        transaction = AuthorizeNetTransactionFactory.create(
            invoice=invoice,
            state=Transaction.States.Initial,
            data={
                'id': '1235',
                'status': None,
                'authorizenet_id': None,
            },
            payment_method=payment_method,
        )

        assert transaction.state == transaction.States.Initial

        payment_processor = get_instance(transaction.payment_processor)
        status = payment_processor.process_transaction(transaction)

        assert status == True
        assert transaction.state == transaction.States.Pending

        assert transaction.data.get('status') != 0
        # 0 implies the API sandbox is in test mode
        assert transaction.data.get('authorizenet_id') != 0

    @pytest.mark.django_db
    def test_process_transaction_update_status(self):

        customer      = CustomerFactory.create()
        customer.meta = self.customer.meta

        entry   = EntryFactory.create()
        invoice = InvoiceFactory.create(
            series          = "pytest",
            customer        = customer,
            invoice_entries = [entry],
            state           = 'issued',
        )

        payment_method = AuthorizeNetRecurringPaymentMethodFactory.create(
            payment_processor='AuthorizeNetTriggered',
            customer=customer
        )

        transaction = AuthorizeNetTransactionFactory.create(
            invoice=invoice,
            state=Transaction.States.Initial,
            data={
                'id': '1235',
                'status': None,
                'authorizenet_id': None,
            },
            payment_method=payment_method,
        )

        assert transaction.state == transaction.States.Initial

        payment_processor = get_instance(transaction.payment_processor)
        status = payment_processor.process_transaction(transaction)

        old_status = transaction.data.get('status')

        assert status == True
        assert transaction.state == transaction.States.Pending

        # assert transaction.data.get('status') != 0
        # 0 implies the API sandbox is in test mode
        assert transaction.data.get('authorizenet_id') != 0

        status = payment_processor.fetch_transaction_status(transaction)

        # transaction.States.Settled
        assert status == True
        assert old_status != transaction.data.get('status')
        assert transaction.data.get('authorizenet_id') != 0
        assert transaction.data.get('status') != 0

    ### @pytest.mark.django_db
    ### def test_void_transaction(self):
    ###     customer      = CustomerFactory.create()
    ###     customer.meta = self.customer.meta

    ###     entry   = EntryFactory.create()
    ###     invoice = InvoiceFactory.create(
    ###         series          = "pytest",
    ###         customer        = customer,
    ###         invoice_entries = [entry],
    ###         state           = 'issued',
    ###     )

    ###     payment_method = AuthorizeNetRecurringPaymentMethodFactory.create(
    ###         payment_processor='AuthorizeNetTriggered',
    ###         customer=customer
    ###     )

    ###     transaction = AuthorizeNetTransactionFactory.create(
    ###         invoice=invoice,
    ###         state=Transaction.States.Initial,
    ###         data={
    ###             'id': '1235',
    ###             'status': None,
    ###             'authorizenet_id': None,
    ###         },
    ###         payment_method=payment_method,
    ###     )

    ###     assert transaction.state == transaction.States.Initial

    ###     payment_processor = get_instance(transaction.payment_processor)
    ###     status = payment_processor.process_transaction(transaction)

    ###     old_status = transaction.data.get('status')

    ###     assert status == True
    ###     assert transaction.state == transaction.States.Pending

    ###     # assert transaction.data.get('status') != 0
    ###     # 0 implies the API sandbox is in test mode
    ###     assert transaction.data.get('authorizenet_id') != 0

    ###     status = payment_processor.void_transaction(transaction)

    ###     # transaction.States.Settled
    ###     assert status == True
    ###     # 1 - success, even though it's void apparently 
    ###     assert transaction.data.get('status') == 4
    ###     assert transaction.data.get('authorizenet_id') != 0
    ###     assert transaction.data.get('status') != 0

    @pytest.mark.django_db
    def test_refund_transaction(self):
        customer      = CustomerFactory.create()
        customer.meta = self.customer.meta

        entry   = EntryFactory.create()
        invoice = InvoiceFactory.create(
            series          = "pytest",
            customer        = customer,
            invoice_entries = [entry],
            state           = 'issued',
        )

        payment_method = AuthorizeNetRecurringPaymentMethodFactory.create(
            payment_processor='AuthorizeNetTriggered',
            customer=customer
        )

        transaction = AuthorizeNetTransactionFactory.create(
            invoice=invoice,
            state=Transaction.States.Initial,
            data={
                'id': '1235',
                'status': None,
                'authorizenet_id': None,
            },
            payment_method=payment_method,
        )

        assert transaction.state == transaction.States.Initial

        payment_processor = get_instance(transaction.payment_processor)
        status = payment_processor.process_transaction(transaction)

        old_status = transaction.data.get('status')

        assert status == True
        assert transaction.state == transaction.States.Pending

        # assert transaction.data.get('status') != 0
        # 0 implies the API sandbox is in test mode
        assert transaction.data.get('authorizenet_id') != 0

        status = payment_processor.refund_transaction(transaction)

        # transaction.States.Settled
        assert status == True
        # 1 - success, even though it's void apparently 
        assert transaction.data.get('status') == 1
        assert transaction.data.get('authorizenet_id') != 0
        assert transaction.data.get('status') != 0



    ###
    ### Tests for things that failed server-side
    ### 
    @pytest.mark.django_db
    def test_fetch_transaction_status_with_null_tx_id(self):

        customer      = CustomerFactory.create()
        customer.meta = self.customer.meta

        entry   = EntryFactory.create()
        invoice = InvoiceFactory.create(
            series          = "pytest",
            customer        = customer,
            invoice_entries = [entry],
            state           = 'issued',
        )

        payment_method = AuthorizeNetRecurringPaymentMethodFactory.create(
            payment_processor='AuthorizeNetTriggered',
            customer=customer
        )

        transaction = AuthorizeNetTransactionFactory.create(
            invoice=invoice,
            state=Transaction.States.Pending,
            data={
                'id': '1235',
                'status': None,
                'authorizenet_id': None,
            },
            payment_method=payment_method,
        )

        assert str(transaction.data.get('authorizenet_id')) == "None"

        payment_processor = get_instance(transaction.payment_processor)
        status = payment_processor.fetch_transaction_status(transaction)

        assert status == False
