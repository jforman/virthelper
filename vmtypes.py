"""VM-specific configuration for using vmbuilder wrapper."""
import logging
import os
import subprocess
import time
import urllib

from mako.template import Template

from vmbuilder import VMBuilder, HandledException

class BaseVM(VMBuilder):
    """Base class for all VM types."""

    def __init__(self):
        super(BaseVM, self).__init__()

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
        pass

    def getVirtInstallCustomFlags(self):
        """Custom flags to append to the virt-install execution."""
        pass


class CoreOS(BaseVM):
    """CoreOS VM base class."""

    def __init__(self):
        super(CoreOS, self).__init__()
        # Compressed local snapshot image path
        self.comp_local_snapshot_image_path = "%s/coreos_production_qemu_image-%s.img.bz2" % (
            self.getPoolPath(),
            self.args.coreos_channel)
        self.uncomp_local_snapshot_image_path = "%s/coreos_production_qemu_image-%s.img" % (
            self.getPoolPath(),
            self.args.coreos_channel)

    def _getCloudConfigPath(self):
        """Return absolute path to VM's cloud config file."""
        return os.path.join(self.getPoolPath(), "coreos",
                            self.vm_name, "openstack", "latest", "user_data")

    def deleteVM(self):
        super(CoreOS, self).deleteVM()
        logging.info("Deleting CoreOS config drive for %s.", self.vm_name)
        cloud_config_path = "%s/coreos/%s/openstack/latest" % (self.getPoolPath(), self.vm_name)
        if os.path.exists(cloud_config_path):
            if self.args.dry_run:
                logging.info("DRY RUN: Would have attempted to remove cloud config"
                             " path: %s", cloud_config_path)
                return

            if self.args.deleteifexists:
                logging.info("Attempting remote cloud config path for %s: %s", self.vm_name,
                             cloud_config_path)
                os.removedirs(cloud_config_path)
            else:
                logging.info("Tried to remove %s path, but --deleteifexists flag not "
                             "passed.", cloud_config_path)
                raise HandledException

    def normalizeVMState(self):
        super(CoreOS, self).normalizeVMState()
        coreos_repo_image = "http://%s.release.core-os.net/amd64-usr/current/coreos_production_qemu_image.img.bz2" % self.args.coreos_channel
        logging.debug("Determining if a new CoreOS snapshot image needs to be downloaded.")
        if os.path.exists(self.comp_local_snapshot_image_path):
            snapshot_ctime = os.path.getctime(self.comp_local_snapshot_image_path)
            logging.debug("snapshot ctime: %s", snapshot_ctime)
            now = time.time()
            threshold = self.args.coreos_image_age * (24 * 60 * 60)
            if (now - snapshot_ctime) < threshold:
                logging.info("CoreOS snapshot image is less than %s days old. "
                             "Not re-downloading.", self.args.coreos_image_age)
                return

            message = ("It has been more than %s days since redownloading CoreOS %s image. "
                       "Let's delete the old one, and grab a new one." % (
                           self.args.coreos_image_age, self.args.coreos_channel))
            if self.args.dry_run:
                logging.info("DRY RUN: Would have deleted old image here.")
            else:
                os.remove(self.comp_local_snapshot_image_path)
                os.remove(self.uncomp_local_snapshot_image_path)
        else:
            message = "No local CoreOS %s image was found. Need to download." % self.args.coreos_channel

        logging.info(message)
        if self.args.dry_run:
            logging.info("DRY RUN: Would have retrieved a new %s CoreOS image here.",
                         self.args.coreos_channel)
            return

        logging.info("Attempting to download %s to %s.",
                     coreos_repo_image, self.comp_local_snapshot_image_path)
        urllib.urlretrieve(coreos_repo_image,
                           self.comp_local_snapshot_image_path)
        logging.info("Finished download of %s to %s",
                     coreos_repo_image,
                     self.comp_local_snapshot_image_path)

        logging.debug("Decompressing CoreOS image: %s.", self.comp_local_snapshot_image_path)
        subprocess.check_call(["/bin/bzip2", "-d", "-k", self.comp_local_snapshot_image_path])
        logging.info("Done decompressing CoreOS image.")

    def createDiskImage(self):
        """Create a qcow2 disk image using CoreOS snapshot image."""

        vm_image_path = "%s/%s" % (self.getPoolPath(), self.vm_disk_image)

        commands = []
        command_line = ["/usr/bin/qemu-img", "create", "-f", "qcow2"]
        command_line.extend(["-b", self.uncomp_local_snapshot_image_path])
        command_line.extend([vm_image_path])
        logging.debug("qemu-img command line: %s", " ".join(command_line))
        commands.extend([command_line])

        command_line = ["/usr/bin/virsh", "pool-refresh", "--pool", self.args.disk_pool_name]
        commands.extend([command_line])

        command_line = ["/usr/bin/virsh", "vol-upload", "--vol", os.path.basename(vm_image_path),
                        "--pool", self.args.disk_pool_name, "--file", vm_image_path]
        commands.extend([command_line])

        try:
            # NO shell=true here.
            logging.info("Creating CoreOS VM disk image.")
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
        extra_args = {
            "os-variant": "virtio26",
            "import": "",
            "filesystem": "%s,config-2,type=mount,mode=squash" % os.path.join(
                self.getPoolPath(), "coreos", self.vm_name),
        }
        return extra_args

    def executePreVirtInstall(self):
        self.writeCloudConfig()


    def writeCloudConfig(self):
        """Write VM's cloud config data to file."""
        if not os.path.exists(os.path.dirname(self._getCloudConfigPath())):
            os.makedirs(os.path.dirname(self._getCloudConfigPath()))

        template = Template(filename=self.args.coreos_cloud_config_template)
        cloud_config_vars = {
            'vm_name': self.vm_name,
        }
        template_rendered = template.render(**cloud_config_vars)
        with open(self._getCloudConfigPath(), "w") as cloud_config:
            cloud_config.write(template_rendered)
        logging.debug("rendered cloud config %s", template_rendered)

