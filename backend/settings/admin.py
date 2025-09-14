from django.contrib import admin
from django.contrib.auth.models import Group, User

from . import models

admin.site.unregister(User)
admin.site.unregister(Group)

admin.site.register(models.Settings),
admin.site.register(models.Priority)
