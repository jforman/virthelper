#!/usr/bin/env python
"""A helpful wrapper for using libvirt to create virtual machines."""
import argparse
from bs4 import BeautifulSoup
# TOOD(jforman): Figure out how to run script without libvirt locally.
# Are there usecases?
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

    build = None
    conn = None
    pool_path = None
    vm_hostname = None

    def __init__(self):
        self.args = self.parseArgs()
        self.configureLogging()

    def setArgs(self):
        self.args = self.parseArgs()

    def getVmHost(self):
        return self.args.vm_host

    def getVmHostNameArg(self):
        """Return host_name argument from command line."""
        return self.args.host_name

    def setVmHostName(self, host_name, host_index, cluster_size):
        """Return indexed hostname based upon name and index.

        If the cluster_size is 1, just return the hostname.
        There is no reason to index a hostname if there is only one.
        """
        if cluster_size == 1:
            VMBuilder.vm_hostname = host_name
            return

        host_name = host_name.split(".")[0]
        newname = "%s%d" % (host_name, host_index)
        VMBuilder.vm_hostname = newname

    def getVmHostName(self):
        """Return host name of VM."""
        return VMBuilder.vm_hostname

    def getVmName(self):
        """Return FQDN of VM."""
        return "%s.%s" % (self.getVmHostName(), self.getVmDomainName())

    def getVmDiskImageName(self):
        """Given a VM name, return the disk image base name."""
        return "%s.qcow2" % self.getVmName()

    def getVmDomainName(self):
        """Return domain name of VM."""
        return self.args.domain_name

    def getVmDiskImagePath(self):
        return os.path.join(self.getDiskPoolPath(),
                            self.getVmDiskImageName())

    def getDiskPoolName(self):
        """Return name of disk pool VM lives on."""
        return self.args.disk_pool_name

    def getNetworkBridgeInterface(self):
        return self.args.bridge_interface

    def getRam(self):
        return self.args.memory

    def getDistMirror(self):
        return self.args.dist_mirror

    def getCpus(self):
        return self.args.cpus

    def getDiskSize(self):
        return self.args.disk_size_gb

    def getPreseedUrl(self):
        return self.args.preseed_url

    def configureLogging(self):
        """Configure logging level."""
        if self.args.debug:
            log_level = logging.DEBUG
        else:
            log_level = logging.INFO

        logging.basicConfig(level=log_level,
                            format="%(asctime)s %(filename)s:%(lineno)d "
                            "%(levelname)s: %(message)s")

    def getVmType(self):
        return self.args.vm_type

    def getBuild(self):
        """Create or return vm builder object."""
        if VMBuilder.build:
            return VMBuilder.build

        if self.getVmType() == 'ubuntu':
            VMBuilder.build = vmtypes.Ubuntu()
        elif self.getVmType() == 'coreos':
            VMBuilder.build = vmtypes.CoreOS()
        elif self.getVmType() == 'debian':
            VMBuilder.build = vmtypes.Debian()

        return VMBuilder.build

    def getConn(self):
        """Create or return libvirt connection to VM host."""
        if VMBuilder.conn:
            return VMBuilder.conn

        VMBuilder.conn = libvirt.open(
            "qemu+ssh://%s/system" % self.args.vm_host)
        return VMBuilder.conn

    def getDiskPools(self):
        """Return list of disk pools on VM host."""
        return [current.name() for current in
                self.getConn().listAllStoragePools()]

    def getDiskPoolPath(self):
        """Return the absolute path for the VM's disk pool."""
        # TODO(jforman): Can you get disk pool XML via the API?
        # Does this provide for using remote host?
        command_line = ["/usr/bin/virsh",
                        "pool-dumpxml",
                        self.getDiskPoolName()]
        try:
            output = subprocess.check_output(command_line,
                                             stderr=subprocess.STDOUT)
            logging.debug("Command line %s; Output: %s", command_line, output)
        except subprocess.CalledProcessError as err:
            logging.error("Error in creating disk image: %s.", err.output)
            raise
        soup = BeautifulSoup(output, "lxml")
        self.pool_path = soup.target.path.string
        return self.pool_path

    def getDiskPoolVolumes(self):
        """Return list of all volumes in specified disk pool."""
        logging.debug("Getting volumes for pool %s.", self.getDiskPoolName())
        volumes = [x.name() for x in self.getConn().storagePoolLookupByName(
            self.getDiskPoolName()).listAllVolumes()]
        logging.debug("Volumes in pool %s: %s", self.getDiskPoolName(), volumes)
        return volumes

    def getNetworkInterfaces(self):
        """Return a list of viable network interfaces to connect to."""
        return self.getConn().listInterfaces()

    def getIPAddress(self):
        return self.args.ip_address

    def getNameserver(self):
        return self.args.nameserver

    def getNetmask(self):
        return self.args.netmask

    def getGateway(self):
        return self.args.gateway

    def getDefinedVMs(self):
        """Return list of all VM names on a VM host."""
        domains = [x.name() for x in self.getConn().listAllDomains()]
        return domains

    def getSshKey(self):
        """Returns contents of Public SSH Key."""
        homedir = os.environ['HOME']
        key_files = ['id_dsa.pub', 'id_rsa.pub']
        for current_kf in key_files:
            cf = os.path.join(homedir, ".ssh", current_kf)
            if os.path.exists(cf):
                with open(cf, 'r') as f:
                    key = f.read()
                return key
        logging.fatal("Unable to read any SSH keys. Do you need to create one?")

    def getUbuntuRelease(self):
        return self.args.ubuntu_release

    def getDebianRelease(self):
        return self.args.debian_release

    @classmethod
    def parseArgs(cls):
        """Parse and return command line flags."""
        parser = argparse.ArgumentParser()
        commands = parser.add_argument_group('commands')
        commands.add_argument('command',
                              type=str,
                              choices=['create_vm',
                                       'list_disk_pools',
                                       'list_network_interfaces',
                                       'list_pool_volumes'])
        vm_props = parser.add_argument_group('vm properties')
        vm_props.add_argument("--bridge_interface",
                              required=True,
                              help=("NIC/VLAN to bridge."
                                    "See command list_network_interfaces"))
        vm_props.add_argument("--cpus",
                              type=int,
                              default=1,
                              help="Number of CPUs. Default: %(default)d")
        vm_props.add_argument("--disk_size_gb",
                              default=10,
                              type=int,
                              help=("Size (GB) of disk image. "
                                    "Default: %(default)d"))
        vm_props.add_argument("--domain_name",
                              required=True,
                              help="VM domain name. Default: %(default)s")
        vm_props.add_argument("--memory",
                              type=int,
                              default=512,
                              choices=[512, 1024, 2048, 4096, 8192],
                              help="Amount of RAM, in MB. Default: %(default)d")
        vm_props.add_argument("--disk_pool_name",
                              required=True,
                              help=("Disk pool for VM disk image storage."
                                    "See command list_disk_pools"))
        vm_props.add_argument("--vm_type",
                              required=True,
                              choices=["coreos", "debian", "ubuntu"],
                              help="Type of VM to create.")
        vm_props.add_argument("--host_name",
                              required=True,
                              help="Virtual Machine Base Hostname")

        network_props = parser.add_argument_group('network properties')
        network_props.add_argument("--ip_address",
                                   help="IP Address of the VM.")
        network_props.add_argument("--nameserver",
                                   action='append',
                                   help="IP Address of DNS server. Multiple servers accepted.")
        network_props.add_argument("--netmask",
                                   default="255.255.255.0",
                                   help="IP Netmask for static config.")
        network_props.add_argument("--gateway",
                                   help="IP Address of default gateway.")

        vm_host_props = parser.add_argument_group('vm host properties')
        vm_host_props.add_argument("--vm_host",
                                   default="localhost",
                                   help="VM host. Default: %(default)s")

        parser.add_argument("--debug",
                            action="store_true",
                            help="Display debug output.")
        parser.add_argument("--deleteifexists",
                            action="store_true",
                            help="Delete VM data if it exists.")
        parser.add_argument("--dry_run",
                            action="store_true",
                            help=("Don't execute anything, just print out "
                                  "what would have been done."))
        parser.add_argument("--cluster_size",
                            default=1,
                            type=int,
                            help=("Create a number of VM instances. "
                                  "Default: %(default)s"))

        coreos_args = parser.add_argument_group('coreos vm properties')
        coreos_args.add_argument("--coreos_channel",
                                 choices=["stable", "beta", "alpha"],
                                 default="stable",
                                 help=("Channel of CoreOS image for VM base. "
                                       "Default: %(default)s."))
        coreos_args.add_argument("--coreos_image_age",
                                 default=7,
                                 help=("Age (days) of CoreOS base image before "
                                       "downloading a new one. "
                                       "Default: %(default)s"))
        coreos_args.add_argument("--coreos_cloud_config_template",
                                 default=os.path.join(
                                     os.path.dirname(
                                         os.path.realpath(__file__)),
                                     "configs",
                                     "coreos_user_data.template"),
                                 help=("Mako template for CoreOS cloud config "
                                       "user_data. Default: %(default)s"))
        coreos_args.add_argument("--coreos_create_cluster",
                                 action="store_true",
                                 help="Create an etcd cluster containing the "
                                      "instance(s).")
        coreos_args.add_argument("--coreos_cluster_overlay_network",
                                 default="10.123.0.0/16",
                                 help="Default overlay network used for fleet "
                                      "clustering. Default: %(default)s")
        coreos_args.add_argument("--coreos_nfs_mount",
                                 action="append",
                                 help="Mount Host:Mount tuple on CoreOS machine.")

        debian_args = parser.add_argument_group('debian-based vm properties')
        debian_args.add_argument("--preseed_url",
                                 help="URL of Debian-based OS install preseed file.")
        debian_args.add_argument("--debian_release",
                                 default="jessie",
                                 help="Debian OS release to install. Default: %(default)s.")
        debian_args.add_argument("--ubuntu_release",
                                 default="xenial",
                                 help="Ubuntu OS release to install. Default: %(default)s")
        debian_args.add_argument("--dist_mirror",
                                 help="Installation Mirror. Default: %(default)s",
                                 default="mirrors.mit.edu")

        args = parser.parse_args()
        network_args = [args.ip_address, args.nameserver, args.gateway]
        if any(network_args) and not all(network_args):
            logging.error("To configure static networking, IP address, "
                          "nameserver, netmask, and gateway are ALL required,")
            raise HandledException

        return args

    def createDiskImage(self):
        """Create a qcow2 disk image."""
        # TOOD: Figure out an API-ish way to create volume since
        #  vol-create-as does not support providing a --connect flag
        #  (["--connect", "qemu+ssh://%s/system" % self.args.vm_host])

        command_line = ["/usr/bin/virsh", "vol-create-as"]
        command_line.extend(["--pool", self.getDiskPoolName()])
        command_line.extend(["--name", self.getVmDiskImageName()])
        command_line.extend(["--capacity", "%dG" % self.getDiskSize()])
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
        logging.info("Checking for pre-existing disk image for this VM.")
        if self.getVmDiskImageName() not in self.getDiskPoolVolumes():
            logging.info("VM image does not exist for VM. Nothing to delete.")
            return

        logging.info("Attempting to delete image in pool %s for vm %s.",
                     self.getDiskPoolName(),
                     self.getVmName())
        if self.args.dry_run:
            logging.info("DRY RUN: Disk image not actually deleted.")
            return

        if not self.args.deleteifexists:
            logging.error("VM image found for host, but --deleteifexists flag "
                          "not passed.")
            raise HandledException
        self.getConn().storagePoolLookupByName(
            self.args.disk_pool_name).storageVolLookupByName(
                self.getVmDiskImageName()).delete()
        logging.info("Finished deleting VM image for VM.")

    def deleteVM(self):
        """Stop and delete the VM."""
        if self.args.dry_run:
            logging.info("DRY RUN: VM would have been deleted here.")
            return

        if self.getVmName() not in self.getDefinedVMs():
            logging.info("VM does not already exist.")
            return

        logging.info("Found existing VM with same name.")
        if not self.args.deleteifexists:
            logging.error("VM image found, but --deleteifexists "
                          "flag not passed.")
            raise HandledException

        if self.getConn().lookupByName(self.getVmName()).isActive():
            self.getConn().lookupByName(self.getVmName()).destroy()
        self.getConn().lookupByName(self.getVmName()).undefine()

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

        if self.args.cluster_size > 1:
            logging.info("More than one instance was asked to be created, "
                         "not connecting to console by default.")
            command_line.extend(["--noautoconsole"])

        flags = {
            "connect": "qemu+ssh://%s/system" % self.getVmHost(),
            "disk": "vol=%s/%s,cache=none" % (self.getDiskPoolName(),
                                              self.getVmDiskImageName()),
            "name": self.getVmName(),
            "network": "bridge=%s,model=virtio" % (
                self.getNetworkBridgeInterface()),
            "os-type": "unix",
            "ram": self.getRam(),
            "vcpus": self.getCpus(),
            "virt-type": "kvm",
        }

        virt_install_custom_flags = self.getBuild().getVirtInstallCustomFlags()
        if virt_install_custom_flags:
            flags.update(virt_install_custom_flags)

        extra_args = self.getBuild().getVirtInstallExtraArgs()
        if extra_args:
            logging.debug("Found extra-args for virt-install.")
            flags.update({'extra-args': extra_args})

        for flag, value in flags.iteritems():
            command_line.extend(["--%s" % flag, str(value)])
            logging.debug("flag: %s, value: %s",
                          flag, value)

        str_command_line = " ".join(command_line)
        logging.debug("virt-install command line: %s", str_command_line)

        self.getBuild().executePreVirtInstall()

        if self.args.dry_run:
            logging.info("DRYRUN: VM not actually created. Skipping.")
            return

        subprocess.call(str_command_line,
                        stderr=subprocess.STDOUT,
                        shell=True)
        self.getBuild().executePostVirtInstall()

    def createVM(self):
        """Main execution handler for the script."""

        cluster_index = 1
        while cluster_index <= self.args.cluster_size:
            self.setVmHostName(self.getVmHostNameArg(), cluster_index,
                               self.args.cluster_size)
            logging.info("Starting VM build for %s", self.getVmName())
            logging.info("Creating instance %s of cluster with %d "
                         "instances.", self.getVmName(), self.args.cluster_size)

            self.normalizeVMState()
            self.createDiskImage()
            self.executeVirtInstall()
            cluster_index += 1
        logging.info("VM %s creation is complete.", self.getVmName())

def main():
    """Main function for handling VM and disk creation."""

    vm = VMBuilder()

    if vm.args.command == 'list_disk_pools':
        print vm.getDiskPools()
    elif vm.args.command == 'list_pool_volumes':
        print vm.getDiskPoolVolumes()
    elif vm.args.command == 'list_network_interfaces':
        print vm.getNetworkInterfaces()
    elif vm.args.command == 'create_vm':
        logging.debug("about to run vm.getbuild.createvm")
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
