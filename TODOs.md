# Major TODOs

 * Search the codebase for keywords to find places in the code that relate.

 * Completed features below will need to be turned into documentation. Then
   delete the sections.


## Metered Feature relationships

### Needs:

* "included units" for a metered feature, dependent on the number "consumed
  units" of another metered feature. E.g.  7000 outbound minutes included
  monthly per agent seat purchased?

* Minimum number of units associated with metered feature that are included
  every month

* Need a way to indicate a metered feature is pre-billed at the start of the
  billing cycle. Currently only available on plan level.

### Pre-billed and included units

* add an optional pre-billed minimum: when subscription starts, metered usage
  under X is pre-billed. When usage goes over this limit, it goes into normal
  billing.

### Linked feature calculation / LinkedFeaturesFeature

#### Documentation

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

#### Calculations supported

For now, only `add`, `subtract`, and `multiply` are supported, and the function
parameters are the following:

 1.) `MeteredFeature.included_units`
 2.) `MeteredFeatureUnitsLog.consumed_units`

To understand better how the number of consumed units are determined, see:

    silver.models.subscriptions.Subscription._get_included_units_calc

The summary is that this feature relies on existing code that determines
included units via log items during the billing date period.


