# em2 docker image for em2

The directory contains files required to serve the basic em2 server with docker.

To build:

    ./docker/build.sh

To run the compose example (with `activate.sh` activated):

    docker-compose up -d

You'll want to then connect to logspout to view the log with something like

    curl -q -s http://localhost:5001/logs
