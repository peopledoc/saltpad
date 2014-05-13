============
Installation
============

At the command line::

    $ pip install saltpad

Or grab the deb package here: TODO FIXME

Salt installation
-----------------

SaltPad doesn't support yet the salt-api so it requires that saltpad is installed on the same computer than salt-master.

For the saltstack installation, please follow official installations instructions here: `http://docs.saltstack.com/en/latest/topics/installation/index.html <http://docs.saltstack.com/en/latest/topics/installation/index.html>`_.

For local developpement environment and saltpad-vagrant it's recommended to launch SaltStack as your current user using instructions located here: `http://docs.saltstack.com/en/latest/ref/configuration/nonroot.html <http://docs.saltstack.com/en/latest/ref/configuration/nonroot.html>`_.

If you didn't configure SaltStack to be launched with your user, you may need to use sudo for running saltpad and saltpad-vagrant.

If you want to install saltpad in a virtualenv and you installed SaltStack with debian packaging for example, do not forget the "--system-site-packages" option when creating the virtualenv, otherwise saltpad will not have access to salt package.

You can check that everything works correctly by launching this command: "saltpad-vagrant status".
