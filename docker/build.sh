#!/usr/bin/env bash

set -e

KEY_FILE=${1:-em2-private.pem}
if [ ! -f ${KEY_FILE} ]; then
  echo "Error: files '$KEY_FILE' does not exist"
  exit 2
fi

# copy the file before changing directory so $KEY_FILE is still correct
THIS_DIR=`dirname "$0"`
cp ${KEY_FILE} ${THIS_DIR}/private.pem

cd ${THIS_DIR}
if [[ ! -d tmp ]]; then
    echo "creating tmp directory..."
    mkdir tmp
else
    echo "tmp directory already exists"
fi

echo "copying necessary files into place..."
rsync -i -a requirements.txt tmp/docker-requirements.txt
rsync -i -a --delete --exclude=*.pyc --exclude=__pycache__ ../em2 tmp/
rsync -i -a ../setup.py tmp/
rsync -i -a Dockerfile tmp/
mv private.pem tmp/

echo "building docker image..."
docker build tmp -t em2 --build-arg EM2_COMMIT=`git rev-parse --short HEAD`
echo "done."

# creating the network here saves lots of time when working with compose
echo "checking network exists..."
status=0
docker network inspect em2 >/dev/null 2>&1 || status=1
if [ $status -eq 0 ]; then
    echo 'docker network "em2" already exists'
else
    echo 'docker network "em2" network...'
    docker network create --driver=bridge --subnet=172.20.0.0/16 em2
fi
