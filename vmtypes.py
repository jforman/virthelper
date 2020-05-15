"""VM-specific configuration for using vmbuilder wrapper."""
import ipaddress
import logging
import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import libvirt
from bs4 import BeautifulSoup


# NEXT: test overlay network flag

class VMBuilder(object):
    """Class to marshall build of a VM."""

    build = None
    conn = None
    pool_path = None
    vm_hostname = None
    cluster_index = 0
    args = None
    virt_install_flag_updates = {}

    def __init__(self, args):
        VMBuilder.args = args
        self.configureLogging()

    def setArgs(self):
        """Parse command-line arguments into object variable."""
        self.args = self.parseArgs()

    def getConfigsDir(self):
        """return on-disk path to where virthelper configs are."""
        return os.path.join(os.path.dirname(
            os.path.realpath(__file__)),
            "configs")

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
        """Set indexed hostname based upon name and index.

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

    def getVmDirectory(self):
        """Return on-disk path to directory of VM."""
        return os.path.join(self.getDiskPoolPath(), self.getVmName())

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
            VMBuilder.build = Ubuntu()
        elif self.getVmType() == 'debian':
            VMBuilder.build = Debian()
        elif self.getVmType() == 'ubuntu-cloud':
            import ubuntu_cloud
            VMBuilder.build = ubuntu_cloud.UbuntuCloud()
        elif self.getVmType() == 'proxmox-ubuntu-cloud':
            import proxmox_ubuntu_cloud
            VMBuilder.build = proxmox_ubuntu_cloud.ProxmoxUbuntuCloud()

        return VMBuilder.build

    def getConn(self):
        """Create or return libvirt connection to VM host."""
        if VMBuilder.conn:
            return VMBuilder.conn

        VMBuilder.conn = libvirt.open(
            f"qemu+ssh://{self.args.vm_host}/system")
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
            logging.debug(f"Command line {command_line}; Output: {output}.")
        except subprocess.CalledProcessError as err:
            logging.critical(f"Error in creating disk image: {err.output}.")
        soup = BeautifulSoup(output, "lxml")
        self.pool_path = soup.target.path.string
        return self.pool_path

    def getDiskPoolVolumes(self):
        """Return list of all volumes in specified disk pool."""
        logging.debug(f"Getting volumes for pool {self.getDiskPoolName()}.")
        volumes = [x.name() for x in self.getConn().storagePoolLookupByName(
            self.getDiskPoolName()).listAllVolumes()]
        logging.debug(f"Volumes in pool {self.getDiskPoolName()}: {volumes}.")
        return volumes

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
            f"{self.args.ip_address}/{self.getNetmask()}",
            strict=False)

        logging.debug(f"Computed Network: {network}.")
        hosts = [x.exploded for x in network.hosts()]
        host_start_index = hosts.index(self.args.ip_address)
        logging.debug(f"Host start index: {host_start_index}, size: {self.getClusterSize()}, "
                      f"cluster index: {self.getClusterIndex()}.")
        hosts_slice = hosts[
            host_start_index:host_start_index+self.getClusterSize()]
        logging.debug(f"Slice of hosts: {hosts_slice}.")

        # Subtract one from the list because the list is
        # zero-indexed, but the cluster index is not.
        ip_address = hosts_slice[self.getClusterIndex()]
        logging.debug(f"Generated IP address: {ip_address}.")
        return ip_address

    def getPrefixLength(self, ip_address, netmask):
        """Given an IP address and netmask, return integer prefix length."""
        composed_address = f"{ip_address}/{netmask}"
        logging.debug(f"Determing network prefix length of {composed_address}.")
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


    def createDiskImage(self):
        """Create a qcow2 disk image."""
        # TOOD: Figure out an API-ish way to create volume since
        #  vol-create-as does not support providing a --connect flag
        #  (["--connect", "qemu+ssh://%s/system" % self.args.vm_host])

        command_line = (
            f"/usr/bin/virsh vol-create-as "
            f"--pool {self.getDiskPoolName()} "
            f"--name {self.getVmDiskImageName()} "
            f"--capacity {self.GetDiskSize()}G "
            f"--format qcow2 "
            f"--prealloc-metadata")

        logging.debug(f"Create disk image command line: {command_line}")

        if self.args.dry_run:
            logging.info("DRYRUN: No disk image was created.")
            return

        try:
            # NO shell=true here.
            output = subprocess.check_output(command_line,
                                             stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            logging.error(f"Error in creating disk image: {err.output}.")
            raise
        logging.info("Disk image created successfully.")
        logging.debug(f"Disk image creation output: {output}.")

    def deleteVMImage(self):
        """Delete a VM's disk image."""
        logging.info("Checking for pre-existing disk image for this VM.")
        if self.getVmDiskImageName() not in self.getDiskPoolVolumes():
            logging.info("VM image does not exist for VM. Nothing to delete.")
            return

        logging.info(f"Attempting to delete image in pool {self.getDiskPoolName()} for vm {self.getVmName()}")
        if self.args.dry_run:
            logging.info("DRY RUN: Disk image not actually deleted.")
            return

        if not self.args.deleteifexists:
            logging.critical("VM image found for host, but --deleteifexists flag "
                          "not passed.")
            sys.exit(1)

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
            logging.info("VM does not already exist. No VM to delete.")
            return

        logging.info("Found existing VM with same name.")
        if not self.args.deleteifexists:
            logging.fatal("VM image found, but --deleteifexists "
                          "flag not passed.")

        if self.getConn().lookupByName(self.getVmName()).isActive():
            self.getConn().lookupByName(self.getVmName()).destroy()
        self.getConn().lookupByName(self.getVmName()).undefine()

    def deleteVMDirectory(self):
        """Delete a VM directory underneath the disk-pool."""
        vm_dir = os.path.join(
            self.getDiskPoolPath(),
            self.getVmName())

        if self.args.dry_run:
            logging.info(f"DRY RUN: Would have tried to delete VM data directory: {vm_dir}.")
            return

        if not os.path.exists(vm_dir):
            logging.info(f"VM data directory {vm_dir} not found. Nothing to delete.")
            return

        if not self.args.deleteifexists:
            logging.fatal("VM directory found, but --deleteifexists flag not passed.")

        logging.info(f"Attempting to delete VM directory: {vm_dir}.")
        shutil.rmtree(vm_dir)

    def normalizeVMState(self):
        """Delete pre-existing VM and disk image if desired.

        If args.deleteifexists, delete VM and disk image.
        Else raise error.
        """

        self.deleteVM()
        self.deleteVMImage()

    def checkValidMacAddress(self, mac_address, fatal=False):
        """Check if MAC address is valid. If fatal is true, raise exception."""
        logging.debug(f"Verifying validity of MAC address: {mac_address}.")
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
            "connect": f"qemu+ssh://{self.getVmHost()}/system",
            "disk": [f"vol={self.getDiskPoolName()}/{self.getVmDiskImageName},cache=none"],
            "name": self.getVmName(),
            "network": f"bridge={self.getNetworkBridgeInterface()},model=virtio",
            "os-type": "linux",
            "ram": self.getRam(),
            "vcpus": self.getCpus(),
        }

        if self.args.use_uefi:
            flags.update({"boot": "uefi"})

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

        # TODO: simplify this logic to see if we need to have multiples
        # of one flag.
        for flag, values in flags.items():
            if isinstance(values, list):
                if len(values) > 1:
                    # multiple instances of an arg,
                    # so we need to iterate over each arg
                    for x in range(0,len(values)):
                        command_line.extend(["--%s" % flag, str(values[x])])
                else:
                    command_line.extend(["--%s" % flag, str(values[0])])
            else:
                command_line.extend(["--%s" % flag, str(values)])

            logging.debug(f"flag: {flag}, value: {values}")

        str_command_line = " ".join(command_line)

        final_args = self.getBuild().getVirtInstallFinalArgs()

        if final_args:
            logging.info(f"Adding final arguments to virt-install: {final_args}.")
            str_command_line = str_command_line + " " + final_args

        logging.debug(f"virt-install command line: {str_command_line}")

        self.getBuild().executePreVirtInstall()

        if self.args.dry_run:
            logging.info("DRYRUN: VM not actually created. Skipping.")
            return

        returncode = subprocess.call(
            str_command_line,
            stderr=subprocess.STDOUT,
            shell=True)

        logging.debug(f"virt-install returncode: {returncode}.")

        if returncode != 0:
            logging.exception("non-zero returncode from virt-install execution. exiting.")
            raise

        self.getBuild().executePostVirtInstall()

    def createVM(self):
        """Main execution handler for the script."""

        for cluster_index in range(0, self.getClusterSize()):
            self.setClusterIndex(cluster_index)
            logging.debug(f"Starting to build host {self.getClusterIndex()}.")
            self.setVmHostName(self.getVmHostNameArg(), self.getClusterIndex(),
                               self.getClusterSize())
            logging.info(f"Starting VM build for {self.getVmName()}.")
            logging.info(f"Creating instance {self.getVmName()} of cluster with {self.args.cluster_size} "
                         f"instances.")

            self.normalizeVMState()
            self.createDiskImage()
            self.executeVirtInstall()
            logging.info(f"VM {self.getVmName()} creation is complete.")

    def verifyMinimumCreateVMArgs(self):
        """Verify that list of minimum args to create a VM were passed."""
        if not all([
            self.args.bridge_interface,
            self.args.domain_name,
            self.args.disk_pool_name,
            self.args.vm_type,
            self.args.host_name,
        ]):
            logging.critical(
                "Missing critical arguments. Arguments considered "
                "critical: bridge_interface, domain_name, disk_pool, "
                "vm_type, host_name")

