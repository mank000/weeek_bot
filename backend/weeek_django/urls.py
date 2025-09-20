from django.contrib import admin
from django.urls import include, path

from .views import LogMoveView, get_bot_token

app_label = "week"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/bot-token/", get_bot_token, name="get-bot-token"),
    path("log_move/", LogMoveView.as_view(), name="log_move"),
]
