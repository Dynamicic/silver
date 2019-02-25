from __future__ import absolute_import

import json
import pytest

from decimal import Decimal
from rest_framework import status
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from silver.tests.factories import (AdminUserFactory, MeteredFeatureFactory,
                                    ProductCodeFactory)
from silver.tests.utils import build_absolute_test_url


class TestMeteredFeatureEndpoint(APITestCase):

    def setUp(self):
        admin_user = AdminUserFactory.create()
        self.client.force_authenticate(user=admin_user)
        ProductCodeFactory.reset_sequence(1)
        self.product_code = ProductCodeFactory.create()
        self.complete_data = {
            "name": "Page Views",
            "unit": "100k",
            "price_per_unit": '0.0500',
            "included_units": '0.0000',
            "product_code": self.product_code.value
        }

    """
    def _full_url(self, pk=None):
        base_url = "http://testserver"
        relative_url = reverse('metered-feature-detail', kwargs={'pk': pk})
        return urlparse.urljoin(base_url, relative_url)
    """

    def test_create_post_metered_feature(self):
        url = reverse('metered-feature-list')
        response = self.client.post(url, json.dumps(self.complete_data),
                                    content_type='application/json')
        assert response.status_code == status.HTTP_201_CREATED
        expected = self.complete_data
        # expected.update({'url': self._full_url(1)})
        assert expected == response.data

    def test_create_post_metered_feature_without_required_field(self):
        url = reverse('metered-feature-list')

        required_fields = ['name', 'price_per_unit', 'included_units']
        for field in required_fields:
            temp_data = self.complete_data.copy()
            try:
                temp_data.pop(field)
            except KeyError:
                pytest.xfail('Metered Feature required field %s not provided in'
                             'the complete test data.' % field)

            response = self.client.post(url, json.dumps(temp_data),
                                        content_type='application/json')

            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            assert (response.data == {field: ['This field may not be blank.']} or
                    response.data == {field: ['This field is required.']})
    """
    #def test_create_post_metered_feature_bulk(self):
        #mfs = MeteredFeatureFactory.create_batch(7)

        #raw_mfs = json.loads(serializers.serialize('json', mfs))

        #serialized_mfs = []
        #for item in raw_mfs:
            #serialized_mfs.append(item['fields'])

        #url = reverse('metered-feature-list')

        #response = self.client.post(url, data=json.dumps(serialized_mfs),
                                    #content_type='application/json')

        #self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        #self.assertEqual(len(response.data), 7)

    def test_get_metered_feature_detail(self):
        metered_feature = MeteredFeatureFactory.create(product_code=self.product_code)

        url = reverse('metered-feature-detail',
                      kwargs={'pk': metered_feature.pk})

        response = self.client.get(url)

        assert response.status_code == status.HTTP_200_OK
        assert response.data == {
            "name": metered_feature.name,
            "unit": metered_feature.unit,
            "included_units": metered_feature.included_units.to_eng_string(),
            "price_per_unit": metered_feature.price_per_unit.to_eng_string(),
            "product_code": self.product_code.value,
            'url': self._full_url(1)
        }
    """

    def test_get_metered_feature_list(self):
        MeteredFeatureFactory.create_batch(40)
        url = reverse('metered-feature-list')

        response = self.client.get(url)

        full_url = build_absolute_test_url(url)

        assert response.status_code == status.HTTP_200_OK
        assert response._headers['link'] == \
            ('Link', '<' + full_url + '?page=2>; rel="next", ' +
             '<' + full_url + '?page=1>; rel="first", ' +
             '<' + full_url + '?page=2> rel="last"')

        response = self.client.get(url + '?page=2')

        assert response.status_code == status.HTTP_200_OK
        assert response._headers['link'] == \
            ('Link', '<' + full_url + '>; rel="prev", ' +
             '<' + full_url + '?page=1>; rel="first", ' +
             '<' + full_url + '?page=2> rel="last"')

    """
    def test_get_metered_feature_unexisting(self):
        url = reverse('metered-feature-detail',
                      kwargs={'pk': 42})

        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data, {u'detail': u'Not found'})

    def test_delete_metered_feature(self):
        MeteredFeatureFactory.create()

        url = reverse('metered-feature-detail', kwargs={'pk': 1})

        response = self.client.delete(url)

        self.assertEqual(response.status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data,
                         {u'detail': u"Method 'DELETE' not allowed."})

    def test_edit_put_metered_feature(self):
        MeteredFeatureFactory.create()

        url = reverse('metered-feature-detail', kwargs={'pk': 1})

        response = self.client.put(url)

        self.assertEqual(response.status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data,
                         {u'detail': u"Method 'PUT' not allowed."})

    def test_edit_patch_metered_feature(self):
        MeteredFeatureFactory.create()

        url = reverse('metered-feature-detail', kwargs={'pk': 1})

        response = self.client.patch(url)

        self.assertEqual(response.status_code,
                         status.HTTP_405_METHOD_NOT_ALLOWED)
        self.assertEqual(response.data,
                         {u'detail': u"Method 'PATCH' not allowed."})

    """

