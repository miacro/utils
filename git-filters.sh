#!/bin/sh
git filter-branch --prune-empty -f  --tag-name-filter cat --tree-filter 'find -name "*.vcxproj.user" -delete' HEAD 
