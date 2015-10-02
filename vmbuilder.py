#!/usr/bin/env python

import argparse
import libvirt
import logging
import subprocess
import sys

import ubuntu

# TODO: Config file for defaults/assumptions?
# Figure out better way to not run virsh commands? all libvirt api? how does dry run work?
# FIX: Error in creating disk image: error: command 'vol-create-as' doesn't support option --connect

class HandledException(Exception):
    pass

class VMBuilder(object):

    def __init__(self):
        self.args = self.parseArgs()
        self.conn = self.getConn()
        self.build = None
        self.flags = None

    def getConn(self):
        if hasattr(self, 'conn'):
            return self.conn

        self.conn = libvirt.open("qemu+ssh://%s/system" % self.args.vm_host)
        return self.conn

    def getDiskPools(self):
        """Return list of disk pools on VM host."""
        return [current.name() for current in self.conn.listAllStoragePools()]

    def getNetworkInterfaces(self):
        """Return a list of viable network interfaces to connect to."""
        return self.conn.listInterfaces()

    def getVMList(self):
        domains = []
        # VMs that are not running
        for current in self.conn.listDefinedDomains():
            domains.append(current)
        # VMs that are currently running on the host
        for current in self.conn.listDomainsID():
            domains.append(self.conn.lookupByID(current).name())
        return domains


    def parseArgs(self):
        parser = argparse.ArgumentParser()
        parser.add_argument('command',
                            type=str,
                            choices=['create_vm',
                                     'list_disk_pools',
                                     'list_network_interfaces'])
        parser.add_argument("--bridge_interface",
                            help=("NIC/VLAN to bridge."
                                  "See command list_network_interfaces"))
        parser.add_argument("--cpus",
                            type=int,
                            default=1,
                            help="Number of CPUs. Default: %(default)d")
        parser.add_argument("--debug",
                            action="store_true",
                            help="Display debug output when executing virt-install.")
        parser.add_argument("--deleteifexists",
                            action="store_true",
                            help="Delete VM data store and configuration if it exists.")
        parser.add_argument("--disk_pool_name",
                            help=("Disk pool for VM disk image storage."
                            "See command list_disk_pools"))
        parser.add_argument("--disk_size_gb",
                            default=10,
                            type=int,
                            help="Default size of hard disk image, in GB. Default: %(default)d")
        parser.add_argument("--domain_name",
                            default="server.boston.jeffreyforman.net",
                            help="Domain name the VM upon creation. Default: %(default)s")
        parser.add_argument("--dry_run",
                            action="store_true",
                            help="Don't actually do anything, but print out what would have been done.")
        parser.add_argument("--host_name",
                           help="Virtual Machine Hostname")
        parser.add_argument("--ip_address",
                            default=None,
                            help="Static IP address for VM.")
        # TODO: Figure out a way to programatically make releases a choice
        parser.add_argument("--location",
                            help="URL to installation source. Default: %(default)s",
                            default="http://mirror.uoregon.edu/ubuntu/dists/utopic/main/installer-amd64/")
        parser.add_argument("--memory",
                           type=int,
                           default=512,
                           choices=[512, 1024, 2048, 4096, 8192],
                           help="Amount of RAM, in MB. Default: %(default)d")
        parser.add_argument("--vm_host",
                            default="localhost",
                            help="VM host system to connect to for creating VM guest. Default: %(default)s")
        parser.add_argument("--vm_type",
                            choices=["coreos", "ubuntu"],
                            help="Type of VM you wish to create.")
        args = parser.parse_args()
        return args

    def createDiskImage(self):
        """Attempt to create a qcow2 disk image."""

        vm_name = "%s.%s" % (self.args.host_name, self.args.domain_name)
        command_line = ["/usr/bin/virsh", "vol-create-as"]
        # TODO: Make work command_line.extend(["--connect", "qemu+ssh://%s/system" % args.vm_host])
        command_line.extend(["--pool", self.args.disk_pool_name])
        command_line.extend(["--name", "%s" % vm_name])
        command_line.extend(["--capacity", "%dG" % self.args.disk_size_gb])
        command_line.extend(["--format", "qcow2"])
        command_line.extend(["--prealloc-metadata"])

        if self.args.debug:
            logging.debug("Create disk image command line: %s", command_line)

        if self.args.dry_run:
            logging.info("DRYRUN: No disk image was created.")
            return

        try:
            output = subprocess.check_output(command_line,
                                             stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            logging.error("Error in creating disk image: %s.", err.output)
            raise

        logging.info("Disk image created successfully. Output: %s", output)

    def normalizeVMState(self):
        """Perform presence checks on disk image and VM itself.
        If disk image and VM exist already, error out.

        If disk image and VM exist already, and --deleteifexists flag is passed,
        delete both and proceed in a 'clean' state."""

        vm_list = self.getVMList()
        pool_volumes = [x.name() for x in self.conn.storagePoolLookupByName(
            self.args.disk_pool_name).listAllVolumes()]
        vm_name = "%s.%s" % (self.args.host_name, self.args.domain_name)

        logging.info("Checking if a previous disk image for this host already exists.")
        logging.debug("Pool %s volumes: %s", self.args.disk_pool_name,
            pool_volumes)
        if vm_name in pool_volumes:
            logging.info("Disk image for this VM already exists.")
            if self.args.deleteifexists:
                logging.info("Deleteifexists flag passed, deleting VM disk image.")
                if self.args.dry_run:
                    logging.info("DRY RUN: Disk image not actually deleted.")
                else:
                    self.conn.storagePoolLookupByName(self.args.disk_pool_name).storageVolLookupByName(vm_name).delete()
                    logging.info("VM disk image deleted.")
                # TODO: Handle errors where the delete fails.
            else:
                logging.error("Flag --deleteifexists NOT passed. Not deleting " +
                              "an existing VM disk image.")
                raise HandledException

        if vm_name not in vm_list:
            logging.info("VM %s not already defined.", vm_name)
            return False

        if self.args.deleteifexists:
            if self.args.dry_run:
                logging.info("DRYRUN: Would have deleted both VM " +
                             "and its data stores.")
                return

            if self.conn.lookupByName(vm_name).isActive():
                self.conn.lookupByName(vm_name).destroy()
            self.conn.lookupByName(vm_name).undefine()
            return

        # TODO: implement/test that this actually throws an exception
        logging.exception("VM %s already exists and --deleteifexists " +
                          "flag not passed to delete if present.", vm_name)

    def executeVirtInstall(self):
        command_line = ["/usr/bin/virt-install", "--autostart"]
        for flag, value in self.flags.iteritems():
            command_line.extend(["--%s" % flag, str(value)])
            logging.debug("flag/type: %s/%s, value/type: %s/%s",
                          flag, type(flag), value, type(value))

        str_command_line = " ".join(command_line)
        logging.debug("virt-install command line: %s", str_command_line)

        if self.args.dry_run:
            logging.info("DRYRUN: VM not actually created. Skipping.")
            return

        try:
            subprocess.call(str_command_line,
                            stderr=subprocess.STDOUT,
                            shell=True)
            pass
        except subprocess.CalledProcessError as err:
            logging.error("virt-install cmd: %s", err.cmd)
            logging.exception("virt-install output: %s", err.output)

        return


    def createVM(self):
        logging.info("Starting VM build for %s.%s.", self.args.host_name,
                    self.args.domain_name)

        self.normalizeVMState()
        self.createDiskImage()
        self.executeVirtInstall()
        logging.info("VM %s.%s creation is complete.", self.args.host_name,
                    self.args.domain_name)

    def createVMBuilderObject(self):
        if self.args.vm_type == "ubuntu":
            self.build = ubuntu.Ubuntu()
        else:
            logging.fatal("Your vm_type is not supported.")
            raise HandledException

def main():
    """Main function for handling VM and disk creation."""

    vm = VMBuilder()

    if vm.args.debug:
        log_level = logging.DEBUG
    else:
        log_level = logging.INFO

    logging.basicConfig(level=log_level,
                        format="%(asctime)s %(levelname)s: %(message)s")

    if vm.args.command == 'list_disk_pools':
        print vm.getDiskPools()
    elif vm.args.command == 'list_network_interfaces':
        print vm.getNetworkInterfaces()
    elif vm.args.command == 'create_vm':
        vm.createVMBuilderObject()
        vm.build.composeVirtinstallArgs()
        vm.build.createVM()
    else:
        logging.fatal("The command you entered is not recognized.")

if __name__ == "__main__":
    try:
        sys.exit(main())
    except HandledException:
        logging.error("Exiting from handled exception.")
        sys.exit(1)
    except Exception as err:
        logging.exception(err)
