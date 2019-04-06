#!/bin/sh
badblocks -svn -b 512 -c 65536 -o badsectors.txt $1
e2fsck -cfpv /dev/sdb4
hdparm --read-sector 2683286643 /dev/sdb
