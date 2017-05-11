#!/bin/sh
make menuconfig
make
make install
make module_prepare
make module_install
genkernel --install initramfs 
grub-mkconfig -o /boot/efi/grub/grub.cfg
emerge -av @module-rebuild
