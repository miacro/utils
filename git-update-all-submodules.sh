#!/bin/sh
git submodule foreach "git fetch && git checkout master && git merge origin/master"
