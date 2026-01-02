from django.conf import settings
from django.conf.urls import include
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import path, re_path, reverse_lazy
from django.views.generic import RedirectView

urlpatterns = [
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
    re_path(r"^rewards/", include("tasks.apps.rewards.urls")),
    re_path(r"^quests/", include("tasks.apps.quests.urls")),
    re_path(r"^", include("tasks.apps.tree.urls")),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
