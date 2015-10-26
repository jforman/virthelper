#!/usr/bin/env python
"""A helpful wrapper for using libvirt to create virtual machines."""
import argparse
from bs4 import BeautifulSoup
import libvirt
import logging
import os
import subprocess
import sys

import vmtypes

class HandledException(Exception):
    """General exception for known cases of building VM."""
    pass

class VMBuilder(object):
    """Class to marshall build of a VM."""

    def __init__(self):
        self.args = self.parseArgs()
        self.configureLogging()
        self.conn = None
        self.build = None
        self.flags = {}
        self.vm_name = "%s.%s" % (self.args.host_name,
                                  self.args.domain_name)
        self.vm_disk_image = "%s.qcow2" % self.vm_name
        self.pool_path = None


    def configureLogging(self):
        """Configure logging level."""
        if self.args.debug:
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO

        logging.basicConfig(level=log_level,
                            format="%(asctime)s %(levelname)s: %(message)s")

    def getBuild(self):
        """Create or return vm builder object."""
        if self.build:
            return self.build

        if self.args.vm_type == 'ubuntu':
            self.build = vmtypes.Ubuntu()
        elif self.args.vm_type == 'coreos':
            self.build = vmtypes.CoreOS()
        elif self.args.vm_type == 'debian':
            self.build = vmtypes.Debian()

        return self.build

    def getConn(self):
        """Create or return libvirt connection to VM host."""
        if self.conn:
            return self.conn
        self.conn = libvirt.open("qemu+ssh://%s/system" % self.args.vm_host)
        return self.conn

    def getDiskPools(self):
        """Return list of disk pools on VM host."""
        return [current.name() for current in
                self.getConn().listAllStoragePools()]

    def getPoolPath(self):
        """Return the absolute path for the VM's disk pool."""
        if self.pool_path:
            return self.pool_path

        command_line = ["/usr/bin/virsh", "pool-dumpxml",
                        self.args.disk_pool_name]
        try:
            output = subprocess.check_output(command_line,
                                             stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            logging.error("Error in creating disk image: %s.", err.output)
            raise
        soup = BeautifulSoup(output)
        self.pool_path = soup.target.path.string
        return self.pool_path

    def getPoolVolumes(self, pool):
        """Return list of all volumes in a disk pool."""
        volumes = [x.name() for x in self.getConn().storagePoolLookupByName(
            pool).listAllVolumes()]
        return volumes

    def getNetworkInterfaces(self):
        """Return a list of viable network interfaces to connect to."""
        return self.getConn().listInterfaces()

    def getDefinedVMs(self):
        """Return list of all VM names on a VM host."""
        domains = [x.name() for x in self.getConn().listAllDomains()]
        return domains

    @classmethod
    def parseArgs(cls):
        """Parse and return command line flags."""
        parser = argparse.ArgumentParser()
        commands = parser.add_argument_group('commands')
        commands.add_argument('command',
                              type=str,
                              choices=['create_vm',
                                       'list_disk_pools',
                                       'list_network_interfaces'])
        vm_props = parser.add_argument_group('vm properties')
        vm_props.add_argument("--bridge_interface",
                              help=("NIC/VLAN to bridge."
                                    "See command list_network_interfaces"))
        vm_props.add_argument("--cpus",
                              type=int,
                              default=1,
                              help="Number of CPUs. Default: %(default)d")
        vm_props.add_argument("--disk_size_gb",
                              default=10,
                              type=int,
                              help="Size (GB) of disk image. Default: %(default)d")
        vm_props.add_argument("--domain_name",
                              default="wired.boston.jeffreyforman.net",
                              help="VM domain name. Default: %(default)s")
        vm_props.add_argument("--memory",
                              type=int,
                              default=512,
                              choices=[512, 1024, 2048, 4096, 8192],
                              help="Amount of RAM, in MB. Default: %(default)d")
        vm_props.add_argument("--disk_pool_name",
                              help=("Disk pool for VM disk image storage."
                                    "See command list_disk_pools"))
        vm_props.add_argument("--vm_type",
                              choices=["coreos", "debian", "ubuntu"],
                              help="Type of VM you wish to create.")
        vm_props.add_argument("--host_name",
                              help="Virtual Machine Hostname")
        vm_props.add_argument("--dist_location",
                              help="Installation source. URL Default: %(default)s",
                              default=("ftp://debian.csail.mit.edu/debian/"
                                       "dists/jessie/main/installer-amd64/"))

        vm_host_props = parser.add_argument_group('vm host properties')
        vm_host_props.add_argument("--vm_host",
                                   default="localhost",
                                   help="VM host. Default: %(default)s")

        parser.add_argument("--debug",
                            action="store_true",
                            help="Display debug output when executing virt-install.")
        parser.add_argument("--deleteifexists",
                            action="store_true",
                            help="Delete VM data store and configuration if it exists.")
        parser.add_argument("--dry_run",
                            action="store_true",
                            help=("Don't execute commands, only print out "
                                  "what would have been done."))

        coreos_args = parser.add_argument_group('coreos vm properties')
        coreos_args.add_argument("--coreos_channel",
                                 choices=['stable', 'beta', 'alpha'],
                                 default='stable',
                                 help=("Channel of CoreOS image to use as VM base. "
                                       "Default: %(default)s."))
        coreos_args.add_argument("--coreos_image_age",
                                 default=7,
                                 help=("Age (days) of CoreOS base image before "
                                       "downloading a new one. Default: %(default)s"))
        coreos_args.add_argument("--coreos_cloud_config_template",
                                 default=os.path.join(
                                     os.path.dirname(
                                         os.path.realpath(__file__)),
                                     "coreos_user_data.template"),
                                 help=("Mako template for CoreOS cloud config "
                                       "user_data. Default: %(default)s"))

        # parser.add_argument("--ip_address",
        #                     default=None,
        #                     help="Static IP address for VM.")
        # TODO: Figure out a way to programatically make releases a choice
        args = parser.parse_args()
        return args

    def createDiskImage(self):
        """Create a qcow2 disk image."""
        # TOOD: Figure out an API-ish way to create volume since
        #  vol-create-as does not support providing a --connect flag
        #  (["--connect", "qemu+ssh://%s/system" % self.args.vm_host])

        command_line = ["/usr/bin/virsh", "vol-create-as"]
        command_line.extend(["--pool", self.args.disk_pool_name])
        command_line.extend(["--name", self.vm_disk_image])
        command_line.extend(["--capacity", "%dG" % self.args.disk_size_gb])
        command_line.extend(["--format", "qcow2"])
        command_line.extend(["--prealloc-metadata"])

        logging.debug("Create disk image command line: %s", command_line)

        if self.args.dry_run:
            logging.info("DRYRUN: No disk image was created.")
            return

        try:
            # NO shell=true here.
            output = subprocess.check_output(command_line,
                                             stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            logging.error("Error in creating disk image: %s.", err.output)
            raise
        logging.info("Disk image created successfully.")
        logging.debug("Disk image creation output: %s", output)

    def deleteVMImage(self):
        """Delete a VM's disk image."""
        logging.debug("Pool %s volumes: %s",
                      self.args.disk_pool_name,
                      self.getPoolVolumes(self.args.disk_pool_name))

        logging.info("Checking for pre-existing disk image for this VM.")
        if self.vm_disk_image not in self.getPoolVolumes(self.args.disk_pool_name):
            logging.info("VM image does not exist for VM. Nothing to delete.")
            return

        logging.info("Attempting to delete image in pool %s for vm %s.",
                     self.args.disk_pool_name,
                     self.vm_name)
        if self.args.dry_run:
            logging.info("DRY RUN: Disk image not actually deleted.")
            return

        if not self.args.deleteifexists:
            logging.error("VM image found for host, but --deleteifexists flag "
                          "not passed.")
            raise HandledException
        self.getConn().storagePoolLookupByName(
            self.args.disk_pool_name).storageVolLookupByName(self.vm_disk_image).delete()
        logging.info("Finished deleting VM image for VM.")

    def deleteVM(self):
        """Stop and delete the VM."""
        if self.args.dry_run:
            logging.info("DRY RUN: VM would have been deleted here.")
            return

        if self.vm_name not in self.getDefinedVMs():
            logging.info("VM does not already exist.")
            return

        logging.info("Found existing VM with same name.")
        if not self.args.deleteifexists:
            logging.error("VM image found, but --deleteifexists "
                          "flag not passed.")
            raise HandledException

        if self.getConn().lookupByName(self.vm_name).isActive():
            self.getConn().lookupByName(self.vm_name).destroy()
        self.getConn().lookupByName(self.vm_name).undefine()

    def normalizeVMState(self):
        """Delete pre-existing VM and disk image if desired.

        If args.deleteifexists, delete VM and disk image.
        Else raise error.
        """

        self.deleteVM()
        self.deleteVMImage()

    def executeVirtInstall(self):
        """Execute virt-install with vm-specific flags."""
        command_line = ["/usr/bin/virt-install", "--autostart",
                        "--nographics",
                        '--console pty,target_type=serial']
        if self.args.debug:
            command_line.extend(["--debug"])

        self.flags.update({
            "connect": "qemu+ssh://%s/system" % self.args.vm_host,
            "disk": "vol=%s/%s,cache=none" % (self.args.disk_pool_name,
                                              self.vm_disk_image),
            "name": self.vm_name,
            "network": "bridge=%s,model=virtio" % self.args.bridge_interface,
            "os-type": "unix",
            "ram": self.args.memory,
            "vcpus": self.args.cpus,
            "virt-type": "kvm",
        })

        self.flags.update(self.getBuild().getVirtInstallCustomFlags())
        extra_args = self.getBuild().getVirtInstallExtraArgs()
        if extra_args:
            logging.debug("Found extra-args for virt-install.")
            self.flags.update({'extra-args': extra_args})

        for flag, value in self.flags.iteritems():
            command_line.extend(["--%s" % flag, str(value)])
            logging.debug("flag: %s, value: %s",
                          flag, value)

        str_command_line = " ".join(command_line)
        logging.debug("virt-install command line: %s", str_command_line)

        if self.args.dry_run:
            logging.info("DRYRUN: VM not actually created. Skipping.")
            return

        self.getBuild().executePreVirtInstall()
        subprocess.call(str_command_line,
                        stderr=subprocess.STDOUT,
                        shell=True)
        self.getBuild().executePostVirtInstall()

    def createVM(self):
        """Main execution handler for the script."""
        logging.info("Starting VM build for %s.%s.", self.args.host_name,
                     self.args.domain_name)

        self.normalizeVMState()
        self.createDiskImage()
        self.executeVirtInstall()
        logging.info("VM %s.%s creation is complete.", self.args.host_name,
                     self.args.domain_name)


def main():
    """Main function for handling VM and disk creation."""

    vm = VMBuilder()

    if vm.args.command == 'list_disk_pools':
        print vm.getDiskPools()
    elif vm.args.command == 'list_network_interfaces':
        print vm.getNetworkInterfaces()
    elif vm.args.command == 'create_vm':
        vm.getBuild().createVM()
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
