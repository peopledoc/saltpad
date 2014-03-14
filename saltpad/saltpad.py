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
import operator

from salt.output.highstate import _format_host

from core import SaltStackClient

from time import sleep
from plumbum import cli, local, FG
from clint.eng import join as eng_join
from clint.textui import colored, puts, indent
from os import listdir, mkdir
from os.path import expanduser, isfile, join, isdir, split, abspath
from pprint import pformat
from jinja2 import Environment, meta
from shutil import copy
from vagrant import Vagrant, SandboxVagrant
from distutils.util import strtobool

def parse_step_name(step_name):
    splitted = step_name.replace('_|', '|').replace('|-', '|').split('|')
    return "{0}.{3}: '{2}' [id '{1}']:".format(*splitted)


def call(cmd):
    print cmd
    base_cmd = local
    for part in cmd.split():
        if '$' in part:
            part = local.env[part.replace('$', '')]
            for subpart in part.split():
                base_cmd = base_cmd[subpart]
        else:
            base_cmd = base_cmd[part]
    # Execute cmd in FG with tty redirection, ignore exit code
    base_cmd & FG(None)


def bool_choice(message):
    try:
        return strtobool(raw_input(message).lower())
    except ValueError:
        return 0


class SaltPad(cli.Application):
    VERSION = "0.0.1"

    def __init__(self, *args, **kwargs):
        super(SaltPad, self).__init__(*args, **kwargs)
        self.config_file = expanduser("~/.saltpad.json")

        if isfile(self.config_file):
            with open(self.config_file) as f:
                self.config = json.load(f)
        else:
            self.config = {}

        self.client = SaltStackClient()

    def main(self, *args):
        if args:
            print "Unknown command %r" % (args[0],)
            return 1   # error exit code
        if not self.nested_command:           # will be ``None`` if no sub-command follows
            print "No command given"
            return 1   # error exit code

    def write_config_file(self):
        with open(self.config_file, 'w') as f:
            json.dump(self.config, f)


@SaltPad.subcommand("register_dir")
class RegisterDir(cli.Application):

    def main(self, templates_directory):
        templates_directory = abspath(templates_directory)
        puts(colored.blue("Looking in %s for templates" %  templates_directory))

        # Check for VagrantFile template file
        vagrantfile_template = join(templates_directory, 'Vagrantfile.template')
        if isfile(vagrantfile_template):
            puts(colored.blue("Found a Vagrantfile template: %s" % vagrantfile_template))

            self.parent.config.setdefault('vagrantfiles', {})['default'] = vagrantfile_template
        else:
            puts(colored.yellow("No Vagrantfile template found: %s" % vagrantfile_template))

        # Check for minions configurations
        minions_conf = join(templates_directory, 'minions_configuration')
        if isdir(minions_conf):
            logging.info("Found a minion configuration directory: %s" % minions_conf)

            for filename in listdir(minions_conf):
                filepath = join(minions_conf, filename)
                puts(colored.blue("Found minion conf: %s" % filepath))

                self.parent.config.setdefault('minion_conf', {})[filename] = filepath
        else:
            puts(colored.yellow("No minion configuration directory found: %s" % minions_conf))

        # Write config file
        self.parent.write_config_file()


@SaltPad.subcommand("create_vm")
class CreateVm(cli.Application):

    def main(self, project_name):
        # Check directory
        project_path = abspath(project_name)
        if isdir(project_path):
            puts(colored.red("The directory %s already exists, abort" % project_path))
            sys.exit(1)

        # Choose minion configuration
        if len(self.parent.config.get('minion_conf', [])) == 0:
            puts(colored.red("You must register at least one minion configuration,"
                "use register_dir command to do so."))
            sys.exit(1)
        if len(self.parent.config.get('minion_conf', [])) == 1:
            minion_conf = self.parent.config['minion_conf'].values()[0]
        else:
            minion_list = sorted(self.parent.config['minion_conf'].keys())
            while True:
                puts(colored.blue("Please choose a minion configuration:"))
                for i, minion in enumerate(minion_list):
                    print "%s) %s" % (i, minion)
                try:
                    minion_conf = minion_list[int(raw_input("Your choice: "))]
                    break
                except IndexError, ValueError:
                    continue

            minion_conf = self.parent.config['minion_conf'][minion_conf]

        puts(colored.blue("Using %s as minion configuration" % minion_conf))

        # Prepare vagrant file

        # Choose vagrantfile
        if len(self.parent.config.get('vagrantfiles', {})) == 0:
            logging.error("You must register at least one Vagrantfile, use"
                "register_dir command to do so.")
            sys.exit(1)
        if len(self.parent.config.get('vagrantfiles', {})) == 1:
            vagrantfile = self.parent.config['vagrantfiles']['default']
        else:
            raise Exception("More than one Vagrantfile, TODO")

        puts(colored.blue("Using %s as VagrantFile template" % vagrantfile))

        # Get declared variables
        env = Environment()
        with open(vagrantfile) as f:
            vagrantfile_template = f.read()

        missing_variables = meta.find_undeclared_variables(env.parse(vagrantfile_template))
        missing_variables.remove('project_name')
        variables = {'project_name': project_name}

        if missing_variables:
            puts(colored.blue("Please enter VagrantFile template variables:"))

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
        puts(colored.blue("Generating keys for minion"))
        call("salt-key --gen-keys=%s --gen-keys-dir=%s" % (project_name, project_path))
        # Copy it on master
        call("cp %s/%s.pub /etc/salt/pki/master/minions/%s" % (project_path, project_name, project_name))

        # Register VM
        self.parent.config.setdefault('minions', {})[project_name] = project_path

        self.parent.write_config_file()

        puts(colored.blue("Done"))

        # Edition of minion configuration
        puts(colored.blue("Would you like to edit minion configuration?"))
        choice = bool_choice("Yes/No: ")

        if choice:
            call("$EDITOR %s" % join(project_path, minion))
            puts(colored.blue("Edition done"))

        # Done
        puts(colored.blue("Would you like to run vagrant up on VM?"))
        choice = bool_choice("Yes/No: ")

        if choice:
            VagrantUp.parent = self.parent
            VagrantUp.run(['up', project_name])



