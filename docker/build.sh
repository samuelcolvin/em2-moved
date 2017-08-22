#!/usr/bin/env bash

set -e

if [ -z ${1+x} ]; then
  echo "Error: please provide the private key file as sole argument"
  exit 2
fi

if [ ! -f $1 ]; then
  echo "Error: files '$1' does not exist"
  exit 2
fi

# copy the file before changing directory so $1 is still correct
THIS_DIR=`dirname "$0"`
cp $1 ${THIS_DIR}/private.pem

cd ${THIS_DIR}
if [[ ! -d tmp ]]; then
    echo "creating tmp directory..."
    mkdir tmp
else
    echo "tmp directory already exists"
fi

echo "copying necessary files into place..."
rsync -i -a requirements.txt tmp/docker-requirements.txt
rsync -i -a --exclude=*.pyc --exclude=__pycache__ ../em2 tmp/
rsync -i -a ../setup.py tmp/
rsync -i -a Dockerfile tmp/
mv private.pem tmp/

echo "building docker image..."
docker build tmp -t em2 --build-arg EM2_COMMIT=`git rev-parse --short HEAD`
echo "done."
