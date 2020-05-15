# virtbuilder

virtbuilder is a helpful wrapper script that makes creating virtual machines managed by libvirt a lot easier.

## Functionality Provided

* Delete pre-existing VM and VM disk images before creating a new one.
* Ubuntu and Debian installs without needing to download an ISO locally.
* CoreOS support with ability to provide with a templated Container Linux config file.
* CoreOS etcd-based cluster support using CoreOS public Discovery service.
* Secure etcd-client configuration for flannel.
* Listing disk pools and volumes in those libvirt disk pools.

Supported types of virtual machines that can be created:
* CoreOS
* Debian
* Ubuntu (libvirt and proxmox)


## Assumptions

* Libvirt is configured on your VM host machine with at least one disk pool and bridged network interface.

## Requirements

* Python
* Python module: bs4, ipaddress, libvirt, jinja2, netaddr, proxmoxer, python3-requests

## Usage

### Informational Commands

Before actually creating your VM, it's important to know a few things.

What network interface do you want to bridge it to on your VM host? Yes, my script assumes you want to bridge to an interface.

What disk pool do you want to store your VM's root disk image in?

#### List disk pools on localhost

```
% ./vmbuilder.py list_disk_pools
['dump', 'default', 'localdump', 'boot-scratch']
```

#### List volumes in disk pool 'dump'

```
% ./vmbuilder.py --disk_pool dump list_pool_volumes
['cd58.iso']
```

#### List network interfaces

```
% ./vmbuilder.py list_network_interface
['br0', 'lo']
```

### Creating a Virtual Machine

There are several required parameters.

* bridge_interface
* disk_pool_name
* host_name
* domain_name
* vm_type

### Creating a single Debian/Ubuntu VM

```
vmbuilder.py --bridge_interface ${vm_host_iface} --disk_pool_name ${disk_pool_name} --host_name ${vm_name} --vm_type ${host_type} --domain_name ${vm_domainname} --preseed_url http://${fqdn}/mycustom.pressed create_vm
```

When creating a VM on Proxmox, it is important to tag all template VM's with the tag 'template'. The name of the VM will be needed as the argument to the `proxmox_template` flag.

### Creating a three-cluster CoreOS VM set.

If you want to tie your CoreOS VMs together into an etcd-based cluster the following flags are required:

* cluster_size: an integer for the number of CoreOS hosts to create.
* coreos_create_cluster: No value here is needed. This is used to tell the script to retrieve an etcd Discovery URL token used for all hosts.

**NOTE: etcd clustering is configured to use secure communications (https) with
self signed certificates.**

Certificates are expected to live in */etc/ssl/certs* hostname_with_index

* CA: ca.pem
* Client Certificate: etcd-client.pem
* Client Key: etcd-client-key.pem

```
vmbuilder.py \
--bridge_interface ${vm_host_iface} --disk_pool_name localdump --host_name ${base_name} --vm_type coreos --domain_name ${vm_domainname} --coreos_create_cluster --cluster_size ${cluster_size} create_vm
```

_TODO: Add support for en/disabling secure transport for etcd from command line._
_TODO: Add support for configuring SSL certificate directory from command line._

### A three-VM CoreOS cluster using static IP addressing for each CoreOS node.

Like the above example, but this time with static IP addresses.

Example uses 10.10.250.111 as the starting address for a three machine cluster. Therefore the IPs of the three machines, named coreF1, coreF2, and coreF3 are addressed 10.10.250.111, 10.10.250.112, and 10.10.250.113 respectively. Each coreOS machine uses 10.10.250.1 as their nameserver and default gateway.

```
vmbuilder.py create_vm --bridge_interface ${interface} --domain_name foo.dmz.example.net --disk_pool_name ${vm_store} --vm_type coreos --host_name coreF --cluster_size 3 --coreos_create_cluster --ip_address 10.10.250.111 --nameserver 10.10.250.1 --gateway 10.10.250.1 --netmask 255.255.255.0.
```

#### Adding an NFS mount to your CoreOS machine

An NFS mount stanza can be added to your cloud config file with the following flag.
```
--coreos_nfs_mount allmyfiles1:/foo/bar

The NFS directory of the remote server will be mounted on your CoreOS VM at /foo/bar.
```

## Notes

The CoreOS Container Linux configs, resultant Ignition configs as well as their
libvirt XML files are stored within the disk pool directory itself. Previously
these files were stored in the default libvirt/qemu directory within the host.

This provides for more resilient storage (on my host this is a ZFS-backed NFS
share which is backed up remotely). Because of this new directory location,
an update to the apparmor configuration file is needed. Explanation can be found
in this CoreOS bug: https://github.com/coreos/bugs/issues/2083
