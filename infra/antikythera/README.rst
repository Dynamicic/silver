===========
antikythera
===========

A django app that houses all the billing functionality you've come to know and love. What About February™?

package config TODOs:

* include silver package as a package in antikythera, not as a path
  modification so that testing isn't a matter of global system config.
* bumpversion for `silver` deploy, or just include in antikythera?
* server setup - $HOME/deploy/antikythera 
* test celery task setup


Quickstart
----------

**Developing**

* Clone the repo, and navigate to this directory.
* Create a virtualenv or whatever you need
* Run python setup.py develop
* Run python setup.py test


Features
--------

* Deploy setup
* Test running (`make test`)
* Access to usual django stuff (`antikythera-manage`)
* wsgi app entrypoint (`antikythera.antikythera.wsgi`)


Tests
-----

Tox stuff will be coming, but for now we can test all the modifications
we've made through:

::

    make test

Deploy
------

This bit is currently changing, see `fabfile.py` at the root of the repo for
docs. Working server deploy process will appear shortly.


Dealing with silver packages
----------------------------

This package is solely focused on the Django aspects of running the web
server. 

**For deploy**, the modified version of `silver` should be installed
separately as a package, as with any extra plugins for silver.  You may
want to build stable versions of these via `bdist_wheel` for deploy.

**For development**, you will want to include the source in the PYTHON
PATH. You can do this via your PATH or `.env`:

::

    ANTIKYTHERA_EXTRA_PATHS=/path/to/silver:/path/to/silver_authorize

This will then be included before app launch so that the modules will be
found, and code changes will be included.

Package dependencies to `silver`, are included in this package
(`setup.py`) to make sure everything will build as expected.

Configuring wsgi, nginx, etc.
-----------------------------

write up:

* wsgi.ini
* uwsgi install, and plugins: logging, uwsgi-python3 
* nginx config example

