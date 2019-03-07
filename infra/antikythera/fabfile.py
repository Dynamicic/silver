from fabric.api import *
from fabric.api import env, run, local, put, prefix, cd, settings
from fabric.contrib.project import rsync_project
import requests

# the user to use for the remote commands
# the servers where the commands are executed
env.hosts = [ ]

ENVIRONMENTS = {
    'dev': {
        'user': '',
        'hosts': [],
        'target_dir': '/opt/sites/dev.billing.dynamicic.com',
    },
    'prod': {
        'user': '',
        'hosts': [''],
        'target_dir': '/TBD',
    }
}


def set_environment(environment_name='staging'):
    """ Set dictionary values to environment. Run before every task.
    """
    env.dep_environment = environment_name
    for option, value in ENVIRONMENTS[env.dep_environment].items():
        setattr(env, option, value)

def hup(pidfile):
    run("kill -HUP `cat %s`" % pidfile)

def pack():
    # build the package
    # local('sh pre_prune.sh', capture=False)
    local('python setup.py sdist --formats=gztar', capture=False)

def dev_deploy(kill=False):
    set_environment('dev')

    # figure out the package name and version
    dist = local('python setup.py --fullname', capture=True).strip()
    filename = '%s.tar.gz' % dist

    # upload the package to the temporary folder on the server
    put('dist/%s' % filename, '/tmp/%s' % filename)

    # install the package in the application's virtualenv with pip
    run(env.target_dir + '/env/bin/pip install /tmp/%s' % filename)

    # remove the uploaded package
    run('rm -r /tmp/%s' % filename)

    # HUPPPPP
    hup(env.target_dir + '/uwsgi.wsgi.pid')

