"""Ubuntu Cloud specific virtual machine builder library."""
import logging
import os
import subprocess
import urllib
import uuid
from urlparse import urljoin

import jinja2

import vmtypes

RELEASE_TO_VER = {
    'bionic': '18.04'
}

class UbuntuCloud(vmtypes.BaseVM):
    """Ubuntu-Cloud specific configuration."""

    name = "UbuntuCloud"

    def __init__(self):
        super(UbuntuCloud, self).__init__()

    def normalizeVMState(self):
        """get VM images in a state ready to be installed."""
        super(UbuntuCloud, self).normalizeVMState()
        self.downloadUbuntuCloudImage()
        self.createVmDirectory()
        # TODO: write network config data out.
        self.writeUserData()
        self.writeMetaData()
        self.createGoldenUbuntuCloudImage()
        self.createVmSeedImage()

    def getUbuntuReleaseDatestamp(self):
        return RELEASE_TO_VER[self.getUbuntuRelease()]

    def getUbuntuReleaseImageFilename(self):
        """Release cloud-image file name."""
        return "ubuntu-%s-minimal-cloudimg-amd64.img" % self.getUbuntuReleaseDatestamp()

    def getReleaseImageDownloadPath(self):
        """remote url to download image file."""
        return "http://cloud-images.ubuntu.com/minimal/releases/%s/release/ubuntu-%s-minimal-cloudimg-amd64.img" % (self.getUbuntuRelease(),  self.getUbuntuReleaseDatestamp())

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
            "ubuntu-%s-minimal-cloudimg-amd64-golden.img" % self.getUbuntuReleaseDatestamp())

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
            logging.debug("Command line %s; Output: %s", command_line, output)
        except subprocess.CalledProcessError as err:
            logging.critical("Error in creating image: %s.", err.output)

    def downloadUbuntuCloudImage(self):
        """Download Ubuntu cloud image for specificed release."""
        logging.info("Attempting to download %s to %s",
            self.getUbuntuReleaseImageFilename(),
            self.getReleaseImagePath())
        if os.path.exists(self.getReleaseImagePath()):
            logging.info("Image already downloaded. Skipping.")
            return

        if self.args.dry_run:
            logging.info("DRY RUN: Would have retrieved new image %s from %s.",
                         self.getUbuntuReleaseImageFilename(),
                         self.getReleaseImageDownloadPath())
            return
        logging.info("Beginning download of Ubuntu cloud image.")
        urllib.urlretrieve(
            self.getReleaseImageDownloadPath(),
            self.getReleaseImagePath())
        logging.info("Finished downloading Ubuntu cloud image.")

    def createVmDirectory(self):
        """create a host-specific vm-store directory."""
        if not os.path.exists(self.getVmDirectory()):
            if self.args.dry_run:
                logging.info("DRY RUN: Would have created created VM "
                             "directory: %s.", self.getVmDirectory())
                return
            logging.info("Creating VM directory: %s.", self.getVmDirectory())
            os.mkdir(self.getVmDirectory())

    def writeUserData(self):
        """write the cloud-config user-data file."""

        def render(template_file, context):
            """Function to fill in variables in jinja2 template file."""
            path, filename = os.path.split(template_file)
            return jinja2.Environment(
                loader=jinja2.FileSystemLoader(path)
                ).get_template(filename).render(context)

        user_data_vars = {
            'ssh_keys': self.getSshKey()
        }

        user_data_template = os.path.join(
            self.getConfigsDir(),
            "user-data.yaml")

        template_rendered = render(user_data_template, user_data_vars)

        logging.debug("Rendered user-data config: %s", template_rendered)

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

        logging.debug("Rendered meta-data config: %s", template_rendered)

        if self.args.dry_run:
            logging.info("DRY RUN: Did not actually write meta-data.")
            return

        with open(os.path.join(self.getVmDirectory(), "meta-data"), "w") as cc:
            cc.write(template_rendered)

    def createVmSeedImage(self):
        """create VM seed image containing user/meta data."""
        # TODO: Add network config
        logging.info("Writing VM seed image with user and meta data.")
        command_line = ["/usr/bin/cloud-localds",
                        self.getVmSeedImagePath(),
                        os.path.join(self.getVmDirectory(), "user-data"),
                        os.path.join(self.getVmDirectory(), "meta-data")]
        if self.args.dry_run:
            logging.info("DRY RUN. Would have run: %s.", command_line)
            return
        try:
            output = subprocess.check_output(command_line,
                stderr=subprocess.STDOUT)
            logging.debug("Command line %s; Output: %s", command_line, output)
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
                logging.debug("Disk image creation output: %s", output)
        except subprocess.CalledProcessError as err:
            logging.critical("Error in creating disk image: %s.", err.output)

    def getVirtInstallCustomFlags(self):
        return {
            'disk': ["vol=%s/%s,cache=none,bus=virtio" % (self.getDiskPoolName(),
                                              self.getVmDiskImageName()),
                    "%s,cache=none,bus=virtio" % (self.getVmSeedImagePath())],
            'boot': 'hd',
        }
