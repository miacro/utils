#!/bin/sh
make menuconfig
make
make install
make modules_prepare
make modules_install
genkernel --install initramfs 
grub-mkconfig -o /boot/efi/grub/grub.cfg
emerge -av @module-rebuild
