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

# using /home/root/smtp_html_template.html should make overriding this file easier
rsync -i -a  ../em2/extras/smtp_html_template.html tmp/smtp_html_template.html

echo "building docker image..."
docker build tmp -t em2 --build-arg EM2_COMMIT=`git rev-parse --short HEAD`
echo "done."
