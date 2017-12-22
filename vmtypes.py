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
