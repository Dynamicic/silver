from django.contrib import admin
from reversion.admin import VersionAdmin
from reversion_compare.admin import CompareVersionAdmin
from reversion_compare.helpers import patch_admin

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
admin.site.unregister(Subscription)


## Transaction overrides

@admin.register(Transaction)
class VersionedTransactionAdmin(VersionAdmin, TransactionAdmin):
    pass

patch_admin(Transaction)


## Invoice overrides

@admin.register(Invoice)
class VersionedInvoiceAdmin(VersionAdmin, InvoiceAdmin):
    pass

patch_admin(Invoice)



## Customer overrides

@admin.register(Customer)
class VersionedCustomerAdmin(VersionAdmin, CustomerAdmin):
    pass

patch_admin(Customer)

## Subscription overrides

@admin.register(Subscription)
class VersionedSubscriptionAdmin(VersionAdmin, SubscriptionAdmin):
    pass

patch_admin(Subscription)
