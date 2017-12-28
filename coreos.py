"""CoreOS-specific virtual machine builder library."""

import logging
import os
import shutil
import stat
import subprocess
import time
import urllib
from urlparse import urljoin
import vmtypes

import jinja2

from bs4 import BeautifulSoup

from vmbuilder import HandledException


class CoreOS(vmtypes.BaseVM):
    """CoreOS VM base class."""

    discovery_url = None

    def __init__(self):
        super(CoreOS, self).__init__()
        self.clconfig_rendered = ""

    def getCompressedLocalSnapshotImagePath(self):
        """Return absolute local path of compressed CoreOS snapshot image."""

        img = "coreos_production_qemu_image-%s.img.bz2" % self.getCoreOSChannel()
        return os.path.join(self.getDiskPoolPath(), img)

    def getUnCompressedLocalSnapshotImagePath(self):
        """Return absolute local path of uncompressed CoreOS snapshot image."""
        return self.getCompressedLocalSnapshotImagePath().rstrip(".bz2")

    def getCoreosConfigBasePath(self):
        """Return absolute directory path for configs for CoreOS hosts."""
        return os.path.join(self.getDiskPoolPath(), "coreos")

    def getCloudConfigDir(self):
        """Return absolute directory path of VM's cloud config directory."""
        return os.path.join(self.getCoreosConfigBasePath(),
                            self.getVmName())

    def getCloudConfigPath(self):
        """Return absolute path to VM's Container Linux config file."""
        return os.path.join(self.getCloudConfigDir(), "config.cl")

    def getCoreosXmlPath(self):
        """Return absolute path to VM's XML config."""
        return os.path.join(self.getCloudConfigDir(), "vm.xml")

    def getCtPath(self):
        """Return absolute path to config transpiler for CoreOS."""
        return os.path.join(self.getCoreosConfigBasePath(),
                            "ct-v%s" % self.args.coreos_ct_version)

    def getIgnitionConfigPath(self):
        """Return absolute path to VM's Ignition config file."""
        return os.path.join(self.getCloudConfigDir(), "config.ign")

    def getCloudConfigTemplate(self):
        """Retun absolute path to cloud config template file."""
        return self.args.coreos_cloud_config_template

    def getCoreOSImageAge(self):
        """Return CoreOS image age threshold (days)."""
        return self.args.coreos_image_age

    def getCoreOSChannel(self):
        """Return the CoreOS channel used to create image."""
        return self.args.coreos_channel

    def getClusterOverlayNetwork(self):
        """Return CIDR string used for CoreOS flannel network.

        Example: '10.123.0.0/16'
        """
        return self.args.coreos_cluster_overlay_network

    def deleteVM(self):
        """Undefine a VM image in libvirt."""
        super(CoreOS, self).deleteVM()
        logging.debug("Trying to delete cloud config dir: %s.",
                      self.getCloudConfigDir())
        if os.path.exists(self.getCloudConfigDir()):
            if self.args.dry_run:
                logging.info("DRY RUN: Would have attempted to remove cloud "
                             "config path: %s", self.getCloudConfigDir())
                return

            if self.args.deleteifexists:
                logging.info("Attempting to remove cloud config path for %s: %s",
                             self.getVmName(), self.getCloudConfigDir())
                shutil.rmtree(self.getCloudConfigDir())
            else:
                logging.info("Tried to remove %s path, but --deleteifexists "
                             "flag not passed.", self.getCloudConfigDir())
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
                     self.getCompressedLocalSnapshotImagePath())

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
            # print-xml causes the XML for the domain to be printed to the
            # console and not actually create the VM.
            "print-xml": "",
        }
        return extra_args

    def getVirtInstallFinalArgs(self):
        """String args at the very end of a virt-install run."""
        return "> %s" % (self.getCoreosXmlPath())

    def executePostVirtInstall(self):
        """Specify Ignition config in Libvirt VM XML configuration."""

        if self.args.dry_run:
            logging.info("DRY RUN: TODO: Read in-memory copy of XML and "
                         "a way to show the edited copy on stdout.")
            return

        with open(self.getCoreosXmlPath(), 'r') as xml_file:
            vmxml = xml_file.read()

        logging.info("Reading libvirt XML file for virtual machine.")
        soup = BeautifulSoup(vmxml, "xml")
        soup.domain['xmlns:qemu'] = 'http://libvirt.org/schemas/domain/qemu/1.0'

        domain = soup.domain
        qemu_commandline = soup.new_tag('commandline', nsprefix='qemu')
        arg_fwcfg = soup.new_tag('arg', nsprefix='qemu')
        arg_fwcfg['value'] = '-fw_cfg'
        qemu_commandline.append(arg_fwcfg)

        arg_name = soup.new_tag('arg', nsprefix='qemu')
        arg_name['value'] = ("name=opt/com.coreos/config,file=%s" % self.getIgnitionConfigPath())
        qemu_commandline.append(arg_name)

        domain.append(qemu_commandline)

        logging.debug("Modified Libvirt XML with Ignition command-line params:")
        logging.debug(soup.prettify())

        with open(self.getCoreosXmlPath(), 'w') as xml_file:
            xml_file.write(str(soup))
        self.getBuild().defineAndStartVm()

    def downloadCt(self):
        """Download config transpiler from CoreOS.
        https://coreos.com/os/docs/latest/overview-of-ct.html
        https://github.com/coreos/container-linux-config-transpiler/
        Filename structure: v{VER}/ct-v{VER}-x86_x64-unknown-linux-gnu
        """
        if os.path.exists(self.getCtPath()):
            logging.info("Config transpiler version %s already downloaded "
                         "locally.", self.args.coreos_ct_version)
            return

        github_project_release_path = ("https://github.com/coreos/"
                                       "container-linux-config-transpiler/"
                                       "releases/download/")
        version_path = "v%s/ct-v%s-x86_64-unknown-linux-gnu" % (
            self.args.coreos_ct_version,
            self.args.coreos_ct_version)
        logging.info("Attempting to download %s to %s.",
                     urljoin(github_project_release_path, version_path),
                     self.getCtPath())

        urllib.urlretrieve(urljoin(github_project_release_path,
                                   version_path),
                           self.getCtPath())
        logging.info("Finished download of %s to %s",
                     urljoin(github_project_release_path, version_path),
                     self.getCtPath())
        st = os.stat(self.getCtPath())
        os.chmod(self.getCtPath(), st.st_mode | stat.S_IXUSR | stat.S_IXGRP)

    def writeIgnitionConfig(self):
        """Given a Container Linux config, transpile into an Ignition config."""
        if not os.path.exists(self.getCtPath()):
            logging.error("Config transpiler not found. Expected it at: %s.",
                          self.getCtPath())
            raise HandledException

        command_line = [self.getCtPath(),
                        "-pretty",
                        "-strict",
                        "-platform", "vagrant-virtualbox"]

        try:
            if self.args.dry_run:
                logging.info("Reading the Container Linux config from memory "
                             "so I can attempt to transpile an Ignition "
                             "config.")
                logging.info("DRY RUN ct command line: %s", command_line)

                ct_cmd = subprocess.Popen(command_line,
                                          stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE)
                output = ct_cmd.communicate(input=self.clconfig_rendered)[0]
                logging.info("Successfully generated in-memory dry-run "
                             "Ignition config.")
            else:
                logging.debug("Input file: %s, Ouput File: %s.",
                              self.getCloudConfigPath(),
                              self.getIgnitionConfigPath())
                command_line.extend([
                    "-in-file", self.getCloudConfigPath(),
                    "-out-file", self.getIgnitionConfigPath()])
                logging.debug("Ignition Config generation command line: %s.",
                              command_line)
                output = subprocess.check_output(command_line,
                                                 stderr=subprocess.STDOUT)
                logging.info("Successfully wrote Ignition config: %s",
                             self.getIgnitionConfigPath())
        except subprocess.CalledProcessError as err:
            logging.error("Error in creating Ignition Config: %s.", err.output)
            raise HandledException

        logging.debug("Command line: %s.", command_line)
        logging.debug("Output: %s.", output)


    def defineAndStartVm(self):
        """Define (load) VM XML into libvirt and start VM."""
        commands = [
            ["virsh", "define", self.getCoreosXmlPath()],
            ["virsh", "start", self.getVmName()]
        ]

        for command_line in commands:
            try:
                subprocess.check_output(command_line)
            except subprocess.CalledProcessError as err:
                logging.error("Error while loading VM into libvirt: %s.",
                              err.output)
                raise HandledException

    def executePreVirtInstall(self):
        """Execute CoreOS-specific commands before running virt-install."""
        self.writeCloudConfig()
        self.downloadCt()
        self.writeIgnitionConfig()

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
        durl_req = urllib.urlopen("https://discovery.etcd.io/new?size=%d" % self.args.cluster_size)
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
            _, mount_point = current_set.split(":")
            name = mount_point.replace('/', '-').lstrip('-')
            mounts.append({'name': name,
                           'what': current_set,
                           'where': mount_point})
        return mounts

    def writeCloudConfig(self):
        """Write VM's cloud config data to file."""

        def render(template_file, context):
            """Function to fill in variables in jinja2 template file."""
            path, filename = os.path.split(template_file)
            return jinja2.Environment(
                loader=jinja2.FileSystemLoader(path)
                ).get_template(filename).render(context)

        cloud_config_vars = {
            'coreos_channel': self.getCoreOSChannel(),
            'etcd_listen_host': self.getVmName(),
            'ssh_keys': self.getSshKey(),
            'ip_address': '"{"PRIVATE_IPV4"}""',
            'vm_name': self.getVmName(),
        }

        if self.getNfsMounts():
            cloud_config_vars.update({'nfs_mounts': self.getNfsMounts()})

        if self.args.coreos_create_cluster:
            cloud_config_vars.update({
                'cluster_overlay_network': self.getClusterOverlayNetwork(),
                'create_cluster': 1,
                'discovery_url': self.getDiscoveryURL(),
            })

        logging.debug("Checking if static networking is enabled.")
        static_network = all([
            self.getIPAddress(),
            self.getNetmask(),
            self.getGateway()])

        logging.debug("Is static network configured? %s.", static_network)

        if static_network:
            cloud_config_vars.update({
                'static_network': True,
                'dns': self.getNameserver(),
                'gateway': self.getGateway(),
                'ip_address': self.getIPAddress(),
                'network_prefixlen': self.getPrefixLength(
                    self.getIPAddress(),
                    self.getNetmask()),
                'etcd_listen_host': self.getIPAddress(),
            })


        logging.debug("Cloud Config Vars: %s", cloud_config_vars)



        template_rendered = render(self.getCloudConfigTemplate(),
                                   cloud_config_vars)

        logging.debug("Cloud Config to be written:\n%s", template_rendered)

        if self.args.dry_run:
            logging.info("DRY RUN: Did not actually write Cloud Config.")
            self.clconfig_rendered = template_rendered
            return

        if not os.path.exists(os.path.dirname(self.getCloudConfigPath())):
            os.makedirs(self.getCloudConfigDir())

        with open(self.getCloudConfigPath(), "w") as cloud_config:
            cloud_config.write(template_rendered)
