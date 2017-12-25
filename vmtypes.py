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
