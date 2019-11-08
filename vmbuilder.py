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
        description="Building libvirt virtual machines, made easy.",
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
    vm_props.add_argument("--disk_pool_name",
                          help=("Disk pool for VM disk image storage."
                                "See command list_disk_pools"))
    vm_props.add_argument("--vm_type",
                          choices=["coreos", "debian",
                          "ubuntu", "ubuntu-cloud"],
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

    network_props = parser.add_argument_group('network properties')
    network_props.add_argument("--ip_address",
                               help="IP Address of the VM.")
    network_props.add_argument("--nameserver",
                               action='append',
                               help="IP Address of DNS server. Multiple servers accepted.")
    network_props.add_argument("--netmask",
                               help="IP Netmask for static config.")
    network_props.add_argument("--gateway",
                               help="IP Address of default gateway.")
    network_props.add_argument("--mac_address",
                               help="Hard-coded network interface MAC address.")

    vm_host_props = parser.add_argument_group('vm host properties')
    vm_host_props.add_argument("--vm_host",
                               default="localhost",
                               help="VM host. Default: %(default)s")

    coreos_args = parser.add_argument_group('coreos vm properties')
    coreos_args.add_argument("--coreos_ssl_certs_dir",
                             default="/etc/ssl/certs",
                             help=("Path for storing SSL certs on "
                                   "CoreOS host."))
    coreos_args.add_argument("--coreos_channel",
                             choices=["stable", "beta", "alpha"],
                             default="stable",
                             help=("Channel of CoreOS image for VM base. "
                                   "Default: %(default)s."))
    coreos_args.add_argument("--coreos_image_age",
                             default=7,
                             help=("Age (days) of CoreOS base image before "
                                   "downloading a new one. "
                                   "Default: %(default)s"))
    coreos_args.add_argument("--coreos_cloud_config_template",
                             default=os.path.join(
                                 os.path.dirname(
                                     os.path.realpath(__file__)),
                                 "configs",
                                 "coreos_user_data.template"),
                             help=("Jinja2 template for CoreOS cloud config "
                                   "user_data. Default: %(default)s"))
    coreos_args.add_argument("--coreos_create_cluster",
                             action="store_true",
                             help="Create an etcd cluster containing the "
                                  "instance(s).")
    coreos_args.add_argument("--coreos_cluster_overlay_network",
                             default="10.123.0.0/16",
                             help="Default overlay network used for "
                                "Flannel clustering. Default: %(default)s")
    coreos_args.add_argument("--coreos_nfs_mount",
                             action="append",
                             help="Mount Host:Mount tuple on CoreOS machine.")
    coreos_args.add_argument("--coreos_ct_version",
                             default="0.5.0",
                             help=("Version of CoreOS config transpiler "
                             "in the creation of the Ignition config."))

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

    args = parser.parse_args()
    network_args = [args.ip_address, args.nameserver, args.gateway, args.netmask]
    if any(network_args) and not all(network_args):
        logging.critical("To configure static networking, IP address, "
                         "nameserver, netmask, and gateway are ALL required,")

    ldap_args = [args.ldap_uri, args.ldap_basedn]
    if any(ldap_args) and not all(ldap_args):
        logging.fatal("To configure LDAP, you must specify both --ldap_uri and "
                      "--ldap_basedn.")

    return args


def main():
    """Main function for handling VM and disk creation."""

    args = parseArgs()

    vm = VMBuilder(args)

    if vm.args.command == 'list_disk_pools':
        print(vm.getDiskPools())
    elif vm.args.command == 'list_pool_volumes':
        print(m.getDiskPoolVolumes())
    elif vm.args.command == 'create_vm':
        logging.debug("about to run vm.getbuild.createvm")
        vm.verifyMinimumCreateVMArgs()
        vm.getBuild().createVM()
    else:
        logging.critical("The command you entered is not recognized.")

if __name__ == "__main__":
    sys.exit(main())
