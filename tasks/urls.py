from django.conf.urls import include
from django.conf.urls.static import static
from django.urls import re_path
from django.contrib import admin
from django.conf import settings
from django.urls import reverse_lazy
from django.views.generic import RedirectView


urlpatterns = [
    re_path(r'^admin/', admin.site.urls),
    re_path(r'^rewards/', include('tasks.apps.rewards.urls')),
    re_path(r'^quests/', include('tasks.apps.quests.urls')),
    re_path(r'^', include('tasks.apps.tree.urls'))
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()