class TestLinkedMeteredFeatureEndpoint(APITestCase):

    def setUp(self):
        admin_user = AdminUserFactory.create()
        self.client.force_authenticate(user=admin_user)
        ProductCodeFactory.reset_sequence(1)
        self.user_product_code = ProductCodeFactory.create(value="user_product_code")
        self.user_feature_data = {
            "name": "Users",
            "unit": "user",
            "price_per_unit": '1.0000',
            "included_units": '0.0000',
            "product_code": self.user_product_code.value
        }

        self.minutes_product_code = ProductCodeFactory.create(value="minutes_product_code")
        self.minutes_data = {
            "name": "Minutes",
            "unit": "20 minutes / user",
            "price_per_unit": '5.0000',
            "included_units": '20.0000',
            "product_code": self.minutes_product_code.value,
        }

        self.link                               = self.minutes_data.copy()
        self.link['linked_feature']             = self.user_product_code.value
        self.link['linked_feature_calculation'] = "multiply"


        self.prebill_minutes_product_code = ProductCodeFactory.create(
            value="prebill_minutes_product_code"
        )

        self.prebill_minutes_data = {
            "name": "Minutes",
            "unit": "20 minutes / user",
            "prebill_included_units": True,
            "price_per_unit": '5.0000',
            "included_units": '20.0000',
            "product_code": self.minutes_product_code.value,
        }

    @pytest.mark.django_db
    def test_create_post_metered_feature(self):
        """ Test creating the features individually.
        """

        url = reverse('metered-feature-list')
        response = self.client.post(url, json.dumps(self.user_feature_data),
                                    content_type='application/json')
        assert response.status_code == status.HTTP_201_CREATED
        expected = self.user_feature_data

        assert expected == response.data

        minutes_with_link = self.minutes_data

        response = self.client.post(url, json.dumps(minutes_with_link),
                                    content_type='application/json')
        try:
            response.data.pop('pk')
        except:
            pass
        assert response.status_code == status.HTTP_201_CREATED
        expected = self.minutes_data

        assert expected == response.data

    @pytest.mark.django_db
    def test_create_post_metered_feature_with_link(self):
        """ Create the features as above, add a link.
        """

        url = reverse('metered-feature-list')

        response = self.client.post(url,
                                    json.dumps(self.user_feature_data),
                                    content_type='application/json')

        l = self.link
        response = self.client.post(url, json.dumps(l),
                                    content_type='application/json')

        assert response.status_code == status.HTTP_201_CREATED
        expected = self.link

        assert response.data.get('linked_feature') == self.user_product_code.value

    @pytest.mark.django_db
    def test_create_prebilled_feature(self):
        url = reverse('metered-feature-list')
        response = self.client.post(url, json.dumps(self.prebill_minutes_data),
                                    content_type='application/json')
        assert response.status_code == status.HTTP_201_CREATED
        expected = self.prebill_minutes_data

        assert expected == response.data


