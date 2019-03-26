full-test: test

test:
	DJANGO_SETTINGS_MODULE= \
		pytest -vv \
		--capture=sys \
		--disable-warnings \
		--pyargs \
		silver_authorizenet.tests

watchtests:
	pywatch "make test" tests/*.py silver_authorizenet/*.py

run:
	echo "TBA"

build:
	echo "No need to build someting"

lint:
	pep8 --max-line-length=100 --exclude=migrations .

.PHONY: test full-test build lint run
