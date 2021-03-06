from django.contrib import admin
from reversion.admin import VersionAdmin

from silver.admin import *
from silver.models import (
    Plan, MeteredFeature, Subscription, Customer, Provider,
    MeteredFeatureUnitsLog, Invoice, DocumentEntry,
    ProductCode, Proforma, BillingLog, BillingDocumentBase,
    Transaction, PaymentMethod
)

# We could add versioning to these, as well.

# admin.site.unregister(PaymentMethod, PaymentMethodAdmin)
# admin.site.unregister(Plan, PlanAdmin)
# admin.site.unregister(Subscription, SubscriptionAdmin)
# admin.site.unregister(Provider, ProviderAdmin)
# admin.site.unregister(Proforma, ProformaAdmin)
# admin.site.unregister(ProductCode)
# admin.site.unregister(MeteredFeature)

admin.site.unregister(Transaction)
admin.site.unregister(Invoice)
admin.site.unregister(Customer)

@admin.register(Transaction)
class VersionedTransactionAdmin(VersionAdmin, TransactionAdmin):
    pass

@admin.register(Invoice)
class VersionedInvoiceAdmin(VersionAdmin, InvoiceAdmin):
    pass

@admin.register(Customer)
class VersionedCustomerAdmin(VersionAdmin, CustomerAdmin):
    pass

