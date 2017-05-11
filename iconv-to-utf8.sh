#~/bin/sh
function usage()
{
  echo "-f  file"
  echo "-d  directory"
  exit
}

function process_single_file()
{
  file=${1}
  echo "iconv ${file}"
  iconv -f GBK -t UTF-8  ${file} -o ${file}
}

if [[ ${#} < 1 ]]
then
  echo "Please specify the file or directory."
  usage
fi

if [[ ${1} == "-h" ]]
then
  usage
fi

if [[ ${1} == "-f" ]]
then
  process_single_file ${2}
fi

if [[ ${1} == "-d" ]]
then
  file_list=`find ${2} -type f`
  for file in ${file_list}
  do
    is_utf8=`file ${file} | grep "UTF-8" | wc -l`
    is_ascii=`file ${file} | grep "ASCII" | wc -l`
    if [[  ${is_utf8} < 1 && ${is_ascii} < 1 ]]
    then
      process_single_file ${file}
    fi
  done
fi