class BaseVM(VMBuilder):
    """Base class for all VM types."""

    def __init__(self):
        pass

    def executePreVirtInstall(self):
        """Logic to execute right before running virt-install."""
        pass

    def executePostVirtInstall(self):
        """Logic to execute right after running virt-install."""
        pass

    def getVirtInstallExtraArgs(self):
        """Construct VM-type specific extra-args flag for virt-install

        Takes a dict of (key, value) and returns
        "key=value,key=value,add_on1,add_on2" string
        """
        return {}

    def getNetworkExtraArgs(self):
        """Args used when statically configuring networking."""
        return {}

    def getVirtInstallCustomFlags(self):
        """Custom flags to append to the virt-install execution."""
        pass

    def getVirtInstallFinalArgs(self):
        """String of final params at the end of virt-install exection."""
        pass

    def getDistroSpecificExtraArgs(self):
        """Custom Extra Args for a specific Distro."""
        return {}


class Debian(BaseVM):
    """Debian-specific configuration for VM installation.
    Includes Ubuntu as a subclass.
    """

    def getDistLocation(self):
        """Return URL location of installation source."""

        if self.getVmType() == "debian":
            os_release = self.getDebianRelease()
        elif self.getVmType() == "ubuntu":
            os_release = self.getUbuntuRelease()

        return f"https://{self.getDistMirror()}/{self.getVmType()}/dists/{os_release}/main/installer-amd64"

    def getVirtInstallCustomFlags(self):
        """Return dict of OS-type specific virt-install flags."""
        return {
            "location": self.getDistLocation(),
        }

    def getNetworkExtraArgs(self):
        """Extra args when statically configuring networking."""
        if not self.getIPAddress():
            return {}

        extra_args = {
            "netcfg/get_nameservers": " ".join(self.getNameserver()),
            "netcfg/get_ipaddress": self.getIPAddress(),
            "netcfg/get_netmask": self.getNetmask(),
            "netcfg/get_gateway": self.getGateway(),
            "netcfg/confirm_static": "true",
            "netcfg/disable_autoconfig": "true",
        }
        return extra_args


    def getVirtInstallExtraArgs(self):
        """Return constructed list of extra-args parameters.
        Note: This starts out as a dict, but is reformatted as
        key=var,key=var,...
        as this is the expected format for virt-install.
        """
        extra_args = {
            "keyboard-configuration/xkb-keymap": "us",
            "console-setup/ask_detect": "false",
            "locale": "en_US",
            "netcfg/get_domain": self.args.domain_name,
            "netcfg/get_hostname": self.args.host_name,
            "preseed/url": self.getPreseedUrl(),
        }

        add_ons = ['serial', 'console=tty0', 'console=ttyS0,9600n8']
        result = []

        extra_args.update(self.getNetworkExtraArgs())
        extra_args.update(self.getDistroSpecificExtraArgs())
        for key, value in extra_args.iteritems():
            result.append("%s=%s" % (key, value))
        result = " ".join(result)

        for current in add_ons:
            result += " %s" % current

        result = "\"%s\"" % result

        return result


class Ubuntu(Debian):
    """Ubuntu-specific configuration for VM install."""

    def getDistroSpecificExtraArgs(self):
        args = {
            "console-keymaps-at/keymap": "American",
            "console-setup/layoutcode": "us",
            "keyboard-configuration/layout": "USA",
            "keyboard-configuration/variant": "US",
        }
        return args
