#!/bin/sh
for((i=1;$i<=$1;i=i+1));
do
	for((j=1;$j<=$i;j=j+1))
	do
		echo -n "8";
	done
	echo -n " ";
	for((j=1;$j<=$i;j=j+1))
	do
		echo -n "8";
	done
	echo "";
done
