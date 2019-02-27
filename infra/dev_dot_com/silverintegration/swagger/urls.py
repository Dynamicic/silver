from django.conf.urls import url, include

from rest_framework import routers
from rest_framework_swagger.views import get_swagger_view

from . import views
from .views import SwaggerSchemaView

schema_view = get_swagger_view(title='Silver API')

urlpatterns = [
    url(r'^schema/$', SwaggerSchemaView.as_view()),
    url(r'^$', schema_view)
]
