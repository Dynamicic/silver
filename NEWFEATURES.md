# New Features

Here's a running overview of some of the new features we've created for Silver.
Some of these include keywords for searching the codebase (via `ag` or
something) to find the implementation.

## Linked feature calculation

### keyword: LinkedFeaturesFeature

Linked Features allow you to provide a calculation for included or pre-billed
units on one particular feature that depends on how many units of another
feature have been consumed.

Scenario: suppose we have a plan with two features, one for `users` and one for
`minutes`. The amount of pre-billed minutes must be a product of the number of
users included, and the amount of pre-billed or included minutes. The base plan
is `$10`, and `20` minutes per user are included at a cost of `$5 / 20 minutes`.

We need to create two features. Note that it's important to consider the
`included_units` setting. This behaves differently with a linked feature, than
if the feature were a normal standalone feature. In the following example, the
total of included minutes is calculated from the users feature, and we want
it to be more obvious how the math works out, so there are `0` included
users.

    users_feature = MeteredFeatureFactory(
        name="Phone users",
        unit="users",
        included_units=Decimal('0.00'),
        price_per_unit=Decimal('0.00')
    )

    minutes_per_user = MeteredFeature(
        name="Phone minutes",
        unit="Minutes (per user)",
        included_units=Decimal('20.00'),
        included_units_during_trial=Decimal('0.00'),
        price_per_unit=Decimal('5.00'),
        # Here's where the linked magic happens.
        linked_feature=users_feature,
        included_units_calculation="multiply",
    )

These are added to the `Plan` object as normal, and subscriptions are created
for a user.

In order to activate these features within a user's `Subscription`, however, we
need to log usage of the users. If no users are logged, the calculation of
consumed minutes will fall back to the existing silver functionality. If logged 


    users_log = MeteredFeatureUnitsLog(
        subscription=subscription,
        metered_feature=users_feature,
        start_date=start_date,
        end_date=end_date,
        consumed_units=Decimal('2.00')
    )


    phone_log = MeteredFeatureUnitsLog(
        subscription=subscription,
        metered_feature=metered_feature,
        start_date=feature_usage_start,
        end_date=feature_usage_end,
        consumed_units=Decimal('40.00')
    )

Now when this plan is evaluated, `40` minutes will be included
(`users.consumed_units * phone_feature.included_units`), and usage above that
will be charged.

### Calculations supported

For now, only `add`, `subtract`, and `multiply` are supported, and the function
parameters are the following:

 1.) `MeteredFeature.included_units`
 2.) `MeteredFeatureUnitsLog.consumed_units`

To understand better how the number of consumed units are determined, see:

    silver.models.subscriptions.Subscription._get_included_units_calc

The summary is that this feature relies on existing code that determines
included units via log items during the billing date period.

## Pre-billed Metered Features (PrebilledMeteredFeature)

The default functionality of Metered Features is to allow for an amount of
"included" units of the metered feature, which are free and not billed.

For plans that need to include the cost of a set of included features in the
total, the feature may be marked as pre-billed. The total of the included units
will be calculated out.

    MeteredFeature(
        # This
        prebill_included_units=True,
        
        name="Charcoal Base Units",
        unit="Barrels (per seat)",
        included_units=Decimal('40.00'),
        price_per_unit=Decimal('1.00'),
    )

To track overage, it is best for now to use a separate metered feature (with
zero included units), which will then support separate unit cost rates for
overage.

## Subscription Checker

Check subscriptions for failed payments past a certain grace period, and cancel
subscriptions.

The subscription checker can run automatically as a Celerybeat task:

    CELERY_BEAT_SCHEDULE = {
        ...
        'check-subscriptions': {
            'task': 'silver.tasks.check_subscriptions',
            'schedule': datetime.timedelta(seconds=60),
        },
        ...
    }

It can also be run manually via `django manage.py`.

TODO: more doc

## Transaction Retries

Retry transactions daily after a grace period, and until a certain cutoff date.

The transaction retry feature can run automatically as a Celerybeat task:

    CELERY_BEAT_SCHEDULE = {
        ...
        'retry-failed-transactions': {
            'task': 'silver.tasks.retry_failed_transactions',
            'schedule': datetime.timedelta(seconds=60),
        },
        ...
    }

TODO: more doc

## Overpayment checking

    CELERY_BEAT_SCHEDULE = {
        ...
        'check-overpayments': {
            'task': 'silver.tasks.check_overpayments',
            'schedule': datetime.timedelta(seconds=60),
        },
        ...
    }

TODO: more doc

## Webhooks

After initailizing the database and running all migrations, hooks should be
ready to install and use. It requires the following:

1.) Configure a celery beat task to process incoming hook delivery tasks. (See
the section on installing and configuring celery). The task definition for the
webhook should look something like the following:

    CELERY_BEAT_SCHEDULE = {
        ...
        'process-hooks': {
            'task': 'silverintegration.hooktask.process_hooks',
            'schedule': datetime.timedelta(seconds=10),
        }
        ...
    }

2.) Silver requires a `HOOK_FINDER` and a `HOOK_DELIVERER` function to be set
in `settings.py`:

    HOOK_FINDER    = 'silverintegration.hooktask.find_and_fire_hook'
    HOOK_DELIVERER = 'silverintegration.hooktask.deliver_hook_wrapper'

3.) `HOOK_EVENTS` needs to be set in `settings.py`. Following is an example,
but more custom hooks may be created than these.

    HOOK_EVENTS = {
        'any.event.name': 'App.Model.Action' (created/updated/deleted)
        'customer.created': 'silver.Customer.created',
        'customer.updated': 'silver.Customer.updated',
        'customer.deleted': 'silver.Customer.deleted',

        'plan.created': 'silver.Plan.created',
        'plan.updated': 'silver.Plan.updated',
        'plan.deleted': 'silver.Plan.deleted',

        'subscription.created': 'silver.Subscription.created',
        'subscription.updated': 'silver.Subscription.updated',
        'subscription.deleted': 'silver.Subscription.deleted',

        'provider.created': 'silver.Provider.created',
        'provider.updated': 'silver.Provider.updated',
        'provider.deleted': 'silver.Provider.deleted',

        'invoice.created': 'silver.Invoice.created',
        'invoice.updated': 'silver.Invoice.updated',
        'invoice.deleted': 'silver.Invoice.deleted',

        'proforma.created': 'silver.Proforma.created',
        'proforma.updated': 'silver.Proforma.updated',
        'proforma.deleted': 'silver.Proforma.deleted',
    }


4.) Once all the settings are configured, for each hook needed, a Hook
definition needs to be created in the database. Log in to the Django admin and
add a Hook object, and configure the webhook endpoint. The User field may be
required, but it's not necessary: set it to 1 for the root user.


### Testing hooks

For each hook definition, specify a URL that verbosely logs. If you need
something for this that requires almost no effort, use
[https://www.webhookapp.com](https://www.webhookapp.com). NB: only use it for
testing purposes, and not live data.


### Documentation TODOs

Each of these need some doc

    INSTALLED_APPS = [
        ...
        'reversion',
        'reversion_compare',
        'rest_framework_swagger',
        'silver_authorizenet',
        'history',
        'swagger',
        ...
    ]

#### Partial Payments
#### Refund API
#### Offline Payments
#### Object Revision History

