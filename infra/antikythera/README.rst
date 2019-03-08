===========
antikythera
===========

A django app that houses all the billing functionality you've come to know and love. What About February™?

package config TODOs:

* include silver package as a package in antikythera, not as a path
  modification so that testing isn't a matter of global system config.
* best way to expose wsgi / uwsgi for configuring actual prod
  environment? cli command for running?
* server setup - $HOME/deploy/antikythera 
* test celery task setup
* handle manual path alteration in some better way


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
* Test running setup
* Access to usual django stuff
* wsgi app entrypoint


Tests
-----

Tox stuff will be coming, but for now we can test all the modifications
we've made through:

::

    make test

Deploy
------

SSH in, make sure you have the latest and greatest. To deploy to a
development server where code is simply executed from the repo: 

:: 
    fab deploy:dev


Or, to pack a tgz distribution and deploy via pip:

:: 
    fab pack
    fab deploy:prod




Configuring wsgi, nginx, etc.
-----------------------------

write up:

* wsgi.ini
* uwsgi intall, and plugins: logging, uwsgi-python3 
* nginx config example

