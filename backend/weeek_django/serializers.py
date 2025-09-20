from rest_framework import serializers
from settings.models import Settings, TaskMoveLog


class SettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Settings
        fields = "__all__"


class TaskMoveLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskMoveLog
        fields = "__all__"
