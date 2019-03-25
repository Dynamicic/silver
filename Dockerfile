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

WORKDIR /code

RUN set -ex \
    && apk update \
    && apk add --no-cache \
        build-base \
        ca-certificates \
        jpeg \
        jpeg-dev \
        libffi-dev \
        libjpeg-turbo \
        libxslt-dev \
        linux-headers \
        mariadb-client \
        mariadb-dev \
        musl-dev \
        uwsgi \
        uwsgi-python3 \
        wget \
        zlib \
        zlib-dev \
    && update-ca-certificates \
    || apk del .build-deps \
    && wget -qO- https://github.com/jwilder/dockerize/releases/download/v0.2.0/dockerize-linux-amd64-v0.2.0.tar.gz | tar -zxf - -C /usr/bin \
    && chown root:root /usr/bin/dockerize

# Set up this structure:
COPY . /code/src
RUN ln -s /code/src/silver /code/silver
RUN ln -s /code/src/silver-authorize /code/silver_authorizenet
RUN ln -s /code/src/infra/antikythera /code/antikythera
RUN ln -s /code/src/infra/antikythera/wsgi.ini /srv/silver/wsgi.ini
# COPY ./silver /code/silver
# COPY ./silver-authorize /code/silver_authorizenet
# COPY ./infra/antikythera /code/antikythera
# COPY ./infra/antikythera/wsgi.ini /srv/silver
COPY ./docker-scripts /code/docker-scripts

RUN cd /code \
    && pip install --upgrade pip --no-cache-dir

# --editable silversdk
RUN cd /code \
    && pip install --editable silver_authorizenet \
                   --editable silver \
                   --editable antikythera \
                   --no-cache-dir

RUN rm -rf /code/src

# CMD ["/docker-entrypoint"]
CMD ["uwsgi wsgi.ini"]
