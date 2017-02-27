# em2 docker image for api-only server

The directory contains files required to serve the basic em2 server with docker.

To build (from repo root directory):

    docker build . -t em2 -f docker/Dockerfile

To run the compose example:

    compose -f docker/docker-compose.yml -p em2 up
