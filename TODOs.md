
# Major TODOs

Search the codebase for keywords to find places in the code that relate.

## PaymentOverages

Currently not supported. Complex issue to solve because it requires:

 * Transaction models that allow manual transactions to be created over the
   invoice amount

 * Customer object should track all overages charged

 * Billing Document that allows Transactions to be (manually?) issued to credit
   customers' accounts via their payment methods.

 * Payment Gateways should have methods to allow crediting accounts

 * Possibly future invoices could be issued and allow credits based on overage
   amount, so automatically issued transactions on future invoices could be
   settled with overage funds.

