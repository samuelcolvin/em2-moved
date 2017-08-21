# em2 docker image for api-only server

The directory contains files required to serve the basic em2 server with docker.

To build:

    ./build/build.sh

To run the compose example:

    compose -f docker/docker-compose.yml -p em2 up
