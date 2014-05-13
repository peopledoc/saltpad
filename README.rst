===============================
SaltPad
===============================


.. image:: https://travis-ci.org/novapost/saltpad.png?branch=master
        :target: https://travis-ci.org/novapost/saltpad

.. image:: https://pypip.in/d/saltpad/badge.png
        :target: https://crate.io/packages/saltpad?version=latest


SaltPad is a GUI and CLI tool to manage saltstack deployments + orchestration.

* Documentation: http://saltpad.rtfd.org.

Features
--------

Saltpad is a thin layer on top of Saltstack which helps manage:

* Deployments via state.highstate
* Orchestration via the orchestrate runner.
* HealthChecks, or Smoke Tests, via state.top.
* Vagrant VMs deployed with SaltStack.

Saltpad provides 3 interfaces:

* A web interface for deployments, orchestration and healthchecks.
* A cli interface for deployments, orchestration and healthchecks, it's the saltpad cli command.
* A cli interface for managing Vagrant VMs, it's the saltpad-vagrnat cli command.

Interfaces
----------


Saltpad
-------

Saltpad is the main cli interface, it calls directly salt-master to do his job. It exposes two sub-commands:

* healthchecks, run healthchecks on minions matching target. Call state.top with healthcheck_top.sls as top file, see writing healthchecks part for more details.
* deploy, call state.highstate + healthchecks on minions matching target.

Saltpad Vagrant
---------------

Saltpad vagrant helps you manage / create / recreate / deploy vagrant VMs.

It shares the same commands than saltpad, but add a few more:

One command to help VM creation:

* create_vm

Some commands matching vagrant ones:

* destroy
* halt
* up
* ssh
* provision

One command to register templates:

* register_dir

Saltpad GUI
-----------

The web-interface, still in development.
