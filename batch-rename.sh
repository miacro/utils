#!/bin/sh
if [ $# != 2 ]
then
  echo "Usage: batch_rename.sh path prefixion"
else
  echo $#
  for i in `ls $1` 
  do
    mv ${1}/${i} ${1}/${2}${i}
  done
fi
