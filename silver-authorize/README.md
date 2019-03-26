# silver-authorizenet 

Authorize.Net payment processor for silver. 

## Installing

### ... within a Silver Django app

Within a virtual environment, install the package:

    cd /path/to/silver_authorizenet/
    python setup.py install

Then configure the settings.

### ... by calling the source directly

If you need to frequently update the source on a remote server, the best option
may be to alter the path. 

Check out the source somewhere accessible to your Django app. Include the path
to the code within `settings.py`:

    sys.path.append('/path/to/silver_authorizenet/')
 
### Configuring the settings

Within `settings.py` add the package to `INSTALLED_PACKAGES` after `silver`:

    INSTALLED_APPS = (
        ...
        'silver',
        'silver_authorizenet',
        ...
    )

Then, adjust the `PAYMENT_PROCESSORS` setting thus. Make sure to store your API
credentials somewhere out of source control. NB: they could be stored in
memory, and retrieved from `os.environ`.

    PAYMENT_PROCESSORS = {
        'AuthorizeNetTriggered': {
            'setup_data': {
                'environment': authorizenetconstants.constants.SANDBOX,
                'api_login': 'YOUR_AUTHORIZENET_API_LOGIN',
                'transaction_key': 'YOUR_AUTHORIZENET_TRANSACTION_KEY',
                'key': 'YOUR_AUTHORIZENET_KEY',
            },
            'class': 'silver_authorizenet.payment_processors.AuthorizeNetTriggered',
        },
        'AuthorizeNetTriggeredRecurring': {
            'setup_data': {
                'environment': authorizenetconstants.constants.SANDBOX,
                'api_login': 'YOUR_AUTHORIZENET_API_LOGIN',
                'transaction_key': 'YOUR_AUTHORIZENET_TRANSACTION_KEY',
                'key': 'YOUR_AUTHORIZENET_KEY',
            },
            'class': 'silver_authorizenet.payment_processors.AuthorizeNetTriggeredRecurring'
        },
    }

## Developing

To develop locally outside of a Silver installation, you can run the tests,
which create a small local Django+Silver installation. Tests are run against
this.

### 1. configure constants.py

In order to test against an Authorize.net API you will need to configure API
constants. For convenience, a sample file is checked in in `constants.py.in`.
Copy this to `constants.py` and edit the file with your sandbox values.

NB: do not check it in. Git will ignoring it: do not remove it from .gitignore.

### 2. Install test dependencies

Create a virtual environment, then install the test dependencies:

    pip install -r requirements.test.txt


Then run the tests.

    make test

Or watch for local changes and run on change:

    make watchtests
