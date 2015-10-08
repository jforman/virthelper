#!/bin/bash

echo "Starting debian-postinstall.sh"
/bin/sed -i '/^PermitRootLogin/c PermitRootLogin yes' /etc/ssh/sshd_config
/bin/sed -i "/^GRUB_CMDLINE_LINUX/c GRUB_CMDLINE_LINUX='console=tty0 console=ttyS0,19200n8'" /etc/default/grub
/usr/sbin/update-grub
echo "Complete with debian-postinstall.sh"
