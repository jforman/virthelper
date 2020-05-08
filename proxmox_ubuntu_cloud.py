"""Ubuntu Cloud on Proxmox virtual machine builder library."""

from proxmoxer import ProxmoxAPI
import logging

import vmtypes
import sys

class ProxmoxUbuntuCloud(vmtypes.BaseVM):
    """Ubuntu-Cloud Proxmox configuration."""

    name = "ProxmoxUbuntuCloud"

    def __init__(self):
        super(ProxmoxUbuntuCloud, self).__init__()
        self.proxmox = ProxmoxAPI(
            self.args.vm_host,
            user=self.args.proxmox_username,
            password=self.args.proxmox_password,
            verify_ssl=False)
        self.allvminfo = {}
        self.getAllVMInfo()

    def getAllVMInfo(self):
        """Make a dict containing information on all VMs."""
        logging.info("Creating dict of all VM info.")
        if self.allvminfo:
            return self.allvminfo
        for node in self.proxmox.nodes.get():
            logging.debug(f"Looking for VMs on node {node['node']}.")
            for vm in self.proxmox.nodes(node['node']).qemu.get():
                logging.debug(f"Found VM: {vm['name']}.")
                self.allvminfo[vm['name']] = vm
                self.allvminfo[vm['name']]['node'] = node
        logging.info(f"Found {len(self.allvminfo)} VMs.")
        logging.info("Done creating dict of all VM info.")

    def normalizeVMState(self):
        """Delete VM if one of same name is found."""
        logging.info(f"Normalizing VM state for VM {self.getVmName()}.")
        vm_dict = {}
        if not bool(self.getAllVMInfo()):
            # No VMs are found in the cluster.
            return

        if self.getVmName() in self.getAllVMInfo().keys():
            logging.info(f"Found a VM by {self.getVmName()} already exists.")
            if self.args.deleteifexists:
                logging.info("Deleting existing VM.")
                self.proxmox.nodes(node['node']).qemu(vm['vmid']).delete()
                logging.debug("Finished deleting VM.")
                return
            else:
                logging.critical(
                    "Existing VM by that name already found, but --deleteifexists flag "
                    "not passed. Exiting.")
                sys.exit(1)
        logging.debug("Done with normalizeVmState.")
