# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import jsonfield
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('silver', '0032_auto_20170201_1342'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuthorizeNetPaymentMethod',
            fields=[
            ],
            options={
                'proxy': True,
            },
            bases=('silver.paymentmethod',),
        ),
        migrations.CreateModel(
            name='CustomerData',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('data', jsonfield.fields.JSONField(default={}, null=True, blank=True)),
                ('customer', models.ForeignKey(to='silver.Customer')),
            ],
        ),
    ]
