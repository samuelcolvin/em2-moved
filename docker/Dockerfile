# docker image to run the em2 api server only
# image must be built using build.sh
FROM python:3.6-alpine

LABEL maintainer "s@muelcolvin.com"

RUN apk --update --no-cache add postgresql-dev gcc g++ musl-dev libuv make libffi-dev \
 && rm -rf /var/cache/apk/*

ADD ./docker-requirements.txt /home/root/
RUN pip install -r /home/root/docker-requirements.txt

# install these before em2-requirements.txt just makes builds faster
RUN pip install uvloop asyncpg cryptography

# the next two lines are just to make repeat builds quicker, they are completely duplicated by "pip install ..." below
ADD ./em2/extras/requirements.txt /home/root/em2-requirements.txt
RUN pip install -r /home/root/em2-requirements.txt

ADD ./em2 /home/root/src/em2
ADD ./setup.py /home/root/src/
RUN pip install -e /home/root/src/
ARG EM2_COMMIT
ENV EM2_COMMIT ${EM2_COMMIT}

WORKDIR /home/root
HEALTHCHECK --interval=20s --timeout=10s --retries=2 CMD em2check
CMD ["em2run"]
