from __future__ import absolute_import

from uuid import UUID

from datetime import datetime as dt
from datetime import timedelta
from decimal import Decimal

from django_filters.rest_framework import DjangoFilterBackend
from django_fsm import TransitionNotAllowed

from django.http import Http404

from rest_framework import permissions, status
from rest_framework.generics import ListCreateAPIView, get_object_or_404, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from silver.api.filters import TransactionFilter
from silver.api.serializers.transaction_serializers import TransactionSerializer
from silver.api.serializers.billing_entities_serializers import CustomerSerializer, ProviderSerializer
from silver.api.serializers.payment_methods_serializers import PaymentMethodSerializer
from silver.api.serializers.documents_serializers import InvoiceSerializer

from silver.models import PaymentMethod, Transaction, Invoice, Customer, Provider, DocumentEntry

import coreapi
import uuid


# doc: OneOffTransactions
class TransactionOneOff(APIView):
    permission_classes = (permissions.IsAuthenticated,)
    # serializer_class = TransactionSerializer
    # filter_backends = (DjangoFilterBackend,)
    # filter_class = TransactionFilter

    # TODO: write out a schema once this settles.
    schema = coreapi.Document(
        title='One-off Transaction API',
        content={ }
    )

    def post(self, request, *args, **kwargs):
        """ Create a one off transaction by way of creating an invoice,
        payment method and document, and return the created transaction.
        """

        import simplejson as json

        rq = request.data

        customer_one_off_defaults = {
            "currency": "USD",
        }

        customer = None
        has_uuid = rq.get('customer', {}).get('account_id', False)

        if has_uuid:
            _u = uuid.UUID(has_uuid)
            # This will provide an exception if an invalid UUID is given
            customer = Customer.objects.get(account_id=_u)

        if customer == None:
            new_customer = customer_one_off_defaults
            new_customer.update(**rq.get('customer'))
            customer = Customer(**new_customer)
            customer.save()

        # URI object
        customer_id = customer.id

        ## Create a customer payment method
        # 

        # check if a method for the customer with this payment_processor
        # doesn't exist yet

        pp = rq.get("payment_processor", "manual")

        try:
            has_method = PaymentMethod.objects.get(customer=customer,
                                                   payment_processor=pp)
        except PaymentMethod.DoesNotExist:
            has_method = False

        if not has_method:
            customer_default_payment_method = {
                "customer": customer,
                "payment_processor": pp,
                "verified": True,
                "canceled": False,
                "valid_until": dt.now() + timedelta(days=7),
                "display_info": "pytest",
                "data": json.dumps({
                    "attempt_retries_after": 2,
                    "stop_retry_attempts": 5
                })
            }
            new_pm = PaymentMethod(**customer_default_payment_method)
            new_pm.save()
        else:
            new_pm = has_method

        ## Get a provider
        # TODO: determine who we want as default
        # 
        provider = Provider.objects.filter(invoice_series="BPInvoiceSeries").first()
        if provider is None:
            prv = {
                "name": "Internal Billing Provider",
                "company": "Internal Billing Provider",
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
            }
            provider = Provider(**prv)
            provider.save()

        ## Create an invoice
        # Some defaults to save effort from the client user
        # 

        invoice_one_off_defaults = {
            "provider": provider,
            "series": provider.invoice_series,
            "customer": customer,
            "transaction_currency": "USD",
            "transaction_xe_rate": Decimal('1.0000'),
            # "transaction_xe_date": dt.datetime(2019, 1, 15, 0, 0, 0),
            "currency": "USD",
            "state": "draft",
        }

        invoice_intry_defaults = {
            "quantity": 1.0,
            "unit_price": rq.get("amount", 0.0),
            "start_date": None,
            "end_date": None,
            "prorated": False,
            "product_code": None
        }

        new_entry = invoice_intry_defaults.copy()

        new_invoice = invoice_one_off_defaults.copy()
        new_invoice.update(**kwargs.get("invoice", {}))

        inv = Invoice(**new_invoice)
        inv.save()

        entr = DocumentEntry(**new_entry)
        entr.save()
        inv.invoice_entries.add(entr)
        inv.save()

        inv.issue()
        inv.save()


        transaction = Transaction.objects.filter(invoice=inv).first()

        _ser_kwargs = {
            "context": {"request": request}
        }

        return Response({
            "customer": CustomerSerializer(customer, **_ser_kwargs).data,
            "payment_method": PaymentMethodSerializer(new_pm, **_ser_kwargs).data,
            "provider": ProviderSerializer(provider, **_ser_kwargs).data,
            "invoice": InvoiceSerializer(inv, **_ser_kwargs).data,
            "transaction": TransactionSerializer(transaction, **_ser_kwargs).data,
        })