@SaltPad.subcommand("status")
class Status(cli.Application):

    def main(self):
        for minion_name, minion_path in self.parent.config.get('minions', {}).items():
            vagrant = Vagrant(minion_path)
            vagrant_status = vagrant.status()['default']
            salt_status = self.parent.client.get_minion_status(minion_name)
            puts("%s:" % minion_name)
            with indent(4):
                puts("vagrant status: %s" % vagrant_status)
                puts("saltstack status: %s" % salt_status)


class VagrantManagerMixin(object):

    def execute_vagrant_command_on_minion(self, project_name, command):
        minion_path = self.parent.config['minions'][project_name]
        vagrant = Vagrant(minion_path)

        puts(colored.blue("Execute vagrant %s on minion %s" % (command, project_name)))
        getattr(vagrant, command)(capture_output=False)

        puts(colored.blue("Done"))

@SaltPad.subcommand("up")
class VagrantUp(cli.Application, VagrantManagerMixin):

    def main(self, project_name):
        self.execute_vagrant_command_on_minion(project_name, 'up')

        # Check if sahara is available
        minion_path = self.parent.config['minions'][project_name]
        sandbox = SandboxVagrant(minion_path)
        sandbox_status = sandbox.sandbox_status()

        if sandbox_status == 'not installed':
            message = "Sandbox support is not available, please install sahara"\
                      " plugin with 'vagrant plugin install sahara'"
            puts(colored.yellow(message))
        else:
            if sandbox_status == 'on':
                puts(colored.blue("Snapshot is already enabled on VM"))
            else:
                puts(colored.blue("Would you like to enable snapshot on VM?"))
                choice = bool_choice("Yes/No: ")

                if choice:
                    puts(colored.blue("Starting snapshot"))
                    sandbox.sandbox_on()
                    puts(colored.blue("Done"))


@SaltPad.subcommand("halt")
class VagrantHalt(cli.Application, VagrantManagerMixin):

    def main(self, project_name):
        self.execute_vagrant_command_on_minion(project_name, 'halt')


@SaltPad.subcommand("destroy")
class VagrantDestroy(cli.Application, VagrantManagerMixin):

    def main(self, project_name):
        self.execute_vagrant_command_on_minion(project_name, 'destroy')


@SaltPad.subcommand("provision")
class VagrantProvision(cli.Application, VagrantManagerMixin):

    def main(self, project_name):
        self.execute_vagrant_command_on_minion(project_name, 'provision')


@SaltPad.subcommand("ssh")
class VagrantSSH(cli.Application):

    def main(self, project_name):
        minion_path = self.parent.config['minions'][project_name]
        with local.cwd(minion_path):
            call('vagrant ssh')


@SaltPad.subcommand("deploy")
class Deploy(cli.Application):

    clean = cli.Flag("--clean", default = False, help = "Clean VM before deploying it")

    def do_clean(self, project_name):
        minion_path = self.parent.config['minions'][project_name]
        sandbox = SandboxVagrant(minion_path)
        sandbox_status = sandbox.sandbox_status()

        # If sandbox is activated, rollback only
        if sandbox_status == 'on':
            message = "Rollback snapshot, if you will delete snapshot, use "\
                      "--force-clean option"
            puts(colored.blue(message))
            sandbox.sandbox_rollback()
            puts(colored.blue("Done"))

            puts(colored.blue("Wait some time for salt-minion to connect"))
            sleep(5)
        # Else destroy and up
        else:
            # Destroy
            VagrantDestroy.parent = self.parent
            VagrantDestroy.run(['destroy', project_name])

            # Up
            VagrantUp.parent = self.parent
            VagrantUp.run(['up', project_name])



    def main(self, project_name):
        # Clean
        if self.clean:
            self.do_clean(project_name)

        # Deploy
        minions = self.parent.client.cmd(project_name, 'test.ping')

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
            puts(colored.blue("Roles: %s" % eng_join(self.parent.client.minions_roles()[minion], im_a_moron=True)))

            puts()
            puts(colored.blue("Execute state.highstate"))

            result = self.parent.client.cmd(minion, 'state.highstate',
                timeout=9999999999)[minion]
            success = self.parse_result(result)

            if not success:
                puts()
                puts(colored.red("Deployment has failed on %s minion, abort!"
                                 % minion))
                sys.exit(1)

            # Do orchestration
            # orchestration_result = self.parent.client.orchestrate(minion)
            # print "orchestration_result", orchestration_result

            # Call health-checks
            health_checks_result = self.parent.client.cmd(minion,
                'state.top', 'healthcheck_top.sls', timeout=9999999999)[minion]
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

@SaltPad.subcommand("healthchecks")
class Healthchecks(cli.Application):

    def main(self, target):
        puts(colored.blue("Starting deployment on %s" % target))
        health_checks_result = self.parent.client.cmd(target,
                'state.top', 9999999999, 'healthcheck_top.sls')
        print output(health_checks_result)
        puts(colored.blue("Done"))


def main():
    SaltPad.run()


if __name__ == '__main__':
    main()
