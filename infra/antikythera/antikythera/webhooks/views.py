from django.shortcuts import render
from rest_framework import viewsets

# from rest_hooks.models import Hook
# from rest_hooks.serializers import HookSerializer



# class HookViewSet(viewsets.ModelViewSet):
#     """
#     Retrieve, create, update or destroy webhooks.
#     """
#     model = Hook
#     serializer_class = HookSerializer

#     def pre_save(self, obj):
#         super(HookViewSet, self).pre_save(obj)
#         obj.user = self.request.user
