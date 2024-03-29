#!/usr/bin/env python3
"""A helpful wrapper for using libvirt to create virtual machines."""
import argparse
import logging
import os
import sys

from vmtypes import VMBuilder

def parseArgs():
    """Parse and return command line flags."""
    parser = argparse.ArgumentParser(
        description="Building libvirt and Proxmox virtual machines, made easy.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    commands = parser.add_argument_group('commands')
    commands.add_argument('command',
                          type=str,
                          choices=['create_vm',
                                   'list_disk_pools',
                                   'list_network_interfaces',
                                   'list_pool_volumes'])

    parser.add_argument("--debug",
                        action="store_true",
                        help="Display debug output.")
    parser.add_argument("--deleteifexists",
                        action="store_true",
                        help="Delete VM data if it exists.")
    parser.add_argument("--dry_run",
                        action="store_true",
                        help=("Don't execute anything, just print out "
                              "what would have been done."))
    parser.add_argument("--cluster_size",
                        default=1,
                        type=int,
                        help=("Create a number of VM instances. "
                              "Default: %(default)s"))
    parser.add_argument("--cluster_start_index",
                        default=0,
                        type=int,
                        help="VM name suffix to start using when creating multiple VMs.")
    parser.add_argument("--timeout_secs",
                        help="Timeout in seconds to wait for any single operation.",
                        type=int,
                        default=300)
    parser.add_argument("--config", help="Virthelper config.")
    parser.add_argument("--cluster", help="Cluster name in config file.")

    vm_props = parser.add_argument_group('vm properties')
    vm_props.add_argument("--bridge_interface",
                          help=("NIC/VLAN to bridge."
                                "See command list_network_interfaces"))
    vm_props.add_argument("--cpus",
                          type=int,
                          default=1,
                          help="Number of CPUs. Default: %(default)d")
    vm_props.add_argument("--disk_size_gb",
                          default=10,
                          type=int,
                          help=("Size (GB) of disk image. "
                                "Default: %(default)d"))
    vm_props.add_argument("--domain_name",
                          help="VM domain name. Default: %(default)s")
    vm_props.add_argument("--memory",
                          type=int,
                          default=512,
                          choices=[512, 1024, 2048, 4096, 8192],
                          help="Amount of RAM, in MB. Default: %(default)d")
    vm_props.add_argument("--vm_storage_pool",
                          help=("Disk pool for VM disk storage."
                                "See command list_disk_pools"))
    vm_props.add_argument("--vm_type",
                          choices=["debian",
                                   "ubuntu", "ubuntu-cloud",
                                   "proxmox-ubuntu-cloud"],
                          help="Type of VM to create.")
    vm_props.add_argument("--host_name",
                          help="Virtual Machine Base Hostname")
    vm_props.add_argument("--use_uefi",
                          action="store_true",
                          help="Enable UEFI support during boot.")
    vm_props.add_argument("--ldap_uri",
                          help="URI for LDAP server.")
    vm_props.add_argument("--ldap_basedn",
                          help="LDAP base DN for user system authentication.")
    vm_props.add_argument("--default_user",
                          default="ubuntu",
                          help="Default username for Virtual Machine.")


    network_props = parser.add_argument_group('network properties')
    network_props.add_argument("--ip_address",
                               help="IP Address of the VM.")
    network_props.add_argument("--nameserver",
                               action='append',
                               help="IP Address of DNS server. Multiple servers accepted.")
    network_props.add_argument("--netmask",
                               help="IPv4 CIDR Netmask or IPv6 Network Preflix length for static config.")
    network_props.add_argument("--gateway",
                               help="IP Address of default gateway.")
    network_props.add_argument("--mac_address",
                               help="Hard-coded network interface MAC address.")

    vm_host_props = parser.add_argument_group('vm host properties')
    vm_host_props.add_argument("--vm_host",
                               default="localhost",
                               help="VM host. Default: %(default)s")

    debian_args = parser.add_argument_group('debian-based vm properties')
    debian_args.add_argument("--preseed_url",
                             help="URL of Debian-based OS install preseed file.")
    debian_args.add_argument("--debian_release",
                             default="stretch",
                             help="Debian OS release codename to install. Default: %(default)s.")
    debian_args.add_argument("--ubuntu_release",
                             default="artful",
                             help="Ubuntu OS release to install. Default: %(default)s")
    debian_args.add_argument("--dist_mirror",
                             help="Installation Mirror. Default: %(default)s",
                             default="mirrors.mit.edu")

    proxmox_args = parser.add_argument_group('proxmox related arguments')
    proxmox_args.add_argument("--proxmox_template",
                              help="VM template to use as base for VM install.")
    proxmox_args.add_argument("--proxmox_storage",
                              help="Target storage name for VM installs.")
    proxmox_args.add_argument("--proxmox_sshkeys",
                              help="SSH keys to install on VM.")
    proxmox_args.add_argument("--noverify_ssl",
                              action="store_false",
                              help="Disable verifying SSL certificate on Proxmox API endpoint.")

    args = parser.parse_args()
    startup_errors = False
    network_args = [args.ip_address, args.nameserver, args.gateway, args.netmask]
    if any(network_args) and not all(network_args):
        logging.critical("To configure static networking, IP address, "
                         "nameserver, netmask, and gateway are ALL required,")
        startup_errors = True

    ldap_args = [args.ldap_uri, args.ldap_basedn]
    if any(ldap_args) and not all(ldap_args):
        logging.fatal("To configure LDAP, you must specify both --ldap_uri and "
                      "--ldap_basedn.")
        startup_errors = True

    if args.config and not os.path.exists(args.config):
        logging.fatal(f"Specified config {args.config} does not exist.")
        startup_errors = True

    if not args.host_name:
        logging.fatal(f"No host_name argument was specified. This is required for VM creation.")

    if startup_errors:
        sys.exit(1)
    return args


def main():
    """Main function for handling VM and disk creation."""

    args = parseArgs()

    vm = VMBuilder(args)

    if vm.args.command == 'list_disk_pools':
        print(vm.getDiskPools())
    elif vm.args.command == 'list_pool_volumes':
        print(vm.getDiskPoolVolumes())
    elif vm.args.command == 'create_vm':
        logging.debug("about to run vm.getbuild.createvm")
        vm.verifyMinimumCreateVMArgs()
        vm.getBuild().createVM()
    else:
        logging.critical("The command you entered is not recognized.")

if __name__ == "__main__":
    sys.exit(main())
