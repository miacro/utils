#!/bin/sh
function usage (){
  echo "usage: dump-mongodb.sh [options] directory"
  echo "  directory: the mongodb backup directory"
  echo "  options:"
  echo "    -p --port mongodb port"
  echo "    -h --host mongodb host"
  echo "       --oplog default=true"
  echo "       --help usage"
  exit
}
GETOPT_ARGS=`getopt -o p:h: -l port:,host:,oplog:,help -- "$@"`
eval set -- ${GETOPT_ARGS}

connect_args="";
backup_root="";
dump_args="";
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
    --) shift 1; backup_root=${1}; shift; continue;;
    --help|*) usage;;
  esac
done

if [[ ! -n ${connect_args} ]]
then
  usage
else
  echo "mongodb server: ${connect_args}"
fi

if [[ ! -n ${backup_root} ]]
then 
  backup_root=`pwd`
fi

if [[ ${oplog} == true ]] 
then
  dump_args="${dump_args} --oplog"
fi

echo "backup mongodb to directory: ${backup_root}"

cd ${backup_root}
backup_dir=backup-$(date +%Y-%m-%dT%H-%M-%S)
backup_archive=${backup_dir}.tar.gz
mongodump ${dump_args} ${connect_args} -o ${backup_dir}

echo "creating archive: ${backup_archive}"
tar -pcvzf ${backup_archive} ${backup_dir}
echo "removing ${backup_dir}"
rm -rf ${backup_dir}
