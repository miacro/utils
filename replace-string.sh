#!/bin/sh
function replace()
{
  tmp_file=/tmp/replace_string.$$
  sed "s/${2}/${3}/g" ${1} > ${tmp_file}
  if [[ ! `cmp ${1} ${tmp_file}` == "" ]]
  then
    echo "processing file ${1}"
    cat ${tmp_file} > ${1}
  fi
  rm ${tmp_file}
}

function usage()
{
  echo "usage: program [option] [pattern before] [pattern after] \
    [dir or file name] "  
  echo ""
  echo "        option: -h for help"
  echo "                -r recursion"
  echo "                -n not recursion"
}

file_list=""

if [[ ${1} == "-h" ]]
then
  usage
fi

if [[ $# !=  4 ]]
then
  usage
fi

if [[ -f ${4} ]]
then
  file_list=${4}
fi

if [[ -d ${4} ]]
then
  if [[ ${1} == "-n" ]]
  then
    file_list=`find ${4} -maxdepth 1`
  fi
  if [[ ${1} == "-r" ]]
  then
    file_list=`find ${4}`
  fi
fi

for i in ${file_list}
do
  if [[ -f ${i} ]]
  then
    replace ${i} ${2} ${3}
  fi
done
