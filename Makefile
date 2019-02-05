full-test: test

testwatch:
	watchmedo shell-command --patterns="*.py" --recursive --ignore-directories --command="flock -n testing.lock make testmod"

testmod:
	DJANGO_SETTINGS_MODULE=settings_test pytest -vv --pyargs silver.tests.integration.test_documents_transactions_hooks

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
