# Major TODOs

Search the codebase for keywords to find places in the code that relate.

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


