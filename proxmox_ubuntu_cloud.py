"""Ubuntu Cloud on Proxmox virtual machine builder library."""

# pylint: disable=logging-fstring-interpolation

import logging
import time
import configparser
import sys
import urllib.parse
import requests
from proxmoxer import ProxmoxAPI
import vmtypes

class ProxmoxUbuntuCloud(vmtypes.BaseVM):
    """Ubuntu-Cloud Proxmox configuration."""

    name = "ProxmoxUbuntuCloud"

    def __init__(self):
        super(ProxmoxUbuntuCloud, self).__init__()
        auth_params = self.getAuthParams(
            self.args.config,
            self.args.cluster)
        self.proxmox = ProxmoxAPI(
            self.args.vm_host,
            user=auth_params['user'],
            token_name=auth_params['token'],
            token_value=auth_params['secret'],
            verify_ssl=False)
        self.allvminfo = {}
        self.getAllVMInfo()

    def getAuthParams(self, cf, cluster):
        """read API auth parameters from config file."""
        cfg = configparser.ConfigParser()
        cfg.read(cf)
        if not cfg.has_section(cluster):
            logging.error(f"Did not find cluster {cluster} in authentication config.")
            sys.exit(1)
        params = cfg.items(cluster)
        pd = dict(params)
        logging.info(f"Using authentication params: User: {pd['user']}; Token: {pd['token']}.")
        return pd

    def getNodeName(self):
        """return node name from vm_host."""
        node_name = self.args.vm_host.split(".")[0]
        logging.debug(f"Returning node name {node_name} from vm host {self.args.vm_host}.")
        return node_name

    def getAllVMInfo(self):
        """Make a dict containing information on all VMs."""
        if not self.allvminfo:
            logging.info("Creating dict of all VM info.")
            for node in self.proxmox.nodes.get():
                logging.debug(f"Looking for VMs on node {node['node']}.")
                for vm in self.proxmox.nodes(node['node']).qemu.get():
                    logging.debug(f"Found VM: {vm['name']}.")
                    self.allvminfo[vm['vmid']] = vm
                    self.allvminfo[vm['vmid']]['node'] = node['node']
            logging.info(f"Found {len(self.allvminfo)} VMs.")
            logging.info("Done creating dict of all VM info.")
            logging.debug(f"All VM Info: {self.allvminfo}.")
        return self.allvminfo

    def checkTaskStatus(self, node, upid, timeout_secs):
        """given a task puid, check status and adhere to timeout."""
        deadline_time = time.time() + timeout_secs
        sleep_time = 10
        while 1:
            if time.time() > deadline_time:
                logging.error(f"Timeout reached waiting on task {upid} on node {node}.")
                sys.exit(1)
            upid_status = self.proxmox.nodes(node).tasks(upid).status.get()
            task_status = upid_status["status"]
            if task_status == "running":
                logging.info(f"Current task status: {upid_status['status']}; "
                             f" PID: {upid_status['pid']}.")
                logging.debug(f"Remaining time before task times out: "
                              f"{deadline_time - time.time()} secs.")
                time.sleep(sleep_time)
                continue
            exit_status = upid_status["exitstatus"]
            if task_status == "stopped" and exit_status == "OK":
                logging.info("Task exited OK.")
                logging.debug(f"Return Value: {upid_status}.")
                return

            logging.error(f"Task status exited NOT OK: {exit_status}. Return Value: {upid_status}.")
            sys.exit(1)


    def getNextVMId(self):
        """return next available VM ID."""
        if self.args.dry_run:
            logging.info("DRY RUN: Would have retrieved next VM ID. Faking it with -1.")
            next_id = -1
        else:
            next_id = self.proxmox.cluster.nextid.get()
            logging.info(f"Next available VM ID is {next_id}.")
        return next_id

    def normalizeVMState(self):
        """Delete VM if one of same name is found."""
        existing_found = False
        logging.info(f"Seeing if other VMs of same name {self.getVmName()} exist..")
        if not bool(self.getAllVMInfo()):
            # No VMs are found in the cluster.
            return

        for vmid, vmvalues in self.getAllVMInfo().items():
            if self.getVmName() == vmvalues['name']:
                logging.info(f"Found VM{vmid} with same name {self.getVmName()} that already exists.")
                node = vmvalues['node']
                if self.args.dry_run:
                    logging.info(f"DRY RUN: Would have stopped, and deleted VM({vmid}) {self.getVmName()}.")
                    continue
                if self.args.deleteifexists:
                    logging.info(f"Stopping existing VM({vmid}): {self.getVmName()}.")
                    status = self.proxmox.nodes(node).qemu(vmid).status.stop.post()
                    self.checkTaskStatus(node, status, self.args.timeout_secs)
                    logging.info(f"Stopped existing VM({vmid}): {self.getVmName()}.")
                    logging.info(f"Deleting existing VM({vmid}): {self.getVmName()}.")
                    status = self.proxmox.nodes(node).qemu(vmid).delete()
                    self.checkTaskStatus(node, status, self.args.timeout_secs)
                    logging.debug(f"Finished deleting VM({vmid}): {self.getVmName()}.")
                    return
                else:
                    logging.critical(
                        f"Existing VM({vmid}) by that name already found, "
                        f"but --deleteifexists flag not passed. Exiting.")
                    existing_found = True

        if existing_found:
            sys.exit(1)
        else:
            logging.info(f"Did not find pre-existing VM of name {self.getVmName()}.")

        logging.debug("Done with normalizeVmState.")

    def createDiskImage(self):
        """Create disk image."""
        # Proxmox uses the cloud disk image as the image itself for the VM.
        # We don't create a seperate disk image in this instance.

    def getNetVMId(self):
        """get next available VM id."""
        self.proxmox.cluster.nextid.get()

    def getViableNode(self):
        """Return node name to install VM to."""
        # TODO: make this smarter than just picking the node that was passed
        #  as a flag. check for available ram/cpu on the node compared to
        #  what VM is requesting.
        # nodes = [x['node'] for x in self.proxmox.nodes.get()]
        # logging.debug(f"Found viable nodes: {nodes}.")
        # return nodes[0]
        node = self.args.vm_host.split(".")[0]
        logging.debug(f"Found viable node: {node}.")
        return node

    def getNetworkConfig(self):
        """Return cloudinit-friendly ipconfigN string for VM."""
        ip = self.getIPAddress()
        if not ip:
            ipconfig = "ip=dhcp,ip6=auto"
        else:
            cidr = self.getPrefixLength(ip, self.getNetmask())
            ipconfig = f"ip={ip}/{cidr},gw={self.getGateway()}"
        logging.debug(f"Network ipconfig0: {ipconfig}")
        return ipconfig

    def getTemplateVMId(self, template_name):
        """return VM ID of VM template."""
        template_vms = {}
        for vm in self.getAllVMInfo().values():
            tags = vm['tags'].split(',')
            logging.debug(f"Found tags {tags} for {vm['name']}.")
            if 'template' in tags and self.getAllVMInfo()[vm['vmid']]['node'] == self.getNodeName():
                template_vms[vm['name']] = vm['vmid']
        logging.debug(f"Found template VMs: {template_vms}.")
        try:
            template_id = template_vms[template_name]
            logging.info(f"Found template VM ID: {template_id} for {template_name}.")
        except KeyError:
            logging.error(f"Did not find a template VM for {template_name} on node requested for install.")
            sys.exit(1)
        return template_id

    def getSSHKeys(self):
        """Given a path, read the SSH keys into a string."""
        if self.args.proxmox_sshkeys.startswith('http'):
            sshkeys = requests.get(self.args.proxmox_sshkeys).text
        else:
            with open(self.args.proxmox_sshkeys, 'r') as f:
                sshkeys = f.read()
        logging.debug(f"SSH keys as retrieved: {sshkeys}")
        return sshkeys

    def executeVirtInstall(self):
        """Create VM. Set any options."""
        new_vmid = self.getNextVMId()
        node = self.getViableNode()
        logging.info(f"Beginning VM installation of ID:{new_vmid} on {node} of {self.getVmName()}.")
        template_vmid = self.getTemplateVMId(self.args.proxmox_template)

        clone_options = {
            'name': self.getVmName(),
            'newid': new_vmid,
            'full': 1,
            'format': 'raw',
            'storage': self.getVmStoragePoolName(),
        }
        logging.debug(f"Clone Options: {clone_options}.")

        if self.args.dry_run:
            logging.info(f"DRY RUN: Would have cloned VM {template_vmid} to "
                         f"{new_vmid} using template {self.args.proxmox_template}.")
        else:
            clone_output = self.proxmox.nodes(node).qemu(template_vmid).clone.post(**clone_options)
            logging.info(f"VM Cloning operation output: {clone_output}.")
            self.checkTaskStatus(
                node,
                clone_output,
                self.args.timeout_secs)

        resize_options = {
            'disk': "scsi0",
            'size': f"{self.args.disk_size_gb}G",
        }

        if self.args.dry_run:
            logging.info(f"DRY RUN: Would have resized disk on VM{new_vmid} with options: {resize_options}.")
        else:
            logging.info(f"Resizing disk on VM{new_vmid} with options: {resize_options}.")
            self.proxmox.nodes(node).qemu(new_vmid).resize().put(**resize_options)

        vm_dict = {
            'ciuser': self.getDefaultUser(),
            'ipconfig0': self.getNetworkConfig(),
            'memory': self.getRam(),
            'net0': f"model=virtio,bridge={self.getNetworkBridgeInterface()}",
            'onboot': 1,
            'ostype': 'l26',
            'sockets': self.getCpus(),
            #'unique': 1,
            'tags': "", # zero out the tags because they are copied from the template.
        }

        if self.getNameserver():
            vm_dict.update({'nameserver': self.getNameserver()})

        if self.args.proxmox_sshkeys:
            vm_dict.update({'sshkeys': urllib.parse.quote(self.getSSHKeys(), safe='')})

        if self.args.dry_run:
            logging.info(f"DRY RUN: Would have set VM {new_vmid} options: {vm_dict}.")
        else:
            ret_val = self.proxmox.nodes(node).qemu(new_vmid).config.post(**vm_dict)
            logging.debug(f"VM options setting output: {ret_val}.")
            logging.info(f"Done setting VM options.")

        if self.args.dry_run:
            logging.info(f"DRY RUN: Would have started VM {self.getVmName()}.")
        else:
            logging.info(f"Starting VM {self.getVmName()}.")
            self.proxmox.nodes(node).qemu(new_vmid).status.start.post()
        logging.info(f"Completed install of VM {self.getVmName()}.")
