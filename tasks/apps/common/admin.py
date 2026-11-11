from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import ApiToken, User

admin.site.register(User, UserAdmin)


@admin.register(ApiToken)
class ApiTokenAdmin(admin.ModelAdmin):
    """Who is logged in from where; deleting a token revokes it. One is
    issued by logging a device in, or by ``manage.py issue_mobile_token``."""

    list_display = ("name", "user", "read_only", "created", "last_used")
    list_select_related = ("user",)
    readonly_fields = ("user", "read_only", "created", "last_used")

    def has_add_permission(self, request):
        return False
