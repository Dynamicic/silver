# next

1. saving the bill cycle end date in the subscription model

2. figuring out how we’re gonna have different billing cycles for recurring vs
   usage billing.

## billing cycle end date / VariableCycleEndDate

need to store this not only for reference but because sometimes it needs to be
altered, and we cannot alter the cycle start date because this would omit days
when searching for usage billing stats.

### Implementation doc

Subject to change, but: 

 * `Subscription.cycle_end_override` - default is null.  If a date value is
   actually stored, that will be a manual cycle end and the billing
   calculations will run by that.

 * `Subscription.cycle_end_reference_date_display` - read only field that
   displays the next cycle end day no matter what `cycle_end_reference` is set
   to.

Questions:

 * What behavior do we want if mid-cycle, we set a new end date. Finish the
   cycle immediately on that date, or wait until the next? potential for wonky
   behavior.

## billing cycles

prepaid usage on a quarterly or annual basis, but still run recurring billing
items on a monthly basis. possibly allowing related metered features across
different subscriptions?

ex.:

sub 1 (annual cycle): predictive seats monthly recurring fees
sub 2 (monthly cycle): talk time minutes, DID fees (which may have included
free units based on quantities in subscription #1)

# later

* sdk: manual transaction endpoint that creates customer, invoice & starts
  processing transaction

* plans and subscriptions: demoable plan on server running transactions against
  authorize.net sandbox

