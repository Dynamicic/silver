# -*- coding: utf-8 -*-
# Generated by Django 1.11.17 on 2018-12-30 20:07
from __future__ import unicode_literals

from django.db import migrations, models
import django_fsm


class Migration(migrations.Migration):

    dependencies = [
        ('silver', '0050_auto_20181230_1946'),
    ]

    operations = [
        migrations.AlterField(
            model_name='transaction',
            name='fail_code',
            field=models.CharField(blank=True, choices=[('expired_payment_method', 'expired_payment_method'), ('default', 'default'), ('transaction_declined', 'transaction_declined'), ('transaction_hard_declined_by_bank', 'transaction_hard_declined_by_bank'), ('transaction_declined_by_bank', 'transaction_declined_by_bank'), ('limit_exceeded', 'limit_exceeded'), ('expired_card', 'expired_card'), ('invalid_card', 'invalid_card'), ('transaction_hard_declined', 'transaction_hard_declined'), ('invalid_payment_method', 'invalid_payment_method'), ('insufficient_funds', 'insufficient_funds')], max_length=32, null=True),
        ),
        migrations.AlterField(
            model_name='transaction',
            name='state',
            field=django_fsm.FSMField(choices=[('initial', 'Initial'), ('settled', 'Settled'), ('pending', 'Pending'), ('canceled', 'Canceled'), ('failed', 'Failed'), ('refunded', 'Refunded')], default='initial', max_length=8),
        ),
    ]