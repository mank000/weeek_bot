from django.contrib.auth.models import User
from django.db import models


class Settings(models.Model):
    api_key = models.CharField("TgBotApiKey", max_length=512, null=True)
    week_key = models.CharField("WeekApiKey", max_length=512, null=True)

    class Meta:
        verbose_name = "Настройки"
        verbose_name_plural = "Настройки"


class TaskMoveLog(models.Model):
    task_title = models.CharField(max_length=255)
    task_id = models.CharField(max_length=100)
    from_column = models.CharField(max_length=255)
    to_column = models.CharField(max_length=255)
    user_name = models.CharField(max_length=255)
    move_time = models.DateTimeField()
    time_spent = models.FloatField()
    board_name = models.CharField()

    def __str__(self):
        return f"Move of task {self.task_id} from {self.from_column} to {self.to_column}"
