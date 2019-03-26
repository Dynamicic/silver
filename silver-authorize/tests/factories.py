import factory
from factory.django import mute_signals

from django.db.models import signals

from silver.tests.factories import TransactionFactory, CustomerFactory, DocumentEntryFactory, ProviderFactory, InvoiceFactory as InvoiceFact

from silver_authorizenet.models import AuthorizeNetPaymentMethod

class EntryFactory(DocumentEntryFactory):
    quantity = factory.fuzzy.FuzzyDecimal(low=1.00, high=5.00, precision=4)
    unit_price = factory.fuzzy.FuzzyDecimal(low=0.01, high=5.00, precision=4)

class InvoiceFactory(InvoiceFact):
    currency = 'USD'
    transaction_currency = 'USD'

@mute_signals(signals.pre_save, signals.post_save)
class AuthorizeNetPaymentMethodFactory(factory.DjangoModelFactory):
    class Meta:
        model = AuthorizeNetPaymentMethod

    payment_processor = 'AuthorizeNetTriggered'
    customer = factory.SubFactory(CustomerFactory)
    data = factory.Sequence(lambda i: {})


@mute_signals(signals.pre_save, signals.post_save)
class AuthorizeNetRecurringPaymentMethodFactory(factory.DjangoModelFactory):
    class Meta:
        model = AuthorizeNetPaymentMethod

    payment_processor = 'AuthorizeNetTriggeredRecurring'
    customer = factory.SubFactory(CustomerFactory)
    data = factory.Sequence(lambda i: {})


class AuthorizeNetTransactionFactory(TransactionFactory):
    payment_method = factory.SubFactory(AuthorizeNetPaymentMethodFactory)
