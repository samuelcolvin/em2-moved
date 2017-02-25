# docker image to run the em2 api server only
# image must be build from the repo root directory, eg. with "docker build . -t em2 -f docker/Dockerfile"
FROM python:3.6-alpine

LABEL maintainer "s@muelcolvin.com"

RUN apk --update --no-cache add postgresql-dev gcc g++ musl-dev libuv make \
 && rm -rf /var/cache/apk/*

ADD ./docker/requirements.txt /home/root/
RUN pip install -r /home/root/requirements.txt

ADD ./em2 /home/root/src/em2
ADD ./setup.py /home/root/src/
RUN pip install /home/root/src/

ADD ./docker/run.py /home/root/
ADD ./docker/check.py /home/root/

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=2 CMD /home/root/check.py
ENTRYPOINT ["/home/root/run.py"]
