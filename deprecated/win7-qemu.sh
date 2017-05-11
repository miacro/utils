#!/bin/sh
cdrom="-cdrom /home/miacro/warehouse/virtual-machine/cn_windows_7_ultimate_with_sp1_x64_dvd_u_677408.iso"
boot="-boot d"
##vncserver
vnc="-vnc 192.168.1.248:1"
##monitor
serial="-serial vc"
monitor="-monitor stdio"

cpu="-cpu host -enable-kvm -smp cpus=4"
mem="-m 4G"
#display="-nographic"
display="-vga std"

# Glaxy Note4: Bus 003 Device 012: ID 04e8:6860
#usb1="-usbdevice host:04e8:6860"
#usb2="-usbdevice host:0bc2:3320"
#usb1="-usbdevice host:3.12"
#usb1="-device usb-host,hostbus=3,hostaddr=5"
usb="-usb -usbdevice tablet ${usb1} ${usb2}"
#sound="-soundhw hda"

disk_img="/home/miacro/warehouse/virtual-machine/qemu-win7_x64_C.img"
disk_img2="/home/miacro/warehouse/virtual-machine/qemu-win7_x64_D.img"
#hda="-hda ${disk_img}"
hda="-drive index=0,media=disk,format=raw,file=${disk_img}"
hdb="-drive index=1,media=disk,format=raw,file=${disk_img2}"
net="-net bridge,br=br0 -net nic,macaddr=52:0d:05:43:34:35"

#vm="${cpu} ${mem} ${cdrom} ${boot} ${hda} ${net} ${vnc} ${display} ${serial}"
vm="${cpu} ${mem} ${hda} ${hdb} ${net} ${display} ${vnc} ${usb} ${sound}"
exec qemu-system-x86_64 ${vm}
