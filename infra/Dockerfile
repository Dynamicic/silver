from python:3.4.9-alpine3.8
MAINTAINER ryan

# Ensure that Python outputs everything that's printed inside
# the application rather than buffering it, maily for logging purposes
ENV PYTHONUNBUFFERED 1

# Set default django settings module
ENV DJANGO_SETTINGS_MODULE silverintegration.settings

# silver app runs on port 8080
EXPOSE 8080

RUN set -ex && mkdir -p /silver
WORKDIR /app

# Install silver
# COPY ./requirements.txt /app/requirements.txt
COPY ./app/dev.billing.dynamicic.com/requirements-docker.txt /app/requirements.txt

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
        cython \
        cython-dev \
        jpeg-dev \
        musl-dev \
        linux-headers \
        build-base \
    && apk add --no-cache --virtual .build-deps \
        mariadb-dev \
    && update-ca-certificates \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps \
    && wget -qO- https://github.com/jwilder/dockerize/releases/download/v0.2.0/dockerize-linux-amd64-v0.2.0.tar.gz | tar -zxf - -C /usr/bin \
    && chown root:root /usr/bin/dockerize

COPY ./app/dev.billing.dynamicic.com/requirements-docker.txt /app
COPY ./silver-authorize /code/silver_authorizenet
COPY ./silver /code/silver

# Install more deps
RUN cd /code/silver_authorizenet \
    && python setup.py develop

VOLUME /app

CMD ["/docker-entrypoint"]
