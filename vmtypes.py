import logging

import vmbuilder

class CoreOS(vmbuilder.VMBuilder):

  def __init__(self):
      super(CoreOS, self).__init__()

class Debian(vmbuilder.VMBuilder):

  def __init__(self):
      super(Debian, self).__init__()

  def getExtraArgs(self):
    extra_args = {
      "keyboard-configuration/xkb-keymap": "us",
      "console-setup/ask_detect": "false",
      "locale": "en_US", #.UTF-8",
      "netcfg/get_domain": self.args.domain_name,
      "netcfg/get_hostname": self.args.host_name,
      "preseed/url": "http://10.10.0.1/jf-custom-debian.preseed"
      }

    # Order of console specs is important. tt0, ttyS0
    add_ons = ['serial', 'console=tty0', 'console=ttyS0,9600n8']

    # NOTE: This needs to be reimplemented.
    # if self.args.ip_address:
    #   network_info = NETWORK_CONFIG[self.args.bridge_interface]
    #   if not self.args.ip_address.startswith(network_info['network']):
    #     logging.error("You assigned an IP address (%s) that does not match the requested interface (%s).", args.ip_address,
    #                   self.args.bridge_interface)
    #   raise vmbuilder.HandledException
    #
    #   extra_args += (" " +
    #                "netcfg/get_nameservers=" + network_info['nameserver'] + " " +
    #                "netcfg/get_ipaddress=" + self.args.ip_address + " " +
    #                "netcfg/get_netmask=" + self.network_info['netmask'] + " " +
    #                "netcfg/get_gateway=" + self.network_info['gateway'] + " " +
    #                "netcfg/confirm_static=true " +
    #                "netcfg/disable_autoconfig=true")
    #
    # custom_flags += "\""

    result = []
    for key,value in extra_args.iteritems():
      result.append("%s=%s" % (key, value))
    result = " ".join(result)

    for current in add_ons:
      result += " %s" % current

    result = "\"%s\"" % result

    return result
      
class Ubuntu(Debian):

  def __init__(self):
      super(Ubuntu, self).__init__()

  def getExtraArgs(self):

    extra_args = {
      "keyboard-configuration/xkb-keymap": "us",
      #"console-keymaps-at/keymap": "us",
      "console-keymaps-at/keymap": "American",
      "console-setup/ask_detect": "false",
      "console-setup/layoutcode": "us",
      "keyboard-configuration/layout": "USA",
      "keyboard-configuration/variant": "US",
      "locale": "en_US", #.UTF-8",
      "netcfg/get_domain": self.args.domain_name,
      "netcfg/get_hostname": self.args.host_name,
      "preseed/url": "http://autobahn.jeffreyforman.net/jf-custom-debian.preseed"
      }

    # Order of console specs is important. tt0, ttyS0
    add_ons = ['serial', 'console=tty0', 'console=ttyS0,9600n8']

    # NOTE: This needs to be reimplemented.
    # if self.args.ip_address:
    #   network_info = NETWORK_CONFIG[self.args.bridge_interface]
    #   if not self.args.ip_address.startswith(network_info['network']):
    #     logging.error("You assigned an IP address (%s) that does not match the requested interface (%s).", args.ip_address,
    #                   self.args.bridge_interface)
    #   raise vmbuilder.HandledException
    #
    #   extra_args += (" " +
    #                "netcfg/get_nameservers=" + network_info['nameserver'] + " " +
    #                "netcfg/get_ipaddress=" + self.args.ip_address + " " +
    #                "netcfg/get_netmask=" + self.network_info['netmask'] + " " +
    #                "netcfg/get_gateway=" + self.network_info['gateway'] + " " +
    #                "netcfg/confirm_static=true " +
    #                "netcfg/disable_autoconfig=true")
    #
    # custom_flags += "\""

    result = []
    for key,value in extra_args.iteritems():
      result.append("%s=%s" % (key, value))
    result = " ".join(result)

    for current in add_ons:
      result += " %s" % current

    result = "\"%s\"" % result

    return result
