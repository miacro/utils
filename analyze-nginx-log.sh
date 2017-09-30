#!/bin/sh
function usage() {
  echo "usage: analyze-nginx-log.sh [options] directory"
  echo "  options:"
  echo "    -h --help usage"
  echo "    directory default ./nginx-log"
  exit
}
GETOPT_ARGS=`getopt -o o:h -l output:,help -- "$@"`
eval set -- ${GETOPT_ARGS}

log_dir=./nginx-log
output=$(pwd)
while [ ${1} ]
do
  case ${1} in
    -o|--output) output="${2}";
      shift 2; continue;;
    --) shift 1; log_dir=${1}; shift; continue;;
    -h|--help|*) usage;;
  esac
done

output=$(realpath ${output})
[[ -f ${output} ]] && rm ${output}
function analyze_log() {
  echo ${filename}
  tempdir=/tmp/analyze-nginx-log/
  mkdir -p ${tempdir}
  tempfile=${tempdir}/$(echo "${filename}" | sha256sum | awk -F " " '{print $1}')
  if [[ $(file ${filename} | grep "gzip") ]]
  then
    gunzip -c ${filename} > ${tempfile} 
  else
      cp ${filename} ${tempfile}
  fi
  awk -F "]" '{print $1"]"}' ${tempfile} \
  | awk -F " - - " '{print $1"  "$2}' >> ${output}
  rm ${tempfile}
}

filenames=$(ls ${log_dir})
cd ${log_dir}
for filename in ${filenames}
do
  analyze_log ${filename}
done

awk -F "  " '!a[$1]++ {print}' ${output} > ${output}.unique
