# Test processes

The intent of this document is to list the minimal steps to initiate
server-side processes to test integrations from the client side. Using this
document, you should be able to get a payment plan processing and issuing
invoices as well as issue payments to the payment processor, and much more.

* [Swagger](#swagger)
* [Creating an Auth Token](#creating-an-auth-token)
* [Authenticating](#authenticating)
* [Triggering a payment to process](#triggering-a-payment-to-process)
   * [Create a Customer](#create-a-customer)
   * [Create a Customer Payment Method](#create-a-customer-payment-method)
   * [Create an invoice provider](#create-an-invoice-provider)
   * [Create a (draft) Invoice](#create-a-draft-invoice)
   * [Set the invoice to Issued](#set-the-invoice-to-issued)
   * [Get the invoice PDF](#get-the-invoice-pdf)
   * [Run the payment process](#run-the-payment-process)
* [Creating and subscribing to plans](#creating-and-subscribing-to-plans)
   * [Create some product codes](#create-some-product-codes)
   * [Create a Plan](#create-a-plan)
   * [Subscribing a customer to the plan](#subscribing-a-customer-to-the-plan)
   * [Activating the customer's plan](#activating-the-customers-plan)
   * [Logging metered feature usage](#logging-metered-feature-usage)
* [Logging a manual transaction](#logging-a-manual-transaction)
   * [Create a new customer](#create-a-new-customer)
   * [Add a manual payment method](#add-a-manual-payment-method)
   * [create manual payment invoice](#create-manual-payment-invoice)
   * [set invoice to issued](#set-invoice-to-issued)
   * [list customer manual payment methods](#list-customer-manual-payment-methods)
   * [list all customer transactions](#list-all-customer-transactions)
      * [List customer manual transactions](#list-customer-manual-transactions)
   * [cancel auto-issued manual initial transaction](#cancel-auto-issued-manual-initial-transaction)
   * [add a manual transaction](#add-a-manual-transaction)
   * [set the transaction state to settled](#set-the-transaction-state-to-settled)
   * [Get the invoice to check the status.](#get-the-invoice-to-check-the-status)
* [One-off Transactions](#one-off-transactions)
* [Testing that failed transactions can automatically be recreated](#testing-that-failed-transactions-can-automatically-be-recreated)
   * [Creating an invoice and payment.](#creating-an-invoice-and-payment)
   * [Failing the transaction](#failing-the-transaction)
   * [Running the server process](#running-the-server-process)
* [Creating a manual payment, and testing overpayment correction.](#creating-a-manual-payment-and-testing-overpayment-correction)
   * [Create an invoice for an amount](#create-an-invoice-for-an-amount)
   * [Issue a payment for way more than the amount](#issue-a-payment-for-way-more-than-the-amount)
   * [Observe the customer balance](#observe-the-customer-balance)
   * [Run the management command](#run-the-management-command)
   * [Check customer invoices](#check-customer-invoices)
* [Creating a subscription, and suspending it on failed payment.](#creating-a-subscription-and-suspending-it-on-failed-payment)
* [Django Admin](#django-admin)
   * [Hooks](#hooks)
   * [Revision history](#revision-history)
   * [Management tasks](#management-tasks)
* [TODO](#todo)

## See also

**README.md**

 * Webhook config

## Swagger

`Django REST Swagger` is installed, and the UI is accessible at the following URL.

 * http://hostname/swagger/

A separate JSON Schema URL is also available.

 * http://hostname/swagger/schema/

## Creating an Auth Token

For now the application uses basic token authentication. In order to create or
retrieve a token, log in to the Django admin interface, click on Tokens, and
add or copy an existing token.

## Authenticating

Authenticated views require an `Authorization` header of the following
structure:

    Authorization: Token YOUR_TOKEN_HERE


## Triggering a payment to process

This is a precise process that relies on API requests, and automatic
server-side processes.

### Create a Customer

Send the following request, noting the customer ID returned:

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "customer_reference": "bbqasddf",
        "first_name": "Bbq",
        "last_name": "Asdf",
        "company": "Some Jumbo Company",
        "email": "asdf@bbq.com",
        "address_1": "1234 Mulberry Lane",
        "address_2": "",
        "city": "Nantucket",
        "state": "Hawaii",
        "zip_code": "41414",
        "country": "US",
        "currency": "USD",
        "phone": "",
        "extra": "",
        "sales_tax_number": "",
        "sales_tax_name": "",
        "sales_tax_percent": null,
        "consolidated_billing": false,
        "meta": {
            "cardNumber": "4111111111111111",
            "cardCode": "123",
            "expirationDate": "2020-12"
        }
    }'

### Create a Customer Payment Method

Send the following request, substituting `CUSTOMER_ID` with the new customer id.

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/CUSTOMER_ID/payment_methods/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "payment_processor_name": "manual",
        "verified": true,
        "canceled": false,
        "valid_until": "2019-10-12T21:33:56.145656Z",
	    "display_info": "testing",
	    "data": {
		    "attempt_retries_after": 2,
		    "stop_retry_attempts": 5
	    }
    }'

Note, for the purposes of this test document, we're creating a `manual` payment
type. `authorizenet_triggered` is also available.

### Create an invoice provider

Create an invoice provider with the following request, and note the ID
returned.

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/providers/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "name": "Billing Provider",
        "company": "Jumbo Company",
        "invoice_series": "BPInvoiceSeries",
        "flow": "invoice",
        "email": "",
        "address_1": "1 Mulberry Lane",
        "address_2": "",
        "city": "Pacoima",
        "state": "CA",
        "zip_code": "",
        "country": "US",
        "invoice_starting_number": 1
      }'

### Create a (draft) Invoice

This is a little wonky for now, because it relies on Django REST API's
`CustomerUrl` serializer, so you will need to create URLs to related objects
instead of simply referencing the object's id.

Create the invoice with the following request and note the invoice id.

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/invoices/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
            "series": "InvoiceSeriesB",
            "provider": "http://$HOSTNAME/silver/providers/$PROVIDER_ID/",
            "customer": "http://$HOSTNAME/silver/customers/$CUSTOMER_ID/",
            "due_date": "2019-03-01",
            "issue_date": "2019-02-15",
            "paid_date": null,
            "cancel_date": null,
            "sales_tax_name": "sales tax",
            "sales_tax_percent": "0.05",
            "currency": "USD",
            "transaction_currency": "USD",
            "transaction_xe_rate": "1.0000",
            "transaction_xe_date": "2019-01-15",
            "state": "draft",
            "proforma": null,
            "invoice_entries": [
                {
                    "description": "Charcoal Latte",
                    "unit": "Cup",
                    "unit_price": "25.0000",
                    "quantity": "2.0000",
                    "total_before_tax": 50.0,
                    "start_date": null,
                    "end_date": null,
                    "prorated": false,
                    "product_code": null
                }
            ]
        }'

### Set the invoice to Issued

Issuing the invoice will automatically create a Payment object associated with
the Invoice and Customer.

    curl --request PUT \
      --url http://dev.billing.dynamicic.com/silver/invoices/$INVOICE_ID/state/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
          "state": "issued"
      }'

### Get the invoice PDF

The PDF generation process runs every minute on the test server, so after the
invoice has been issued, the document should be available with the following:

    curl --request GET \
      --url http://dev.billing.dynamicic.com/silver/invoices/$INVOICE_ID.pdf

This will redirect to the appropriate path. For now, the `pdf_url` attribute
returned from Invoice GET requests is incorrect.

If you need to force the document generation process to run, run the following
management command:

    $ python silverintegration/manage.py generate_pdfs

### Run the payment process

This should be running on a [ celery task ][celery], but for now:

1. Log into the server
2. Activate the virtual environment
3. run `./manage.py execute_transactions` (unless celery is set up for this)

  [celery]: https://github.com/silverapp/silver/blob/0009ff4ca52dfc711e2f160ad90b449060fc4007/settings.py


## Creating and subscribing to plans

This assumes the following steps above have been completed:

 - Creating a Customer
 - Creating a Customer Payment Plan
 - Creating an Invoice Provider

It will require some new objects too. Note that the Plan object defines an
interval to re-evaluate the billing total, so a Plan could function in a very
general way: $1/day, for 30 days: totalling up to $30 at the end of the period.

The Plan could also have metered services associated with it, and there are
endpoints to log incremental changes to metered feature usage (via
Subscriptions). These usage stats will be totalled up to the billing amount.

Subscriptions to each Plan must be created for each customer, and are the
vehicle through which invoices are generated automatically, and through which
automatic plan-based transactions are generated.

### Create some product codes

Run the following, noting the product codes.

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/product-codes/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "value": "charcoal-latte"
    }'

### Create a Plan

Note: this needs to include metered features

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/plans/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "name": "Monthly billing",
        "interval": "day",
        "interval_count": 30,
        "amount": "25.0000",
        "currency": "USD",
        "trial_period_days": 15,
        "generate_after": 0,
        "enabled": true,
        "private": false,
        "product_code": "$PRODUCT_CODE",
        "metered_features": [
            {
                "name": "Basic-Services-metering",
                "unit": "Thing",
                "price_per_unit": "5.0000",
                "included_units": "1.0000",
                "product_code": "basic-services"
            }
        ],
        "provider": "http://dev.billing.dynamicic.com/silver/providers/$PROVIDER_ID/"

### Subscribing a customer to the plan

With the plan ID from the last request to create the plan, send the following:

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/10/subscriptions/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
	    "customer": "http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/",
	    "plan": "http://dev.billing.dynamicic.com/silver/plans/$PLAN_ID/",
	    "start_date": "2019-02-03"
    }'
    

### Activating the customer's plan

Send the following request:

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/subscriptions/$PLAN_ID/activate/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

Note that you can also send to 

 * `$CUSTOMER_ID/subscriptions/$PLAN_ID/cancel/`
   - include a `when` argument in the JSON body.
 * `$CUSTOMER_ID/subscriptions/$PLAN_ID/reactivate/`


### Logging metered feature usage

To log metered feature usage, send a PATCH request like the following. Note
that two `update_type` settings are possible, `absolute` and `relative`.
`absolute` will replace the count with the new value, `relative` will sum the
existing value and the new value, negative values are supported.

    curl --request PATCH \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/subscriptions/$PLAN_ID/metered-features/$PRODUCT_CODE_SLUG/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
	    "date": "2019-02-03",
	    "count": 3,
	    "update_type": "relative"
    }'

## Logging a manual transaction

This is a multi-step process. NB: there could be issues with one customer
having multiple payment methods. If the customer has a manual method and an
authorize.net method with a card on file, setting the invoice to 'issued' will
create multiple new transactions, and a card will be billed automatically if
one is on file.

### Create a new customer

Send the following request. Note the ID returned.

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "first_name": "Manual",
        "last_name": "Payments",
        "company": "Some Jumbo Company",
        "email": "asdf@bbq.com",
        "address_1": "23192 Manchester Rd",
        "city": "Lake Winnipesaukee",
        "state": "New Hampshire",
        "zip_code": "41414",
        "country": "US",
        "currency": "USD",
        "meta": {}
    }'

### Add a manual payment method

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/payment_methods/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "payment_processor_name": "manual",
        "verified": true,
        "canceled": false,
        "valid_until": "2019-10-12T21:33:56.145656Z",
        "display_info": "manual payment method"
    }'

### create manual payment invoice

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/invoices/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '    {
            "series": "InvoiceSeriesB",
            "provider": "http://dev.billing.dynamicic.com/silver/providers/$YOUR_PROVIDER_ID/",
            "customer": "http://dev.billing.dynamicic.com/silver/customers/$YOUR_CUSTOMER_ID/",
            "due_date": "2019-02-01",
            "issue_date": "2019-01-15",
            "paid_date": null,
            "cancel_date": null,
            "sales_tax_name": "sales tax",
            "sales_tax_percent": "0.05",
            "currency": "USD",
            "transaction_currency": "USD",
            "transaction_xe_rate": "1.0000",
            "transaction_xe_date": "2019-01-15",
            "state": "draft",
            "proforma": null,
            "total": 50.12,
            "total_in_transaction_currency": 50.12,
            "pdf_url": null,
            "invoice_entries": [
                {
                    "description": "Charcoal Latte",
                    "unit": "Cup",
                    "unit_price": "25.0000",
                    "quantity": "2.0000",
                    "total_before_tax": 50.0,
                    "start_date": null,
                    "end_date": null,
                    "prorated": false,
                    "product_code": null
                }
            ]
        }'

### set invoice to issued

Issuing the invoice will automatically create a Payment object associated with
the Invoice and Customer.

    curl --request PUT \
      --url http://dev.billing.dynamicic.com/silver/invoices/$INVOICE_ID/state/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
          "state": "issued"
      }'

### list customer manual payment methods

Note the URL attribute in the response, because you may need to generate or
return this for future requests.

    curl --request GET \
      --url 'http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/payment_methods/?payment_processor_name=manual' \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

### list all customer transactions

    curl --request GET \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/transactions/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

#### List customer manual transactions

    curl --request GET \
      --url 'http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/transactions/?state=initial&payment_processor=manual' \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

### cancel auto-issued manual initial transaction

If the customer is paying manually by any amount other than the auto-issued
amount, we need to cancel this transaction, and create a new transaction for
less than that amount. This is because silver prevents over-paid invoices.

In this example, we will be cancelling this transaction, and recreating a new
one for the sake of example. Note, we could just as easily set the already
existing transaction to 'Settled' (i.e., a check was received, and cashed).

Note any GUIDs from the previous API calls for the transactions you need to
cancel, and send a request:

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/transactions/$TRANSACTION_GUID/cancel_request/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

### add a manual transaction

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/transactions/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "amount": 25.02,
        "currency": "USD",
        "proforma": null,
        "invoice": "http://dev.billing.dynamicic.com/silver/invoices/$INVOICE_ID/",
        "payment_method": "http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/payment_methods/$CUSTOMER_MANUAL_PAYMENT_ID/",
        "valid_until": null
    }'

### set the transaction state to settled

TODO: this endpoint isn't implemented yet, but this is what it will look like:

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/transactions/$TRANSACTION_GUID/settle_transaction/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

### Get the invoice to check the status.

If the payments total up to the invoice amount, the invoice will be
automatically marked as paid within silver.

    curl --request GET \
      --url http://dev.billing.dynamicic.com/silver/invoices/$INVOICE_ID/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'


## One-off Transactions

That previous section was a lot to get a transaction to go. If you don't need
to track the provider, invoice, customer, etc., you can create a one-off
transaction. 

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/transactions/one-off/ \
      --header 'content-type: application/json' \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --data '{
	    "payment_processor": "AuthorizeNetTriggered",
	    "customer": {
		    "first_name": "One off",
		    "last_name": "Test Customer",
		    "company": "Some Company Name",
		    "email": "asdf@bbq.com",
		    "address_1": "1234 Mulberry Lane",
		    "city": "Nantucket",
		    "state": "Hawaii",
		    "zip_code": "41414",
		    "country": "US",
		    "currency": "USD",
		    "meta": {
			    "cardNumber": "4111111111111111",
			    "cardCode": "123",
			    "expirationDate": "2020-12"
		    }
	    },
	    "invoice": {
		    "due_date": "2019-02-01",
		    "issue_date": "2019-01-15",
		    "sales_tax_name": "sales tax",
		    "sales_tax_percent": "0.05"
	    },
	    "entry": {
		    "description": "Charcoal Latte",
		    "unit": "Cup",
		    "unit_price": "25.0000",
		    "quantity": "2.0000",
		    "total_before_tax": "50.0"
	    },
	    "amount": 50.0
    }
    '

The response will return each of the created objects, but `transaction` is
probably what you're looking for.

## Testing that failed transactions can automatically be recreated

This is slightly harder to test outside of the test suites, unless you're
willing to wait a while, or log in and run a server process 

### Creating an invoice and payment.

Follow the process above in `Triggering a payment to process`, but do not
execute the transactions. Now, note the transaction ID and the customer ID for
the next step.

### Failing the transaction

Run the following transaction to fail the request manually.

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/transactions/$TRANSACITON_ID/fail_request/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

### Running the server process

Now, either wait for a few days, or log in to the server and issue the
following management command.

    $ python silverintegration/manage.py retry_failed_transactions \
        --document=$INVOICE_ID \
        --force YES

Checking the customer's transactions should result in a new transaction
appearing.

    curl --request GET \
      --url 'http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/transactions/?state=initial' \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

## Creating a manual payment, and testing overpayment correction.

This process is also difficult to test outside of test suites, unless you are
able to run management commands to substitute for automatically running celery
processes.

Note that this also covers partial payments; during this process you could
issue multiple payments for amounts less than the invoice total. A final
payment could be over the amount, and will trigger the same processes.

### Create an invoice for an amount

Follow the process in `Triggering a payment to process`.

### Issue a payment for way more than the amount

Note to set `overpayment` to `True`.

    curl --request POST \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/transactions/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json' \
      --data '{
        "amount": 9000.01,
        "currency": "USD",
        "overpayment": True,
        "proforma": null,
        "invoice": "http://dev.billing.dynamicic.com/silver/invoices/$INVOICE_ID/",
        "payment_method": "http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/payment_methods/$CUSTOMER_MANUAL_PAYMENT_ID/",
        "valid_until": null
    }'


### Observe the customer balance

Run the following request and observe the `$.balance` parameter.

    curl --request GET \
      --url http://dev.billing.dynamicic.com/silver/customers/$CUSTOMER_ID/ \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

### Run the management command

Now you can optionally issue an invoice to automatically correct for this. This
is also available as a celery task.

Run the following command.

    $ python silverintegration/manage.py check_overpayments \
        --customer=$CUSTOMER_ID

### Check customer invoices

Now check the customer's invoices to confirm that a new invoice has been
issued:

    curl --request GET \
      --url 'http://dev.billing.dynamicic.com/silver/invoices/?customer=$CUSTOMER_ID' \
      --header 'authorization: Token $YOUR_AUTH_TOKEN' \
      --header 'content-type: application/json'

## Creating a subscription, and suspending it on failed payment.

This is particularly tricky to test outside of test suites, where time can be
altered. We will need to come up with a plan here. Here's the overview:

- Create a plan, and subscribe a customer (with a payment method) to the plan
- Force the first payment to be issued
- Manually fail the first payment
- Check subscriptions (`python manage.py check_subscriptions --subscription=123 --ignore_date`)
- Observe that the subscription status is set to cancelled.

## Django Admin

Some new features have been added to the Django admin.

### Hooks

See `README.md`

### Revision history

Revision history is enabled for edits made within the admin site.

1.) Log in: http://HOSTNAME/silver/admin/
2.) Navigate to customers
3.) Create a customer
4.) Edit the customer name, address, etc.
5.) Save
6.) Go back to customer detail
7.) Click the `History` button in the upper righthand corner
8.) Choose two items in the change log
9.) Click compare.

### Management tasks

Some of the automatically running cron tasks are available within the admin
interface from the `Actions` menu just above the object list.

* Customer view:
  - Check overpayments
  - Check all subscriptions

* Invoice view
  - Check for failed transactions, and recreate.

## TODO

Documentation that needs creating above.

* Document where to find some of the admin tasks
* Metered feature stuff
