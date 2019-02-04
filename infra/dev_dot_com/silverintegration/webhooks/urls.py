from rest_framework import routers

from . import views

router = routers.SimpleRouter(trailing_slash=False)
router.register(r'webhooks', views.HookViewSet, 'webhook')

