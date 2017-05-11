#!/bin/sh
#pulseaudio device (pactl list sources)
#  Name: alsa_output.pci-0000_01_00.1.hdmi-stereo.monitor
#  Name: alsa_output.pci-0000_00_1b.0.analog-stereo.monitor # internal
#  Name: alsa_input.pci-0000_00_1b.0.analog-stereo  # outside
exec ffmpeg -f x11grab -s 1366x768  -i $DISPLAY  -f pulse -i default -r 25 test.mkv
