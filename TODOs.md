# Major TODOs

 * Search the codebase for keywords to find places in the code that relate.

 * Completed features below will need to be turned into documentation. Then
   delete the sections.


## Transaction failure emails

* `EMAIL_ON_TRANSACTION_FAIL` = True
* `MANAGERS` must be set, or no emails will be sent

Also customize:

* `SERVER_EMAIL`
* `EMAIL_SUBJECT_PREFIX`

## Payment retries & grace period

* Document models handle the creation of transactions through payment methods.

  - `models.documents.base.create_transaction_for_document`
      (`post_document_save`)
  - `models.payment_methods.create_transactions_for_issued_documents`
      (`post_payment_method_save`)


* Transaction instances only represent the cycle of one payment attempt. Once
  state transition goes from Pending to Settled/Canceled/Failed/Refunded, it
  should no longer be reused.

* Store days to retry on customer Payment Method instances, using metadata
  field for now. Maybe: retry after days (1-2), stop retrying after days (4-5).
  (days after initial payment attempt). 
  
    Ex.) Retry after 2 days + stop after 5:

        Day 1: customer is billed
        Day 2: no success yet (transaction fails)
        Day 3: initiate retry attempts
        Day 4: continue retry attempts
        Day 5: stop retrying

* Create a new process that runs a couple times daily to check:

  - do unpaid documents have failed transactions
  - do the payment methods on those failed transactions have retry attempt settings
  - if so, initiate a new transaction for the payment method via the billing doc

* Alter or confirm that the transaction status checking process is emailing
  admins on transaction failure

## Overpayments

Concerns 3 model relationships:

 - Customer
 - Transaction
 - Document

__Management command and task__: settle up balance and issue invoice that
will trigger credit transaction.

- ✅ Calculating overpayment: Customer @property for balance. sum amounts paid
  by customer over all successful transactions associated with paid invoices
  minus the sum of document total

  - Q: do we really care if the customer overpays for one invoice and underpays
    another, while that invoice is listed as issued and unsettled?

- ✅ If amount is nonzero, issue new invoice with a negative amount (this will
  keep the sum 0 when corrected)

- ✅ New invoice Transactions created for customer payment methods; potentially
  standing in for a manual check sent to customer. Transction can be marked
  as Settled, and invoice marked as Paid.

✅ need to exclude any current balance correction invoices from the
calculation? Otherwise, imagine: 

a. management process runs, detects overage of 150
b. management process issues overpayment refund invoice of -150
c. if transactions for this aren't settled by the next run, a duplicate
   overpayment refund invoice could be issued for -150.

Ideas:
- new correction invoices may not be automatically issued while unpaid
  correction invoices exist: 



✅ __Manual overpaid Transactions__: transactions currently validate by amount on
billing doc, if new transaction would result in overpayment, transaction is
invalid and cannot be created.

- Add property on Transaction that can skip this validation, and otherwise
  process as normal.


✅ __Crediting accounts__: Same Transaction model will be used to credit accounts.

- Add a property to indicate that the Transaction is a credit, not a payment.
  (Negative integer for now)

- 🚫 `Transaction.process` should not be run for these transactions, because we
  will need to trigger a credit process. State transitions should result in
  States.Settled, as normal., but potentially the initial state should be
  something new.

    class Transaction(object):
        ... etc ... 

        @transition(field=state, source=States.Initial, target=States.Pending)
        def process(self):
            pass

Transaction needs to be checkable for status as normal: States.Pending ->
States.Settled


