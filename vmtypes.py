"""VM-specific configuration for using vmbuilder wrapper."""
import logging
import os
import subprocess
import time
import urllib

from mako.template import Template

from vmbuilder import VMBuilder, HandledException

# NEXT: test overlay network flag

class BaseVM(VMBuilder):
    """Base class for all VM types."""

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

    def getDistroSpecificExtraArgs(self):
        """Custom Extra Args for a specific Distro."""
        return {}


class CoreOS(BaseVM):
    """CoreOS VM base class."""

    discovery_url = None

    def getCompressedLocalSnapshotImagePath(self):
        """Return absolute local path of compressed CoreOS snapshot image."""

        img = "coreos_production_qemu_image-%s.img.bz2" % self.getCoreOSChannel()
        return os.path.join(self.getDiskPoolPath(), img)

    def getUnCompressedLocalSnapshotImagePath(self):
        """Return absolute local path of uncompressed CoreOS snapshot image."""
        return self.getCompressedLocalSnapshotImagePath().rstrip(".bz2")

    def getCloudConfigDir(self):
        """Return absolute directory path of VM's cloud config directory."""
        return os.path.join(self.getDiskPoolPath(), "coreos",
                            self.getVmName())

    def getCloudConfigPath(self):
        """Return absolute path to VM's cloud config file."""
        return os.path.join(self.getCloudConfigDir(),
                            "openstack", "latest", "user_data")

    def getCloudConfigTemplate(self):
        """Retun absolute path to cloud config template file."""
        return self.args.coreos_cloud_config_template

    def getCoreOSImageAge(self):
        """Return CoreOS image age threshold (days)."""
        return self.args.coreos_image_age

    def getCoreOSChannel(self):
        """Return the CoreOS channel used to create image."""
        return self.args.coreos_channel

    def getClusterOverlaynetwork(self):
        """Return CIDR string used for CoreOS flannel network.

        Example: '10.123.0.0/16'
        """
        return self.args.coreos_cluster_overlay_network

    def deleteVM(self):
        """Undefine a VM image in libvirt."""
        super(CoreOS, self).deleteVM()
        logging.debug("Trying to delete %s cloud config in %s.",
                      self.getVmName(),
                      self.getCloudConfigPath())
        if os.path.exists(self.getCloudConfigPath()):
            if self.args.dry_run:
                logging.info("DRY RUN: Would have attempted to remove cloud "
                             "config path: %s", self.getCloudConfigPath())
                return

            if self.args.deleteifexists:
                logging.info("Attempting remote cloud config path for %s: %s",
                             self.getVmName(), self.getCloudConfigPath())
                for root, dirs, files in os.walk(self.getCloudConfigPath(),
                                                 topdown=False):
                    for name in files:
                        os.remove(os.path.join(root, name))
                    for name in dirs:
                        os.rmdir(os.path.join(root, name))
            else:
                logging.info("Tried to remove %s path, but --deleteifexists "
                             "flag not passed.", self.getCloudConfigPath())
                raise HandledException

    def normalizeVMState(self):
        """Prepare VM host system state for new VM installation.

        This might include:
          * Deleting an old VM and VM image if one exists of the same name.
          * Redownloading a VM base image because of old age.
        """
        super(CoreOS, self).normalizeVMState()
        coreos_repo_image = ("http://%s.release.core-os.net/amd64-usr/current/"
                             "coreos_production_qemu_image.img.bz2" %
                             self.getCoreOSChannel())
        logging.debug("Determining if a new CoreOS snapshot image needs "
                      "to be downloaded.")
        if os.path.exists(self.getCompressedLocalSnapshotImagePath()):
            snapshot_ctime = os.path.getctime(
                self.getCompressedLocalSnapshotImagePath())
            logging.debug("Compressed snapshot ctime: %s (%s)",
                          snapshot_ctime,
                          time.strftime('%Y-%m-%d %H:%M:%S',
                                        time.localtime(snapshot_ctime)))
            now = time.time()
            threshold = self.getCoreOSImageAge() * (60 * 60 * 24)
            if (now - snapshot_ctime) < threshold:
                logging.info("CoreOS snapshot image is less than %s days old. "
                             "Not re-downloading.", self.getCoreOSImageAge())
                return

            message = ("It has been more than %s days since re-downloading "
                       "CoreOS %s image. Let's delete the old one, and grab "
                       "a new one." % (self.getCoreOSImageAge(),
                                       self.getCoreOSChannel()))
            if self.args.dry_run:
                logging.info("DRY RUN: Would have deleted old image here.")
            else:
                os.remove(self.getCompressedLocalSnapshotImagePath())
                os.remove(self.getUnCompressedLocalSnapshotImagePath())
        else:
            message = ("No local CoreOS %s image was found. Need to "
                       "download." % self.getCoreOSChannel())

        logging.info(message)
        if self.args.dry_run:
            logging.info("DRY RUN: Would have retrieved a new %s CoreOS "
                         "image here.", self.getCoreOSChannel())
            return

        logging.info("Attempting to download %s to %s.",
                     coreos_repo_image,
                     self.getCompressedLocalSnapshotImagePath())
        urllib.urlretrieve(coreos_repo_image,
                           self.getCompressedLocalSnapshotImagePath())
        logging.info("Finished download of %s to %s",
                     coreos_repo_image,
                     self.getCompressedLocalSnapshotImagePath)

        logging.debug("Decompressing CoreOS image: %s.",
                      self.getCompressedLocalSnapshotImagePath())
        subprocess.check_call(["/bin/bzip2", "-d", "-k",
                               self.getCompressedLocalSnapshotImagePath()])
        logging.info("Finished decompressing CoreOS image.")

    def createDiskImage(self):
        """Create a qcow2 disk image using CoreOS snapshot image."""

        logging.debug("CoreOS vm image path: %s", self.getVmDiskImagePath())
        commands = []
        command_line = ["/usr/bin/qemu-img", "create", "-f", "qcow2"]
        command_line.extend(["-b",
                             self.getUnCompressedLocalSnapshotImagePath()])
        command_line.extend([self.getVmDiskImagePath()])
        logging.debug("qemu-img command line: %s", " ".join(command_line))
        commands.extend([command_line])

        command_line = ["/usr/bin/virsh", "pool-refresh",
                        "--pool", self.getDiskPoolName()]
        commands.extend([command_line])

        command_line = ["/usr/bin/virsh", "vol-upload",
                        "--vol", os.path.basename(self.getVmDiskImagePath()),
                        "--pool", self.getDiskPoolName(),
                        "--file", self.getVmDiskImagePath()]
        commands.extend([command_line])

        try:
            # NO shell=true here.
            logging.info("Creating and uploading CoreOS VM disk image.")
            for current in commands:
                logging.debug("executing: %s", " ".join(current))
                if self.args.dry_run:
                    logging.info("DRY RUN: Did not actually execute.")
                    continue
                output = subprocess.check_output(current,
                                                 stderr=subprocess.STDOUT)
                logging.info("Disk image created successfully.")
                logging.debug("Disk image creation output: %s", output)
        except subprocess.CalledProcessError as err:
            logging.error("Error in creating disk image: %s.", err.output)
            raise HandledException

    def getVirtInstallCustomFlags(self):
        """Return dict of VM-type specific flags for virt-install."""
        extra_args = {
            "os-variant": "virtio26",
            "import": "",
            "filesystem": ("%s,config-2,type=mount,mode=squash" %
                           self.getCloudConfigDir()),
        }
        return extra_args

    def executePreVirtInstall(self):
        """Execute CoreOS-specific commands before running virt-install."""
        self.writeCloudConfig()

    def getDiscoveryURL(self):
        """Return a new etcd discovery URL token."""
        if CoreOS.discovery_url:
            return CoreOS.discovery_url

        if self.args.dry_run:
            logging.info("DRY RUN: Would have retrieved a new Discovery "
                         "URL token.")
            return

        logging.info("Retrieving a new Discovery URL taken.")
        # TODO: Add error checking if the request fails.
        durl_req = urllib.urlopen("https://discovery.etcd.io/new")
        url = durl_req.read()
        logging.info("Etcd Discovery URL %s.", url)
        CoreOS.discovery_url = url
        return CoreOS.discovery_url

    def getNfsMounts(self):
        """Return list of dicts of NFS mounts for CoreOS cloud configs."""
        if not self.args.coreos_nfs_mount:
            return []
        mounts = []
        for current_set in self.args.coreos_nfs_mount:
            server, mount_point = current_set.split(":")
            name = mount_point.replace('/', '-').lstrip('-')
            mounts.append({'name': name + '.mount',
                           'what': current_set,
                           'where': mount_point})
        return mounts

    def writeCloudConfig(self):
        """Write VM's cloud config data to file."""
        template = Template(filename=self.getCloudConfigTemplate())

        cloud_config_vars = {
            'etcd_listen_host': self.getVmName(),
            'vm_name': self.getVmName(),
            'ssh_keys': self.getSshKey(),
            'nfs_mounts': self.getNfsMounts()
        }

        if self.args.coreos_create_cluster:
            cloud_config_vars.update({
                'discovery_url': self.getDiscoveryURL(),
                'fleet_overlay_network': self.getClusterOverlaynetwork(),
            })

        logging.debug("Checking if static networking is enabled.")
        static_network = all([
            self.getIPAddress(),
            self.getNetmask(),
            self.getGateway()])

        logging.debug("Is static network configured? %s.", static_network)

        if static_network:
            cloud_config_vars.update({
                'static_network': static_network,
                'ip_address': self.getIPAddress(),
                'dns': self.getNameserver(),
                'gateway': self.getGateway(),
                'network_prefixlen': self.getPrefixLength(self.getIPAddress(), self.getNetmask()),
                'etcd_listen_host': self.getIPAddress(),
            })

        logging.debug("Cloud Config Vars: %s", cloud_config_vars)

        template_rendered = template.render(**cloud_config_vars)

        logging.debug("Cloud Config to be written:\n%s", template_rendered)

        if self.args.dry_run:
            logging.info("DRY RUN: Did not actually write Cloud Config.")
            return

        if not os.path.exists(os.path.dirname(self.getCloudConfigPath())):
            os.makedirs(os.path.dirname(self.getCloudConfigPath()))

        with open(self.getCloudConfigPath(), "w") as cloud_config:
            cloud_config.write(template_rendered)

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

        return "http://%s/%s/dists/%s/main/installer-amd64" % (
            self.getDistMirror(), self.getVmType(), os_release)

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
