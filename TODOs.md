# next

1. ...

## billing cycle end date / VariableCycleEndDate

Questions:

 * What behavior do we want if mid-cycle, we set a new end date. Finish the
   cycle immediately on that date, or wait until the next? potential for wonky
   behavior.

## split billing cycles / LinkedSubscriptions

This feature is enabled on the Subscription level, and allows the linking of
Subscriptions that are dependent on eachother for billing calculations.

TODO: add stuff for `Subscription._get_proration_status_and_percent` on
remaining intervals (DAY and WEEK), and write out unit tests for those two too.

TODO: do we want to duplicate billing entry items on a subscription that is
  linked?

### Use cases

sub 1 (annual cycle): predictive seats monthly recurring fees
sub 2 (monthly cycle): talk time minutes, DID fees (which may have included
free units based on quantities in subscription #1)

- seats yearly, usage monthly, but monthly allowance needs to be represented on
  the monthly basis 

prorated vs usage billing, customers can add seats in the middle of the month,
or remove seats; but reduction shouldn’t take effect until next monthly billing
cycle 

#### Asshole customer loophole

Situation:

- Add a seat at the beginning of the month, then run a plan and get ridiculous
  levels of overage. 
- At the last day of the month you add 10 seats to get a ton of included
  minutes and kill overage.
- Asshole discount

##### Solutions

We need to bill in a manner where seats are a consumable resource, something
which silver already supports. But this should be taken into account in the
math for minutes calculated by seats consumed. E.g., if we go with seats
consumed per day, then there's no room for someone to fudge numbers around to
get what they want.

#### Prorated functionality

Need to prorate included minutes somehow, if customers add a seat in the middle
of the month they only get half of the included minutes just for that billing
cycle.

### Implementation notes

Going to use two separate plans for this but link and calculate minutes by the
seat feature of a linked subscription.

TODO: determine if the proration in silver can handle some of this
automatically

TODO: fix proration - it looks like the MONTHLYISH setting may break
subscription proration calculations, since proration stuff assumes that monthly
periods are pinned to calendar months.

## invoice html tweaks

 * Clean up and neaten based on sample
 * Invoice entry item generation should be altered to include something with a
   $0 amount that references the linked subscription, providing either a
   subscription ID or something useful to customers

