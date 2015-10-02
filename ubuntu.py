import logging

from vmbuilder import VMBuilder

class Ubuntu(VMBuilder):

  def __init__(self):
      super(Ubuntu, self).__init__()

  def composeVirtinstallArgs(self):
      extra_args = ("\"" +
                    "console=tty0 console=ttyS0,115200n8 " +
                    "console-keymaps-at/keymap=us " +
                    "console-setup/ask_detect=false " +
                    "console-setup/layoutcode=us " +
                    "keyboard-configuration/layout=USA " +
                    "keyboard-configuration/variant=US " +
                    "locale=en_US.UTF-8 " +
                    "netcfg/get_domain=" + self.args.domain_name + " " +
                    "netcfg/get_hostname=" + self.args.host_name + " " +
                    "preseed/url=http://autobahn.jeffreyforman.net/jf-custom.preseed serial")

      # NOTE: This is going to blow up. test and remove?
      if self.args.ip_address:
          network_info = NETWORK_CONFIG[self.args.bridge_interface]
          if not self.args.ip_address.startswith(network_info['network']):
              logging.error("You assigned an IP address (%s) that does not match the requested interface (%s).", args.ip_address,
                            self.args.bridge_interface)
              raise HandledException

          extra_args += (" " +
                         "netcfg/get_nameservers=" + network_info['nameserver'] + " " +
                         "netcfg/get_ipaddress=" + self.args.ip_address + " " +
                         "netcfg/get_netmask=" + self.network_info['netmask'] + " " +
                         "netcfg/get_gateway=" + self.network_info['gateway'] + " " +
                         "netcfg/confirm_static=true " +
                         "netcfg/disable_autoconfig=true")

      extra_args += "\""

      self.flags = {
          "connect": "qemu+ssh://%s/system" % self.args.vm_host,
          "disk": "vol=%s/%s.%s,cache=none" % (self.args.disk_pool_name,
                                               self.args.host_name,
                                               self.args.domain_name),
          "extra-args": extra_args,
          "location": self.args.location,
          "name": "%s.%s" % (self.args.host_name, self.args.domain_name),
          "network": "bridge=%s" % self.args.bridge_interface,
          "os-type": "linux",
          "ram": self.args.memory,
          "vcpus": self.args.cpus,
          "virt-type": "kvm",
      }
