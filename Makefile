SRC=$(realpath .)
DST=${HOME}/bin/utils
MAKE=make --no-print-directory
SHELL=/bin/bash

reinstall:
	mkdir -p `dirname ${DST}` \
	&& ln -fs -T ${SRC} ${DST}

uninstall:
	[[ -L ${DST} ]] && rm ${DST} || exit 0

.PHONY: reinstall uninstall
