#!/bin/sh
function usage (){
  echo "usage: dump-mongodb.sh [options] directory"
  echo "  directory: the mongodb backup directory, it may delete some files in the directory"
  echo "  options:"
  echo "    -p --port mongodb port"
  echo "    -h --host mongodb host"
  echo "       --remove-config remove the config database"
  echo "       --remove-profile remove profile collections"
  echo "       --oplog oplog replay, default=true"
  echo "       --help usage"
  exit
}
GETOPT_ARGS=`getopt -o p:h: -l port:,host:,oplog:,help,remove-config,remove-profile -- "$@"`
eval set -- ${GETOPT_ARGS}

connect_args="";
backup_dir="";
remove_config=false;
remove_profile=false;
restore_args="--noIndexRestore --drop";
oplog=true;

while [ ${1} ]
do
  case ${1} in
    -p|--port) connect_args="${connect_args} --port ${2}";
      shift 2; continue;;
    -h|--host) connect_args="${connect_args} --host ${2}"; 
      shift 2; continue;;
    --oplog) oplog=${2}; 
      shift 2; continue;;
    --remove-config) remove_config=true; shift 1; continue;;
    --remove-profile) remove_profile=true; shift 1; continue;;
    --) shift 1; backup_dir=${1}; shift 1; continue;;
    --help|*) usage;;
  esac
done

if [[ ! -n ${backup_dir} ]]
then 
  usage
fi

if [[ ! -n ${connect_args} ]]
then
  usage
else
  echo "mongodb server: ${connect_args}"
fi

if [[ ${oplog} == true ]]
then
  restore_args="${restore_args} --oplogReplay"
fi

if [[ ${remove_config} == true ]]
then
  echo "remove config database"
  cd ${backup_dir}
  rm -rf ./config
  cd -
fi

if [[ ${remove_profile} == true ]]
then
  cd ${backup_dir}
  echo "remove system.profile from all database"
  find -name "system.profile.bson" -exec echo {} \;
  find -name "system.profile.bson" -delete
  find -name "system.profile.metadata.json" -exec echo {} \;
  find -name "system.profile.metadata.json" -delete
  cd -
fi

mongorestore ${restore_args} ${connect_args} ${backup_dir}
