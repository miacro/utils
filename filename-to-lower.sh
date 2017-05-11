#!/bin/sh
typeset -l var=$1
echo ${var}
mv $1 ${var}
