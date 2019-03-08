from python:3.7.2-alpine3.8
MAINTAINER ryan

# Ensure that Python outputs everything that's printed inside
# the application rather than buffering it, maily for logging purposes
ENV PYTHONUNBUFFERED 1

# Set default django settings module
ENV DJANGO_SETTINGS_MODULE silverintegration.settings

# silver app runs on port 8080
EXPOSE 8080

RUN set -ex && mkdir -p /silver
RUN set -ex && mkdir -p /srv/silver

WORKDIR /app

# Install silver
COPY ./app/dev_dot_com/requirements-docker.txt /app/requirements.txt
COPY ./app/dev_dot_com/xhtml2pdf.zip /app/xhtml2pdf.zip

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
        uwsgi-python3 \
        musl-dev \
        linux-headers \
        build-base \
    && apk add --no-cache --virtual .build-deps \
        mariadb-dev \
    && update-ca-certificates \
    && apk del .build-deps \

RUN set -ex \
    && wget -qO- https://github.com/jwilder/dockerize/releases/download/v0.2.0/dockerize-linux-amd64-v0.2.0.tar.gz | tar -zxf - -C /usr/bin \
    && chown root:root /usr/bin/dockerize

COPY ./app/dev_dot_com/requirements-docker.txt /app
COPY ./silver-authorize /code/silver_authorizenet
COPY ./silver /code/silver

# Install more deps
RUN cd /code/silver_authorizenet \
    && pip install --no-cache-dir -e .

RUN cd /app \
    && pip install --no-cache-dir xhtml2pdf.zip

RUN cd /code/silver/infra/antikythera \
    && python setup.py develop

COPY ./app/antikythera/wsgi.ini /srv/silver

VOLUME /srv/silver

# CMD ["/docker-entrypoint"]
CMD ["uwsgi wsgi.ini"]
