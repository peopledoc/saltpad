#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""SaltStack Orchestration Tool.

Usage:
  saltpad register_dir DIRECTORY_OF_TEMPLATES
  saltpad create_vm PROJECT_NAME
  saltpad status
  saltpad up PROJECT_NAME
  saltpad destroy PROJECT_NAME
  saltpad deploy PROJECT_NAME
  saltpad [--ignore-down-minions]
  saltpad (-h | --help)
  saltpad --version

Options:
  -h --help     Show this screen.
  --version     Show version.
  --ignore-down-minions  Ignore down minions, usefull for dev.

"""
import os
import sys
import json
import logging
import subprocess

from core import SaltStackClient

from docopt import docopt
from itertools import chain
from clint.eng import join as eng_join
from clint.textui import colored, puts, indent
from os import listdir, mkdir
from os.path import expanduser, isfile, join, isdir, split, abspath
from pprint import pformat
from jinja2 import Environment, meta
from shutil import copy
from vagrant import Vagrant

def parse_step_name(step_name):
    splitted = step_name.replace('_|', '|').replace('|-', '|').split('|')
    return "{0}.{3}: '{2}' [id '{1}']:".format(*splitted)


def call(cmd):
    print cmd
    subprocess.call(cmd, shell=True)


class BaseObject(object):

    def __init__(self):
        self.config_file = expanduser("~/.saltpad.json")

        if isfile(self.config_file):
            with open(self.config_file) as f:
                self.config = json.load(f)
        else:
            self.config = {}

        self.client = SaltStackClient()

    def write_config_file(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f)


class Register(BaseObject):

    def __init__(self, options):
        super(Register, self).__init__()
        self.options = options

        if self.options['register_dir'] is True:
            self.register_dir()

    def register_dir(self):
        base_dir = abspath(self.options['DIRECTORY_OF_TEMPLATES'])

        logging.info("Looking in %s for templates", base_dir)

        # Check for VagrantFile template file
        vagrantfile_template = join(base_dir, 'Vagrantfile.template')
        if isfile(vagrantfile_template):
            logging.info("Found a Vagrantfile template: %s", vagrantfile_template)

            self.config.setdefault('vagrantfiles', {})['default'] = vagrantfile_template
        else:
            logging.warning("No Vagrantfile template found: %s", vagrantfile_template)

        # Check for minions configurations
        minions_conf = join(base_dir, 'minions_configuration')
        if isdir(minions_conf):
            logging.info("Found a minion configuration directory: %s", minions_conf)

            for filename in listdir(minions_conf):
                filepath = join(minions_conf, filename)
                logging.info("Found minion conf: %s", filepath)

                self.config.setdefault('minion_conf', {})[filename] = filepath
        else:
            logging.warning("No minion configuration directory found: %s", minions_conf)

        # Write config file
        self.write_config_file()


class VMManager(BaseObject):

    def __init__(self, options):
        super(VMManager, self).__init__()
        self.options = options

        if self.options['create_vm'] is True:
            self.create_vm()
        if self.options['status'] is True:
            self.status()
        if self.options['up'] is True:
            self.up()
        if self.options['destroy'] is True:
            self.destroy()

    def create_vm(self):
        project_name = self.options['PROJECT_NAME']

        # Choose minion configuration
        if len(self.config.get('minion_conf', [])) == 0:
            puts(colored.red("You must register at least one minion configuration,"
                "use register_dir command to do so."))
            sys.exit(1)
        if len(self.config.get('minion_conf', [])) == 1:
            minion_conf = self.config['minion_conf'].values()[0]
        else:
            raise Exception("More than one minion configuration, TODO")

        # Check directory
        project_path = abspath(project_name)
        if isdir(project_path):
            logging.error("The directory %s alread exists, abort", project_path)

        # Prepare vagrant file

        # Choose vagrantfile
        if len(self.config.get('vagrantfiles', {})) == 0:
            logging.error("You must register at least one Vagrantfile, use"
                "register_dir command to do so.")
            sys.exit(1)
        if len(self.config.get('vagrantfiles', {})) == 1:
            vagrantfile = self.config['vagrantfiles']['default']
        else:
            raise Exception("More than one Vagrantfile, TODO")

        # Get declared variables
        env = Environment()
        with open(vagrantfile) as f:
            vagrantfile_template = f.read()

        missing_variables = meta.find_undeclared_variables(env.parse(vagrantfile_template))
        missing_variables.remove('project_name')
        variables = {'project_name': project_name}

        # Prompt them
        for variable_name in missing_variables:
            variables[variable_name] = raw_input("%s: " % variable_name)

        # Render vagrantfile
        rendered_vagrantfile = env.from_string(vagrantfile_template).render(variables)


        # Create directory
        mkdir(project_path)
        copy(minion_conf, join(project_path, 'minion'))
        with open(join(project_path, 'Vagrantfile'), 'w') as f:
            f.write(rendered_vagrantfile)
        # Generate keys
        call("sudo salt-key --gen-keys=%s --gen-keys-dir=%s" % (project_name, project_path))
        call("sudo chmod 777 %s/%s.*" % (project_path, project_name))
        # Copy it on master
        call("sudo cp %s/%s.pub /etc/salt/pki/master/minions/%s" % (project_path, project_name, project_name))

        # Register VM
        self.config.setdefault('minions', {})[project_name] = project_path

        self.write_config_file()

    def status(self):
        for minion_name, minion_path in self.config.get('minions', {}).items():
            vagrant = Vagrant(minion_path)
            vagrant_status = vagrant.status()['default']
            salt_status = self.client.get_minion_status(minion_name)
            puts("%s:" % minion_name)
            with indent(4):
                puts("vagrant status: %s" % vagrant_status)
                puts("saltstack status: %s" % salt_status)

    def up(self):
        project_name = self.options['PROJECT_NAME']
        minion_path = self.config['minions'][project_name]
        vagrant = Vagrant(minion_path)
        puts(colored.blue("Current %s vagrant status: %s" % (project_name, vagrant.status()['default'])))

        puts(colored.blue("Execute vagrant up on minion %s" % project_name))
        vagrant.up(capture_output=False)

        puts(colored.blue("Done"))
        puts(colored.blue("New vagrant status: %s" % (vagrant.status()['default'])))
        puts(colored.blue("Saltstack status: %s" % (self.client.get_minion_status(project_name))))

    def destroy(self):
        project_name = self.options['PROJECT_NAME']
        minion_path = self.config['minions'][project_name]
        vagrant = Vagrant(minion_path)

        puts(colored.blue("Execute vagrant destroy on minion %s" % project_name))
        vagrant.destroy(capture_output=False)

        puts(colored.blue("Done"))
        puts(colored.blue("New vagrant status: %s" % (vagrant.status()['default'])))


class SaltManager(BaseObject):

    def __init__(self, options):
        super(SaltManager, self).__init__()

        self.options = options

        if self.options['deploy'] is True:
            self.deploy()

    def deploy(self):
        project_name = self.options['PROJECT_NAME']
        minions = self.client.cmd(project_name, 'test.ping')

        if len(minions) == 0:
            puts(colored.red("No up minions matching, abort!"))
            sys.exit(1)

        print "Minions", minions

        bad_minions = []
        for minion, minion_status in minions.items():
            if not minion_status:
                bad_minions.append((minion, minion_status))
        if bad_minions:
            puts(colored.red("Could not deploy on theses minions statuses:"))
            with indent(2):
                for minion_tuple in bad_minions:
                    puts(colored.red('* %s status: %s' %  minion_tuple))

        puts(colored.blue("Starting deployment on %s" % eng_join(minions.keys(), im_a_moron=True)))

        for minion in minions:
            puts(colored.blue("=" * 10))
            puts(colored.blue("Minion: %s" % minion))
            puts(colored.blue("Roles: %s" % eng_join(self.client.minions_roles()[minion], im_a_moron=True)))

            puts()
            puts(colored.blue("Execute state.highstate"))

            result = self.client.cmd(minion, 'state.highstate',
                timeout=9999999999)[minion]
            success = self.parse_result(result)

            if not success:
                puts()
                puts(colored.red("Deployment has failed on %s minion, abort!"
                                 % minion))
                sys.exit(1)

            # Do orchestration
            orchestration_result = self.client.orchestrate(minion)
            print "orchestration_result", orchestration_result

            # Call health-checks
            health_checks_result = self.client.health_check(minion)
            print "health_check", health_checks_result

        puts()
        puts(colored.green("Deployment success on all minions!"))

    def format_result(self, step_name, step, color_function):
        puts(color_function("-" * 10))
        puts(color_function(parse_step_name(step_name)))
        with indent(4):
            puts(color_function("Comment: {0}".format(step['comment'])))
            if step['changes']:
                if not isinstance(step['changes'], dict):
                    puts(color_function("Changes: {0}".format(step['changes'])))
                    return
                if step['changes'].get('stderr') or step['changes'].get('stdout'):
                    puts(color_function("Changes:"))
                    puts(color_function("Stdout:"))
                    with indent(4):
                        puts(color_function(step['changes'].get('stdout', '')))
                    puts(color_function("Stderr:"))
                    with indent(4):
                        puts(color_function(step['changes'].get('stderr', '')))
                    pass
                else:
                    puts(color_function("Changes: {0}".format(pformat(step['changes']))))

    def parse_result(self, result):
        success = 0
        failure = 0
        changes = 0
        dependencies = 0
        if not isinstance(result, dict):
            puts(colored.red(result[0]))
            return

        for step_name, step in result.iteritems():
            if isinstance(step, list):
                puts(colored.red(step[0]))
                return
            if step.get('result'):
                if step['result']:
                    success += 1
                if step['changes']:
                    changes += 1
                    self.format_result(step_name, step, colored.blue)
            else:
                failure += 1
                if step['comment'] == 'One or more requisite failed':
                    dependencies += 1
                else:
                    self.format_result(step_name, step, colored.red)
        total = success + failure + dependencies

        if not failure:
            puts(colored.green("All {0} step OK, {1} changes".format(total, changes)))
            return True
        else:
            puts(colored.red("{0} steps, {1} failures, {4} dependencies failed, {2} OK, {3} changes".format(
                total, failure, success, changes, dependencies)))
            return False


def dispatcher(options):
    if options['register_dir'] is True:
        Register(options)
    elif options['create_vm'] is True:
        VMManager(options)
    elif options['status'] is True:
        VMManager(options)
    elif options['up'] is True:
        VMManager(options)
    elif options['destroy'] is True:
        VMManager(options)
    elif options['deploy'] is True:
        SaltManager(options)
    else:
        raise Exception(options)


if __name__ == '__main__':
    arguments = docopt(__doc__, version='SaltPad 0.0.1')
    dispatcher(arguments)
