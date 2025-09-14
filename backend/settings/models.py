from django.db import models


def get_default_priority():
    return Priority.objects.get_or_create(name="Средний")[0].id


class Settings(models.Model):
    api_key = models.CharField("API-KEY", max_length=256)
    default_priority = models.ForeignKey(
        "Priority",
        on_delete=models.SET_NULL,
        default=get_default_priority,
        related_name="settings_default",
        verbose_name="Приоритет по-умолчанию",
        null=True,
    )

    class Meta:
        verbose_name = "Настройки"
        verbose_name_plural = "Настройки"


class Priority(models.Model):
    name = models.CharField("Название приоритета", max_length=64, unique=True)
    value = models.IntegerField("ID в API WEEEK", unique=True)

    class Meta:
        verbose_name = "Приоритет"
        verbose_name_plural = "Приоритеты"

    def __str__(self):
        return self.name
