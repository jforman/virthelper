#!/usr/bin/env python
"""A helpful wrapper for using libvirt to create virtual machines."""
import argparse
import logging
import os
import subprocess
import sys

from bs4 import BeautifulSoup
import ipaddress
import libvirt
import netaddr

import coreos
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
    cluster_index = 1

    def __init__(self):
        self.args = self.parseArgs()
        self.configureLogging()

    def setArgs(self):
        """Parse command-line arguments into object variable."""
        self.args = self.parseArgs()

    def getClusterSize(self):
        """Integer size of cluster being created."""
        return self.args.cluster_size

    def setClusterIndex(self, c_index):
        """Set index of cluster VM being created."""
        VMBuilder.cluster_index = c_index

    def getClusterIndex(self):
        """Get index of cluster VM being created."""
        return VMBuilder.cluster_index

    def getVmHost(self):
        """Get VM hostname containing VMs."""
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
        """Get on-disk path to VM disk image."""
        return os.path.join(self.getDiskPoolPath(),
                            self.getVmDiskImageName())

    def getDiskPoolName(self):
        """Return name of disk pool VM lives on."""
        return self.args.disk_pool_name

    def getNetworkBridgeInterface(self):
        """Get network interface chosen for VM."""
        return self.args.bridge_interface

    def getRam(self):
        """Return, in integer MB, amount of RAM, VM assigned."""
        return self.args.memory

    def getDistMirror(self):
        """Base URL path for OS distribution mirror."""
        return self.args.dist_mirror

    def getCpus(self):
        """Return integer of how many CPUs VM has."""
        return self.args.cpus

    def getDiskSize(self):
        """Return integer GB of disk for VM disk image."""
        return self.args.disk_size_gb

    def getPreseedUrl(self):
        """Return URL used to obtain OS preseed config file."""
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
        """Return OS type of VM guest."""
        return self.args.vm_type

    def getBuild(self):
        """Create or return vm builder object."""
        if VMBuilder.build:
            return VMBuilder.build

        if self.getVmType() == 'ubuntu':
            VMBuilder.build = vmtypes.Ubuntu()
        elif self.getVmType() == 'coreos':
            VMBuilder.build = coreos.CoreOS()
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
        if not self.pool_path is None:
            logging.debug("Returning cached pool path.")
            return self.pool_path

        command_line = ["/usr/bin/virsh",
                        "pool-dumpxml",
                        self.getDiskPoolName()]
        try:
            output = subprocess.check_output(command_line,
                                             stderr=subprocess.STDOUT)
            logging.debug("Command line %s; Output: %s", command_line, output)
        except subprocess.CalledProcessError as err:
            logging.error("Error in creating disk image: %s.", err.output)
            raise HandledException
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
        """
        If only one host, return IP address.
        If more than one, we need to calculate which IP of set to return.
        """
        if not self.args.ip_address:
            # Not statically configured, so return nothing (DHCP assumed).
            return None

        if self.getClusterSize() == 1:
            return self.args.ip_address

        network = ipaddress.ip_network(
            unicode('%s/%s' % (
                self.args.ip_address,
                self.getNetmask())),
            strict=False)

        logging.debug("Computed Network: %s", network)
        hosts = [x.exploded for x in network.hosts()]
        host_start_index = hosts.index(self.args.ip_address)
        logging.debug("Host start index: %s, size: %s, cluster index: %s.",
                      host_start_index, self.getClusterSize(),
                      self.getClusterIndex())
        hosts_slice = hosts[
            host_start_index:host_start_index+self.getClusterSize()]
        logging.debug("Slice of hosts: %s", hosts_slice)

        # Subtract one from the list because the list is
        # zero-indexed, but the cluster index is not.
        ip_address = hosts_slice[self.getClusterIndex()-1]
        logging.debug("Generated IP address: %s", ip_address)
        return ip_address

    def getPrefixLength(self, ip_address, netmask):
        """Given an IP address and netmask, return integer prefix length."""
        composed_address = u"%s/%s" % (ip_address, netmask)
        logging.debug("Determing network prefix length of %s.", composed_address)
        return ipaddress.IPv4Network(composed_address, strict=False).prefixlen

    def getNameserver(self):
        """Return list of nameserver IP addresses."""
        return self.args.nameserver

    def getNetmask(self):
        """Return dotted-quad IP subnet mask."""
        return self.args.netmask

    def getGateway(self):
        """Return IP of default gateway."""
        return self.args.gateway

    def getDefinedVMs(self):
        """Return list of all VM names on a VM host."""
        domains = [x.name() for x in self.getConn().listAllDomains()]
        return domains

    def getSshKey(self):
        """Returns contents of Public SSH Key."""
        homedir = os.environ['HOME']
        key_files = ['id_dsa.pub', 'id_rsa.pub', 'authorized_keys']
        keys = []
        for current_kf in key_files:
            cf = os.path.join(homedir, ".ssh", current_kf)
            if os.path.exists(cf):
                with open(cf, 'r') as f:
                    keys.extend(x.strip() for x in f.readlines() if x != "\n")
        if not keys:
            logging.fatal("Unable to read any SSH keys. Do you need to create one?")
        return keys

    def getUbuntuRelease(self):
        """Return ubuntu release code name."""
        return self.args.ubuntu_release

    def getDebianRelease(self):
        """Return Debian release code name."""
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
                              help="Type of VM to create.")
        vm_props.add_argument("--host_name",
                              help="Virtual Machine Base Hostname")

        network_props = parser.add_argument_group('network properties')
        network_props.add_argument("--ip_address",
                                   help="IP Address of the VM.")
        network_props.add_argument("--nameserver",
                                   action='append',
                                   help="IP Address of DNS server. Multiple servers accepted.")
        network_props.add_argument("--netmask",
                                   help="IP Netmask for static config.")
        network_props.add_argument("--gateway",
                                   help="IP Address of default gateway.")
        network_props.add_argument("--mac_address",
                                   help="Hard-coded network interface MAC address.")

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
        coreos_args.add_argument("--coreos_ct_version",
                                 default="0.5.0",
                                 help=("Version of CoreOS config transpiler "
                                 "in the creation of the Ignition config."))

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
        network_args = [args.ip_address, args.nameserver, args.gateway, args.netmask]
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

    def checkValidMacAddress(self, mac_address, fatal=False):
        """Check if MAC address is valid. If fatal is true, raise exception."""
        logging.debug("Verifying validity of MAC address: %s.", mac_address)
        is_valid_mac = netaddr.valid_mac(mac_address)
        if is_valid_mac:
            logging.debug("Found valid MAC address.")
            return True

        logging.error("Invalid MAC address found.")
        if fatal:
            raise

        return False

    def executeVirtInstall(self):
        """Execute virt-install with vm-specific flags."""

        command_line = ["/usr/bin/virt-install", "--autostart",
                        "--nographics",
                        '--console pty,target_type=serial']
        if self.args.debug:
            command_line.extend(["--debug"])

        if self.getClusterSize() > 1:
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
            "os-type": "linux",
            "ram": self.getRam(),
            "vcpus": self.getCpus(),
        }

        virt_install_custom_flags = self.getBuild().getVirtInstallCustomFlags()
        if virt_install_custom_flags:
            flags.update(virt_install_custom_flags)

        if self.args.mac_address:
            self.checkValidMacAddress(self.args.mac_address, fatal=True)
            flags.update({'network':
                flags['network'] + ",mac=" + self.args.mac_address })

        extra_args = self.getBuild().getVirtInstallExtraArgs()
        if extra_args:
            logging.debug("Found extra-args for virt-install.")
            flags.update({'extra-args': extra_args})

        for flag, value in flags.iteritems():
            command_line.extend(["--%s" % flag, str(value)])
            logging.debug("flag: %s, value: %s",
                          flag, value)

        str_command_line = " ".join(command_line)

        final_args = self.getBuild().getVirtInstallFinalArgs()

        if final_args:
            logging.info("Adding final arguments to virt-install: %s",
                         final_args)
            str_command_line = str_command_line + " " + final_args

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

        for cluster_index in range(1, self.getClusterSize()+1):
            self.setClusterIndex(cluster_index)
            logging.debug("Starting to build host %s.", self.getClusterIndex())
            self.setVmHostName(self.getVmHostNameArg(), self.getClusterIndex(),
                               self.getClusterSize())
            logging.info("Starting VM build for %s", self.getVmName())
            logging.info("Creating instance %s of cluster with %d "
                         "instances.", self.getVmName(), self.args.cluster_size)

            self.normalizeVMState()
            self.createDiskImage()
            self.executeVirtInstall()
        logging.info("VM %s creation is complete.", self.getVmName())

    def verifyMinimumCreateVMArgs(self):
        """Verify that list of minimum args to create a VM were passed."""
        if not all([
            self.args.bridge_interface,
            self.args.domain_name,
            self.args.disk_pool_name,
            self.args.vm_type,
            self.args.host_name,
        ]):
            logging.error("Missing critical arguments. Arguments considered "
                          "critical: bridge_interface, domain_name, disk_pool, "
                          "vm_type, host_name")
            raise HandledException

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
        vm.verifyMinimumCreateVMArgs()
        vm.getBuild().createVM()
    else:
        logging.fatal("The command you entered is not recognized.")

if __name__ == "__main__":
    try:
        sys.exit(main())
    except HandledException:
        logging.exception("Exiting from handled exception.")
        sys.exit(1)
    except Exception as err:
        logging.exception(err)
