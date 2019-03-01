full-test: test

/tmp/test.env: 
	cd /code/silver
	pip install -r requirements/test.txt
	pip install watchdog
	touch /tmp/test.env

/tmp/test.sdk.env: 
	cd /code/silver/infra/silversdk/
	python setup.py develop
	pip install watchdog
	touch /tmp/test.sdk.env

runsdk:
	cd /code/silver/infra/silversdk/ && \
		flock -n testing.lock silversdk --list-endpoints

watchsdk: /tmp/test.sdk.env
	cd /code/silver/infra/silversdk/ && watchmedo shell-command \
		--patterns="*.py" \
		--recursive \
		--command="make runsdk"

testwatch: /tmp/test.env
	watchmedo shell-command \
		--patterns="*.py" \
		--recursive \
		--ignore-directories \
		--command="flock -n testing.lock make testmod"

# --log-level=INFO
testmod:
	DJANGO_SETTINGS_MODULE=settings_test \
	    pytest -vv \
	    --capture=sys \
		--pyargs \
		silver.tests.integration.test_transactions_overpayments \
		silver.tests.integration.test_documents_transactions_hooks \
		silver.tests.integration.test_transaction_decline_retries \
		silver.tests.integration.test_transactions_overpayments \
		silver.tests.api.test_metered_feature \
		silver.tests.unit.test_metered_features

# silver.tests.integration.test_transactions_overpayments \
# silver.tests.integration.test_documents_transactions_hooks \
# silver.tests.integration.test_transaction_decline_retries \
# silver.tests.integration.test_transactions_overpayments \
# silver.tests.api.test_customer_overpayments

test:
	DJANGO_SETTINGS_MODULE=settings_test pytest -vv

run:
	echo "TBA"

dependencies:
	pip install -U -r requirements/test.txt

build:
	echo "No need to build something. You may try 'make dependencies'."

lint:
	pep8 --max-line-length=100 --exclude=migrations,urls.py,setup.py .

.PHONY: test full-test build lint run
