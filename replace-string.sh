#!/bin/bash
function replace() {
    tmp_file=/tmp/replace_string.$$
    sed "s/${2}/${3}/g" "${1}" > ${tmp_file}
    if [[ ! `cmp "${1}" ${tmp_file}` == "" ]]; then
        echo "processing file \"${1}\""
        cat ${tmp_file} > "${1}"
    fi
    rm ${tmp_file}
}

function usage() {
    echo "usage: program [option] [pattern before] [pattern after] \
      [dir or file name] "
    echo ""
    echo "        option: -h for help"
    echo "                -r recursion"
    echo "                -n not recursion"
    exit
}

if [[ ${1} == "-h" ]]; then
  usage
elif [[ $# !=  4 ]]; then
  usage
fi

find_args=""
if [[ -d ${4} ]]; then
    if [[ ${1} == "-n" ]]; then
        file_args="-maxdepth 1"
    fi
fi

find "${4}" ${find_args} -type f -print0 | while read -d $'\0' file
do
  replace "${file}" ${2} ${3}
done
