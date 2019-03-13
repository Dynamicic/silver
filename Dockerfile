from python:3.7.2-alpine3.8
MAINTAINER ryan

# Ensure that Python outputs everything that's printed inside
# the application rather than buffering it, maily for logging purposes
ENV PYTHONUNBUFFERED 1

# Set default django settings module
# ENV DJANGO_SETTINGS_MODULE silverintegration.settings

# silver app runs on port 8080
EXPOSE 8080

RUN set -ex && mkdir -p /code
RUN set -ex && mkdir -p /srv/silver

WORKDIR /app

# Set up this structure:
COPY ./silver /code/silver
COPY ./silver-authorize /code/silver_authorizenet
COPY ./infra/antikythera /code/antikythera
COPY ./infra/antikythera/wsgi.ini /srv/silver
COPY ./docker-scripts /code/docker-scripts

RUN set -ex \
    && apk update \
    && apk add --no-cache \
        mariadb-client \
        mariadb-dev \
        libjpeg-turbo \
        jpeg \
        zlib \
        ca-certificates wget \
        libffi-dev \
        zlib-dev \
        libxslt-dev \
        jpeg-dev \
        uwsgi \
        py3-lxml \
        uwsgi-python3 \
        musl-dev \
        linux-headers \
        build-base \
    && apk add --no-cache --virtual .build-deps \
        mariadb-dev \
    && update-ca-certificates \
    && apk del .build-deps \
    && wget -qO- https://github.com/jwilder/dockerize/releases/download/v0.2.0/dockerize-linux-amd64-v0.2.0.tar.gz | tar -zxf - -C /usr/bin \
    && chown root:root /usr/bin/dockerize

RUN cd /code/silver_authorizenet \
    && python setup.py develop

RUN cd /code/silver \
    && python setup.py develop

# RUN cd /app \
#     && pip3 install --no-cache-dir /code/docker-scripts/xhtml2pdf.zip

RUN cd /code/antikythera \
    && python3 setup.py develop


COPY ./infra/silversdk /code/silversdk
VOLUME /code/antikythera/

# CMD ["/docker-entrypoint"]
CMD ["uwsgi wsgi.ini"]
