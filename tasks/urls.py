from django.conf import settings
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, re_path, reverse_lazy
from django.views.generic import RedirectView

from tasks.apps.common import oauth
from tasks.apps.common.views import health_check

urlpatterns = [
    path("health/", health_check, name="health_check"),
    re_path(r"^admin/", admin.site.urls),
    # Authentication URLs
    path(
        "accounts/login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path(
        "accounts/logout/", auth_views.LogoutView.as_view(next_page="/"), name="logout"
    ),
    # Logging a device in, and out again (apps/common/oauth.py)
    path("oauth/authorize/", oauth.authorize, name="oauth-authorize"),
    path("oauth/token/", oauth.token, name="oauth-token"),
    path("oauth/revoke/", oauth.revoke, name="oauth-revoke"),
    path(
        "accounts/tokens/<int:pk>/revoke/",
        oauth.revoke_token,
        name="api-token-revoke",
    ),
    re_path(r"^", include("tasks.apps.tree.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
