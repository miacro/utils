#!/bin/sh
x=0;
for((i=1;$i<=$1;i=i+1));
do
	let x=x*10+8;
	echo "$x $x"; 
done
	
