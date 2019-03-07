===========
antikythera
===========

A django app that houses all the billing functionality you've come to know and love. What About February™?

package config TODOs:

* manage.py only accessible through package, convert it to an entry point
* test celery task setup
* handle manual path alteration in some better way
* include silver package as a package in antikythera, not as a path
  modification so that testing isn't a matter of global system config.

Features
--------

* Deploy setup
* Test running setup
* Access to usual django stuff

Tests
-----

Tox stuff will be coming, but for now we can test all the modifications
we've made through:

::

    make test

Deploy
------

Ssh in, make sure you have the latest and greatest, then 

:: 
    fab pack
    fab dev_deploy

