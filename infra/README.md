# Infra stuff

TODO: write out basic docs for setting up django app + silver + deps etc. 

## Docker

A dev environment for local work on silver and dependencies, through a basic
django app that loads silver as a module.

TODO: write 

    projdir/docker-compose.yml
    projdir/Dockerfile
    projdir/app/dev_dot_com
    projdir/silver
    projdir/silver-authorize

TODO: environment variable setup

Then

    docker-compose up

And wait a while.

## Logging in

Fixtures should automatically be installed to allow you to log in, you should
see the admin password displayed in the logs to `web_1`. This will not be available on production services
