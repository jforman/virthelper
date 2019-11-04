"""Ubuntu Cloud specific virtual machine builder library."""
import logging
import os
import subprocess
import urllib
import uuid
from urllib.parse import urlparse
import urllib.request

import jinja2

import vmtypes

RELEASE_TO_VER = {
    'bionic': '18.04',
    'cosmic': '18.10',
    'disco': '19.04',
}

class UbuntuCloud(vmtypes.BaseVM):
    """Ubuntu-Cloud specific configuration."""

    name = "UbuntuCloud"
    static_network_configured = False

    def __init__(self):
        super(UbuntuCloud, self).__init__()

    def normalizeVMState(self):
        """get VM images in a state ready to be installed."""
        super(UbuntuCloud, self).normalizeVMState()
        self.deleteVMDirectory()
        self.downloadUbuntuCloudImage()
        self.createVmDirectory()
        self.writeUserData()
        self.writeMetaData()
        self.writeNetworkConfigData()
        self.createGoldenUbuntuCloudImage()
        self.createVmSeedImage()

    def getUbuntuReleaseDatestamp(self):
        return RELEASE_TO_VER[self.getUbuntuRelease()]

    def getUbuntuReleaseImageFilename(self):
        """Release cloud-image file name."""
        return f"ubuntu-{self.getUbuntuReleaseDatestamp()}-minimal-cloudimg-amd64.img"

    def getReleaseImageDownloadPath(self):
        """remote url to download image file."""
        return f"https://cloud-images.ubuntu.com/minimal/releases/{self.getUbuntuRelease()}/release/ubuntu-{self.getUbuntuReleaseDatestamp()}-minimal-cloudimg-amd64.img"

    def getReleaseImagePath(self):
        return os.path.join(
            self.getDiskPoolPath(),
            self.getUbuntuReleaseImageFilename())

    def getVmSeedImagePath(self):
        """return path to cloud vm seed image. containing meta/user data."""
        return os.path.join(
            self.getDiskPoolPath(),
            "%s-seed.img" % self.getVmName())

    def getGoldenImagePath(self):
        """return on-disk path of distro golden image file."""
        return os.path.join(
            self.getDiskPoolPath(),
            f"ubuntu-{self.getUbuntuReleaseDatestamp()}-minimal-cloudimg-amd64-golden.img")

    def createGoldenUbuntuCloudImage(self):
        """create golden ubuntu cloud image to be used for installs."""
        if os.path.exists(self.getGoldenImagePath()):
            logging.info("Golden Ubuntu release image already exists.")
            return
        command_line = ["/usr/bin/qemu-img",
                        "convert", "-O", "qcow2",
                        self.getReleaseImagePath(),
                        self.getGoldenImagePath()]
        if self.args.dry_run:
            logging.info("DRY RUN: Would have created golden Ubuntu release image.")
            return
        logging.info("Attempting to create golden Ubuntu release image.")
        try:
            output = subprocess.check_output(command_line,
                stderr=subprocess.STDOUT)
            logging.debug(f"Command line {command_line}; Output: {output}")
        except subprocess.CalledProcessError as err:
            logging.critical(f"Error in creating image: {err.output}.")

    def downloadUbuntuCloudImage(self):
        """Download Ubuntu cloud image for specificed release."""
        logging.info(f"Attempting to download {self.getUbuntuReleaseImageFilename()} to {self.getReleaseImagePath()}.")
        if os.path.exists(self.getReleaseImagePath()):
            logging.info("Image already downloaded. Skipping.")
            return

        if self.args.dry_run:
            logging.info(f"DRY RUN: Would have retrieved new image {self.getUbuntuReleaseImageFilename()} "
                         f"from {self.getReleaseImageDownloadPath()}.")
            return
        logging.info("Beginning download of Ubuntu cloud image.")
        urllib.request.urlretrieve(
            self.getReleaseImageDownloadPath(),
            self.getReleaseImagePath())
        logging.info("Finished downloading Ubuntu cloud image.")

    def createVmDirectory(self):
        """create a host-specific vm-store directory."""
        if not os.path.exists(self.getVmDirectory()):
            if self.args.dry_run:
                logging.info(f"DRY RUN: Would have created created VM "
                             f"directory: {self.getVmDirectory()}.")
                return
            logging.info(f"Creating VM directory: {self.getVmDirectory()}.")
            os.mkdir(self.getVmDirectory())

    def writeNetworkConfigData(self):
        """write the cloud-config network config data file file."""
        # if network config data is true, add the flag and file to
        # cloud-localds run.

        def render(template_file, context):
            """Function to fill in variables in jinja2 template file."""
            path, filename = os.path.split(template_file)
            return jinja2.Environment(
                loader=jinja2.FileSystemLoader(path)
                ).get_template(filename).render(context)

        logging.debug("Checking if static networking is enabled.")
        static_network = all([
            self.getIPAddress(),
            self.getNetmask(),
            self.getGateway()])

        network_config_vars = {}

        logging.debug(f"Is static network configured? {static_network}.")

        if static_network:
            UbuntuCloud.static_network_configured = True
            network_config_vars.update({
                'static_network': True,
                'dns': self.getNameserver(),
                'gateway': self.getGateway(),
                'ip_address': self.getIPAddress(),
                'network_prefixlen': self.getPrefixLength(
                    self.getIPAddress(),
                    self.getNetmask()),
            })
        else:
            return

        network_config_template = os.path.join(
            self.getConfigsDir(),
            "network-config.yaml")

        template_rendered = render(network_config_template, network_config_vars)

        logging.debug(f"Rendered network-config config: {template_rendered}")

        if self.args.dry_run:
            logging.info("DRY RUN: Did not actually write network-config.")
            return

        with open(os.path.join(self.getVmDirectory(), "network-config"), "w") as cc:
            cc.write(template_rendered)

    def writeUserData(self):
        """write the cloud-config user-data file."""

        def render(template_file, context):
            """Function to fill in variables in jinja2 template file."""
            path, filename = os.path.split(template_file)
            return jinja2.Environment(
                loader=jinja2.FileSystemLoader(path)
                ).get_template(filename).render(context)

        user_data_vars = {
            'hostname': self.getVmHostName(),
            'fqdn': self.getVmName(),
            'ssh_keys': self.getSshKey()
        }

        user_data_template = os.path.join(
            self.getConfigsDir(),
            "user-data.yaml")

        template_rendered = render(user_data_template, user_data_vars)

        logging.debug(f"Rendered user-data config: {template_rendered}")

        if self.args.dry_run:
            logging.info("DRY RUN: Did not actually write user-data.")
            return

        with open(os.path.join(self.getVmDirectory(), "user-data"), "w") as cc:
            cc.write(template_rendered)

    def writeMetaData(self):
        """write the cloud-config meta-data file."""

        def render(template_file, context):
            """Function to fill in variables in jinja2 template file."""
            path, filename = os.path.split(template_file)
            return jinja2.Environment(
                loader=jinja2.FileSystemLoader(path)
                ).get_template(filename).render(context)

        meta_data_vars = {
            'vm_instance_id': uuid.uuid1(),
            'vm_hostname': self.getVmHostName()
        }

        meta_data_template = os.path.join(
            self.getConfigsDir(),
            "meta-data.yaml")

        template_rendered = render(meta_data_template, meta_data_vars)

        logging.debug(f"Rendered meta-data config: {template_rendered}")
        
        if self.args.dry_run:
            logging.info("DRY RUN: Did not actually write meta-data.")
            return

        with open(os.path.join(self.getVmDirectory(), "meta-data"), "w") as cc:
            cc.write(template_rendered)

    def createVmSeedImage(self):
        """create VM seed image containing user/meta data."""

        logging.info("Writing VM seed image with user and meta data.")
        if UbuntuCloud.static_network_configured:
            # TODO: figure out a cleaner way to insert the network
            # config flags as opposed to just copying the list twice.
            command_line = ["/usr/bin/cloud-localds",
                            "--network-config",
                            os.path.join(self.getVmDirectory(),
                                         "network-config"),
                            self.getVmSeedImagePath(),
                            os.path.join(self.getVmDirectory(), "user-data"),
                            os.path.join(self.getVmDirectory(), "meta-data")]
        else:
            command_line = ["/usr/bin/cloud-localds",
                            self.getVmSeedImagePath(),
                            os.path.join(self.getVmDirectory(), "user-data"),
                            os.path.join(self.getVmDirectory(), "meta-data")]


        logging.debug(f"cloud-localds command line: {command_line}")

        if self.args.dry_run:
            logging.info(f"DRY RUN. Would have run: {command_line}.")
            return
        try:
            output = subprocess.check_output(command_line,
                stderr=subprocess.STDOUT)
            logging.debug(f"Command line {command_line}; Output: {output}")
        except subprocess.CalledProcessError as err:
            logging.critical("Error in creating image: %s.", err.output)


    def createDiskImage(self):
        """Create a qcow2 disk image using Ubuntu Cloud golden image."""

        logging.info("Creating disk image for Ubuntu Cloud host %s.",
                     self.getVmName())

        commands = []
        command_line = ["/usr/bin/qemu-img", "create", "-f", "qcow2"]
        command_line.extend(["-b",
                             self.getGoldenImagePath()])
        command_line.extend([self.getVmDiskImagePath()])
        command_line.extend(["%dG" % self.getDiskSize()])
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
            logging.info("Creating and uploading Ubuntu Minimal VM disk image.")
            for current in commands:
                logging.debug("executing: %s", " ".join(current))
                if self.args.dry_run:
                    logging.info("DRY RUN: Did not actually execute.")
                    continue
                output = subprocess.check_output(current,
                                                 stderr=subprocess.STDOUT)
                logging.info("Disk image created successfully.")
                logging.debug(f"Disk image creation output: {output}.")
        except subprocess.CalledProcessError as err:
            logging.critical(f"Error in creating disk image: {err.output}.")

    def getVirtInstallCustomFlags(self):
        return {
            'disk': [f"vol={self.getDiskPoolName()}/{self.getVmDiskImageName()},cache=none,bus=virtio",
                     f"{self.getVmSeedImagePath()},cache=none,bus=virtio"],
            'boot': 'hd',
        }
