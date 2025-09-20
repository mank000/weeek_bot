from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework.decorators import api_view
from rest_framework.response import Response
from settings.models import Settings, TaskMoveLog

from .serializers import SettingsSerializer, TaskMoveLogSerializer


@api_view(["GET"])
def get_bot_token(request):
    setting = get_object_or_404(Settings, id=1)
    serializer = SettingsSerializer(setting)
    return Response(serializer.data)


class LogMoveView(generics.CreateAPIView):
    queryset = TaskMoveLog.objects.all()
    serializer_class = TaskMoveLogSerializer
