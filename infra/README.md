# Infra stuff

TODO: write out basic docs for setting up django app + silver + deps etc. 

## Docker

A dev environment for local work on silver and dependencies, through a basic
django app that loads silver as a module.


### Structure

The existing docker files require a certain base structure. We're assuming `projdir` is the root directory containing all the git repos, and etc:

    projdir/silver
    projdir/silver-authorize

Copy `Dockerfile` and `docker-compose.yml` into your root project directory:

    projdir/docker-compose.yml
    projdir/Dockerfile

Create a directory called `app`, where the Django app itself will live. It
should be enough to create a symlink from `silver/infra/dev_dot_com`:

    projdir/app/dev_dot_com

### Docker environment settings

Within `projdir/app/dev_dot_com/` copy `settings.py.in` to `settings.py`, do
not check it in. Run through this file looking for instances of `TODO`, and add
your own local settings.

Within your copy of `docker-compose.yml` run through and adjust any environment
settings. You may specifically need to provide your own API keys for payment
gateway sandboxes.

### Django app config

For any Django settings configuration questions, see `silver/README.md`.

## Running everything:

    docker-compose up

And wait a while for it to build. It will tag an image, so it will be quicker
to run the next time. If you change python dependencies however, you may need to re-build.

    docker-compose build web

## Logging in

Fixtures should automatically be installed to allow you to log in, you should
see the admin password displayed in the logs to `web_1`. This will not be
available on production services
