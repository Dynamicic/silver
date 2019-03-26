import authorizenet as sdk
# from authorizenet.exceptions import NotFoundError

from silver.models import PaymentMethod


class AuthorizeNetPaymentMethod(PaymentMethod):
    # TODO: determine structure that will be stored 
    """
        data field structure
        {
            'nonce': 'some-nonce', (encrypted, deleted if token exists)
            'token': 'some-token', (encrypted)
            'authorizenet_id': 'transaction-id-given-by-authorizenet',
            'status': 'status-given-by-authorizenet' (does not exist if
                                                   Transaction.state is Initial)
            'details': {
            }
        }
    """
    class Meta:
        proxy = True

    class Types:
        PayPal = 'paypal_account'
        CreditCard = 'credit_card'

    @property
    def authorizenet_transaction(self):
        try:
            return sdk.Transaction.find(self.authorizenet_id)
        except NotFoundError:
            return None

    @property
    def authorizenet_id(self):
        return self.data.get('authorizenet_id')

    @property
    def token(self):
        return self.decrypt_data(self.data.get('token'))

    @token.setter
    def token(self, value):
        self.data['token'] = self.encrypt_data(value)

    @property
    def nonce(self):
        return self.decrypt_data(self.data.get('nonce'))

    @nonce.setter
    def nonce(self, value):
        self.data['nonce'] = self.encrypt_data(value)

    def update_details(self, details):
        if 'details' not in self.data:
            self.data['details'] = details
        else:
            self.data['details'].update(details)

    @property
    def details(self):
        return self.data.get('details')

    @property
    def public_data(self):
        return self.data.get('details')
