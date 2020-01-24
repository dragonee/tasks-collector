from django.conf.urls import url, include
from django.conf.urls.static import static
from django.urls import path
from django.contrib import admin
from django.conf import settings
from django.urls import reverse_lazy
from django.views.generic import RedirectView


urlpatterns = [
    url(r'^admin/', admin.site.urls),
    url(r'^hello/', include('tasks.apps.hello_world.urls')),
    path('', RedirectView.as_view(url='/hello/world/')),
    url(r'^', include('tasks.apps.tree.urls'))
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)


# Debug Toolbar.
if settings.DEBUG:
    import debug_toolbar
    urlpatterns += [
        url(r'^__debug__/', include(debug_toolbar.urls))
    ]
