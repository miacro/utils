#!/bin/sh
badblocks -svn -b 512 -c 65536 -o badsectors.txt $1
