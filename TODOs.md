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

### Linked feature calculation

As one feature increments, another feature's allowable pre-billed minimum
should be able to change.

* Add a MeteredFeature DB field for the related feature to base the calculation
  on.

* Use [ F expressions ][fexp] to calculate on a model field.

* Possibly: adjust MeteredFeatureLog calculation to either work as normal, or
  rely on this calculated field when summing up invoice totals.


  [fexp]: https://docs.djangoproject.com/en/1.11/topics/db/queries/

