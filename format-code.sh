#!/bin/sh
function usage (){
  echo "usage: format-code.sh [options] <file or directory>"
  echo "  options:"
  echo "    -l --language default: cpp  cpp, javascript, java"
  echo "       --regex regex filter"
  echo "       --help usage"
  exit
}
GETOPT_ARGS=`getopt -o l:h: -l language:,regex:,help -- "$@"`
eval set -- ${GETOPT_ARGS}

REGEX=""
LANGUAGE=""
TARGET=""

while [ ${1} ]
do
  case ${1} in
    -l|--language) LANGUAGE=${2}; shift 2; continue;;
    --regex) REGEX=${2}; shift 2; continue;;
    --) shift 1;;
    -h|--help) usage;;
    *) TARGET="${TARGET} ${1}"; shift; continue;;
  esac
done

if [[ ! -n ${LANGUAGE} ]]
then
  LANGUAGE=cpp
fi

if [[ ! -n ${REGEX} ]]
then
  if [[ ${LANGUAGE} == cpp ]]
  then
    REGEX=".*\(\(\.c\)\|\(\.cpp\)\|\(\.h\)\|\(\.hpp\)\)"
  elif [[ ${LANGUAGE} == javascript ]]
  then
    REGEX=".*\(\(\.js\)\)"
  else
    usage
  fi
fi

TARGET_FILES=""
for VAR in ${TARGET}
do
  [[ -f ${VAR} ]] && TARGET_FILES="${TARGET_FILES} ${VAR}"
  [[ -d ${VAR} ]] && TARGET_FILES="${TARGET_FILES} `find ${VAR} -regex ${REGEX}`"
done

TMP_DIR=/tmp/clang-format
[[ ! -d ${TMP_DIR} ]] && mkdir -p ${TMP_DIR}

for FILE in ${TARGET_FILES}
do
  TMP_FILE=${TMP_DIR}/clang-format-files.$$
  clang-format -style=file ${FILE} > ${TMP_FILE}

  if [[ ${?} == 0 ]]
  then
    [[ ! `cmp ${FILE} ${TMP_FILE}` == ""  ]] \
      && echo "formatting ${FILE}" \
      && cat ${TMP_FILE} > ${FILE} 
  else
    echo "error when formatting ${FILE}"
  fi
done
rm -rf ${TMP_DIR}
