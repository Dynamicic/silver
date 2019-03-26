from annoying.functions import get_object_or_None

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from silver.models import Transaction
from silver.payment_processors import get_instance

from silver_authorizenet.models import AuthorizeNetTriggered


@api_view('GET')
def client_token(request, transaction_uuid=None):
    transaction = get_object_or_None(Transaction, id=transaction_uuid)

    payment_processor = get_instance(transaction.payment_processor)
    if not isinstance(payment_processor, AuthorizeNetTriggered):
        return Response(
            {'detail': 'Transaction is not a AuthorizeNetTriggered transaction.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    token = payment_processor.client_token(transaction.customer)

    if not token:
        return Response({'detail': 'AuthorizeNet miscommunication.'},
                        status=status.HTTP_503_SERVICE_UNAVAILABLE)

    return Response({'token': token}, status=status.HTTP_200_OK)
