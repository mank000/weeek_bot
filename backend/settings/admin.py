from django.contrib import admin
from django.contrib.auth.models import Group, User

from .models import Settings, TaskMoveLog

admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(Settings)
class SettingsAdmin(admin.ModelAdmin):
    list_display = ("id", "api_key", "week_key")
    search_fields = ("api_key", "week_key")


@admin.register(TaskMoveLog)
class TaskMoveLogAdmin(admin.ModelAdmin):
    list_display = (
        "task_id",
        "task_title",
        "from_column",
        "to_column",
        "user_name",
        "move_time",
        "time_spent",
        "board_name",
    )
    search_fields = ("task_id", "task_title", "user_name", "board_name")
    list_filter = (
        "from_column",
        "to_column",
        "user_name",
        "board_name",
        "move_time",
    )
    ordering = ("-move_time",)
