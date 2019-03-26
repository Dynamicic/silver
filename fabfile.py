"""
"""


from fabric.api import *
from fabric.api import env, run, local, put, prefix, cd, settings
from fabric.contrib.project import rsync_project

# the user to use for the remote commands
# the servers where the commands are executed
env.hosts = [
    'silverproj'
]

env.use_ssh_config = True

ENVIRONMENTS = {
    'dev': {
        'user': 'root',
        'hosts': ['silverproj'],
        'staging_dir': '/root/deploy/silver.git',
        'target_dir': '/opt/sites/dev.billing.dynamicic.com',
    },
    'prod': {
        'user': '',
        'hosts': [''],
        'target_dir': '/TBD',
    }
}


def pretest():
    """ Test that everything can be installed in a temporary virtual
    environment, and then run antikythera's `make test`.
    """
    set_environment('dev')

    with cd(env.staging_dir):
        run('virtualenv -p python3.6 .envtmp')

        with prefix("source %s/.envtmp/bin/activate" % env.staging_dir):
            with cd('silver/'):
                run('python setup.py develop')
            with cd('silver-authorize/'):
                run('python setup.py develop')
            with cd('infra/antikythera/'):
                run('python setup.py develop')
                run('make test')

        # Clean up
        run('rm -rf .envtmp')

def prepare_deploy():
    set_environment('dev')

    # Build various packages files using a fresh virtualenv
    with cd(env.staging_dir):
        run('rm -rf .buildenv && virtualenv -p python3.6 .buildenv')

        with prefix("source %s/.buildenv/bin/activate" % env.staging_dir):

            run("rm -rf packages && mkdir packages")
            with cd('silver/'):
                run('python setup.py sdist --formats=gztar')
                run('mv dist/*.tar.gz ../packages/')
            with cd('silver-authorize/'):
                run('python setup.py sdist --formats=gztar')
                run('mv dist/*.tar.gz ../packages/')
            with cd('infra/antikythera/'):
                run('python setup.py sdist --formats=gztar')
                run('mv dist/*.tar.gz ../../packages/')

        # Clean up
        run('rm -rf .buildenv')


def deploy_build():
    """ Deploy the packages in $HOME/deploy/silver.git/packages/.

    NB: this deletes the virtualenv and recreates it. Once we get moving
    with actually versioning everything, this can be modified to do a
    hot or hot-ish install
    """

    set_environment('dev')

    # `prepare_deploy` has been run.
    with cd(env.target_dir):
        maintenance_on()
        run('rm -rf env && virtualenv -p python3.6 env')
        with prefix("source %s/env/bin/activate" % env.target_dir):
            # Install the staged packages.
            run("ls -c1 %s/packages/*.tar.gz | xargs -I {} pip install {}" % env.staging_dir)

            run("antikythera-manage collectstatic --noinput")
        maintenance_off()

def maintenance_on():
    set_environment('dev')
    with cd(env.target_dir):
        run('touch maintenance')

def maintenance_off():
    set_environment('dev')
    with cd(env.target_dir):
        run('rm maintenance')

def prod_migrations():
    set_environment('dev')
    with cd(env.target_dir):
        with prefix("source %s/env/bin/activate" % env.target_dir):
            run("antikythera-manage migrate --noinput silver")

def hup_services():
    set_environment('dev')
    with cd(env.target_dir):
        with prefix("source %s/env/bin/activate" % env.target_dir):
            hup(env.target_dir + '/uwsgi.wsgi.pid')
            # TODO: hup celery also


def set_environment(environment_name='dev'):
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

