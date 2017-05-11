SOURCE_DIR=`pwd`
TARGET_DIR=${HOME}/bin/utils
MAKE=make --no-print-directory
SHELL=/bin/bash

reinstall:
	@  ${MAKE} uninstall \
	&& ${MAKE} install

install: prepare_target
	@  [[ ! -L ${TARGET_DIR} ]] && [[ ! -f ${TARGET_DIR} ]] \
	&& ln -s ${SOURCE_DIR} ${TARGET_DIR} \
	||  exit 0

uninstall:
	@  [[ -L ${TARGET_DIR} ]] \
	&& rm ${TARGET_DIR} \
	|| exit 0

prepare_target:
	@ mkdir -p ${HOME}/bin

.PHONY: reinstall uninstall install 