class Debian(BaseVM):
    """Debian-specific configuration for VM installation.

    Includes Ubuntu as a subclass.
    """

    def __init__(self):
        super(Debian, self).__init__()

    def getVirtInstallCustomFlags(self):
        return {
            "location": self.args.dist_location,
        }

    def getVirtInstallExtraArgs(self):
        extra_args = {
            "keyboard-configuration/xkb-keymap": "us",
            "console-setup/ask_detect": "false",
            "locale": "en_US", #.UTF-8",
            "netcfg/get_domain": self.args.domain_name,
            "netcfg/get_hostname": self.args.host_name,
            "preseed/url": "http://10.10.0.1/jf-custom-debian.preseed"
        }

        add_ons = ['serial', 'console=tty0', 'console=ttyS0,9600n8']
        result = []
        for key, value in extra_args.iteritems():
            result.append("%s=%s" % (key, value))
        result = " ".join(result)

        for current in add_ons:
            result += " %s" % current

        result = "\"%s\"" % result

        return result

    def getNetworkExtraArgs(self):
        """WIP: Debian-specific extra args for networking."""
        # NOTE: This needs to be reimplemented.
        # if self.args.ip_address:
        #   network_info = NETWORK_CONFIG[self.args.bridge_interface]
        #   if not self.args.ip_address.startswith(network_info['network']):
        #     logging.error("You assigned an IP address (%s) that does not match the requested interface (%s).", args.ip_address,
        #                   self.args.bridge_interface)
        #   raise vmbuilder.HandledException
        #
        #   extra_args += (" " +
        #                "netcfg/get_nameservers=" + network_info['nameserver'] + " " +
        #                "netcfg/get_ipaddress=" + self.args.ip_address + " " +
        #                "netcfg/get_netmask=" + self.network_info['netmask'] + " " +
        #                "netcfg/get_gateway=" + self.network_info['gateway'] + " " +
        #                "netcfg/confirm_static=true " +
        #                "netcfg/disable_autoconfig=true")
        #
        # custom_flags += "\""
        pass


class Ubuntu(Debian):
    """Ubuntu-specific configuration for VM install."""

    def __init__(self):
        super(Ubuntu, self).__init__()

    def getVirtInstallExtraArgs(self):
        extra_args = {
            "keyboard-configuration/xkb-keymap": "us",
            #"console-keymaps-at/keymap": "us",
            "console-keymaps-at/keymap": "American",
            "console-setup/ask_detect": "false",
            "console-setup/layoutcode": "us",
            "keyboard-configuration/layout": "USA",
            "keyboard-configuration/variant": "US",
            "locale": "en_US", #.UTF-8",
            "netcfg/get_domain": self.args.domain_name,
            "netcfg/get_hostname": self.args.host_name,
            "preseed/url": "http://10.10.0.1/jf-custom-ubuntu.preseed"
        }

        add_ons = ['serial', 'console=tty0', 'console=ttyS0,9600n8']

        # Get networkextra args working.
        network_extra_args = self.getNetworkExtraArgs()
        result = []
        for key, value in extra_args.iteritems():
            result.append("%s=%s" % (key, value))
        result = " ".join(result)

        for current in add_ons:
            result += " %s" % current
        result = "\"%s\"" % result

        return result
