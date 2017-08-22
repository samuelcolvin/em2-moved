#!/usr/bin/env bash

set -e

cd `dirname "$0"`
if [[ ! -d tmp ]]; then
    echo "creating tmp directory..."
    mkdir tmp
else
    echo "tmp directory already exists"
fi

echo "copying necessary files..."
rsync -i -a requirements.txt tmp/docker-requirements.txt
rsync -i -a --exclude=*.pyc --exclude=__pycache__ ../em2 tmp/
rsync -i -a ../setup.py tmp/
rsync -i -a Dockerfile tmp/

echo "building docker image..."
docker build tmp -t em2 --build-arg EM2_COMMIT=`git rev-parse --short HEAD`
echo "done."
