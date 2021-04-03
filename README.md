# virtbuilder

virtbuilder is a helpful wrapper script that makes creating virtual machines managed by libvirt a lot easier.

## Functionality Provided

* Delete pre-existing VM and VM disk images before creating a new one.
* Ubuntu and Debian installs without needing to download an ISO locally.
* Secure etcd-client configuration for flannel.
* Listing disk pools and volumes in those libvirt disk pools.

Supported types of virtual machines that can be created:
* Debian
* Ubuntu (libvirt and proxmox)


## Assumptions

* Libvirt is configured on your VM host machine with at least one disk pool and bridged network interface.

## Requirements

* Python
* Python3-pip
* Python module: bs4, ipaddress, libvirt, jinja2, netaddr, proxmoxer, python3-requests
## Usage

## Docker Container

```
docker run --rm -it -v /path/to/proxmox-token.txt:/proxmox-prod-apitoken.txt jforman/vmbuilder:latest ./vmbuilder.py .... --config /proxmox/prod-apitoken.txt
```

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
