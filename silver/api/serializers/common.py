# Copyright (c) 2015 Presslabs SRL
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import absolute_import

from django.conf import settings

from rest_framework import serializers
from rest_framework.reverse import reverse
from rest_framework.relations import HyperlinkedRelatedField

from silver.api.serializers.product_codes_serializer import ProductCodeRelatedField
from silver.models import MeteredFeature

from django.core.exceptions import ObjectDoesNotExist, MultipleObjectsReturned

class RelatedPropertyField(serializers.RelatedField):
    """ A serializer that uses a property on a related object to stand
    in for the object relationship. When you kind of need a
    SlugRelatedField, but with depth. Assumes a unique relationship,
    otherwise errors will be raised.

    :param related_lookup (str): a field accessor value that will be
        used to query and return values, e.g. `object__property`

    """

    def __init__(self, related_lookup=None, **kwargs):
        assert related_lookup is not None, 'The `related_lookup` argument is required.'
        self.related_lookup = related_lookup
        super(RelatedPropertyField, self).__init__(**kwargs)

    def to_internal_value(self, data):
        from django.db.models import Q

        try:
            return self.queryset.get(Q(**{
                self.related_lookup: data
            }))
        except (MultipleObjectsReturned, ObjectDoesNotExist, TypeError, ValueError):
            self.fail('invalid')

    def to_representation(self, instance):
        """ Traverse the related lookup string for the deepest argument.
        """
        w = instance
        for p in self.related_lookup.split('__'):
            w = getattr(w, p)
        return w


class CustomerUrl(HyperlinkedRelatedField):
    def get_url(self, obj, view_name, request, format):
        kwargs = {'customer_pk': obj.pk}
        return self.reverse(view_name, kwargs=kwargs, request=request, format=format)

    def get_object(self, view_name, view_args, view_kwargs):
        return self.queryset.get(pk=view_kwargs['customer_pk'])

    def use_pk_only_optimization(self):
        # We have the complete object instance already. We don't need
        # to run the 'only get the pk for this relationship' code.
        return False


class PaymentMethodTransactionsUrl(serializers.HyperlinkedIdentityField):
    def get_url(self, obj, view_name, request, format):
        lookup_value = getattr(obj, self.lookup_field)
        kwargs = {'payment_method_id': str(lookup_value),
                  'customer_pk': obj.customer_id}
        return self.reverse(view_name, kwargs=kwargs,
                            request=request, format=format)

class MeteredFeatureSerializer(serializers.ModelSerializer):
    product_code = ProductCodeRelatedField()

    linked_feature = RelatedPropertyField(related_lookup="product_code__value",
                                          queryset=MeteredFeature.objects.all(),
                                          required=False,
                                          allow_null=True)

    included_units_calculation = serializers.CharField(required=False,
                                                       allow_null=True)

    class Meta:
        model = MeteredFeature
        fields = ('name', 'unit', 'price_per_unit', 'included_units',
                  'product_code', 'included_units_calculation', 'linked_feature')

        extra_kwargs = {
            'included_units_calculation': {'required': False},
            'linked_feature': {'required': False},
        }

    def create(self, validated_data):
        product_code = validated_data.pop('product_code')
        product_code.save()

        validated_data.update({'product_code': product_code})

        metered_feature = MeteredFeature.objects.create(**validated_data)

        return metered_feature

    def to_representation(self, instance):
        """ Remove some additional fields if no value is set.
        """
        from collections import OrderedDict
        EMPTY_VALUES = ['', None, [], ()]
        EXCLUDABLE = self.Meta.extra_kwargs.items()

        ret = super().to_representation(instance)

        return OrderedDict(
            ( (name, value) for name, value in ret.items()
               if value not in EMPTY_VALUES and name not in EXCLUDABLE
            )
        )


class PDFUrl(serializers.HyperlinkedRelatedField):
    def get_url(self, obj, view_name, request, format):
        if not (obj.pdf and obj.pdf.url):
            return None

        if getattr(settings, 'SILVER_SHOW_PDF_STORAGE_URL', True):
            return request.build_absolute_uri(obj.pdf.url)

        return self.reverse(view_name, kwargs={'pdf_pk': obj.pdf.pk},
                            request=request, format=format)
