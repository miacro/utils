#!/bin/sh
find -name "*.epub" | xargs -I FN ebook-convert FN ${FN%%/*}.mobi
