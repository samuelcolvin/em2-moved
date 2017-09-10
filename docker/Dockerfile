# docker image to run the em2 api server only
# image must be built using build.sh
FROM python:3.6-alpine

LABEL maintainer "s@muelcolvin.com"

RUN apk --update --no-cache add postgresql-dev gcc g++ musl-dev libuv make libffi-dev \
 && rm -rf /var/cache/apk/*

RUN pip install -U pip setuptools
ADD ./docker-requirements.txt /home/root/
RUN pip install -r /home/root/docker-requirements.txt

ADD ./em2/extras/requirements1.txt /home/root/em2-requirements1.txt
RUN pip install -r /home/root/em2-requirements1.txt
ADD ./em2/extras/requirements2.txt /home/root/em2-requirements2.txt
RUN pip install -r /home/root/em2-requirements2.txt

ADD ./em2 /home/root/src/em2
ADD ./setup.py /home/root/src/
RUN pip install -e /home/root/src/
ARG EM2_COMMIT
ENV EM2_COMMIT ${EM2_COMMIT}

ADD ./private.pem /home/root/
ENV EM2_PRIVATE_DOMAIN_KEY_FILE /home/root/private.pem

ADD ./smtp_html_template.html /home/root/
ENV EM2_SMTP_HTML_TEMPLATE /home/root/smtp_html_template.html

WORKDIR /home/root
HEALTHCHECK --interval=20s --timeout=10s --retries=2 CMD em2check
ENTRYPOINT ["em2run"]
