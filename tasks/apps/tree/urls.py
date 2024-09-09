from django.urls import include, path, re_path
from django.views.generic import TemplateView


from rest_framework import routers
from . import views

from django.urls import include, path

router = routers.DefaultRouter()
router.register(r'boards', views.BoardViewSet, basename='boards')
router.register(r'threads', views.ThreadViewSet)
router.register(r'plans', views.PlanViewSet)
router.register(r'reflections', views.ReflectionViewSet)
router.register(r'observation-api', views.ObservationViewSet)
router.register(r'updates', views.ObservationUpdatedViewSet)
router.register(r'journal', views.JournalAddedViewSet)
router.register(r'quick-notes', views.QuickNoteViewSet)
router.register(r'observation-events', views.ObservationEventViewSet)


urlpatterns = [
    path('boards/<int:id>/summary/', views.board_summary),
    path('summaries/', views.summaries),

    path('boards/<int:id>/commit/', views.commit_board),
    path('boards/append/', views.add_task),
    path('periodical/', views.periodical),
    path('observations/add/', views.observation_edit, name='public-observation-add'),
    re_path(r'^observations/(?P<observation_id>[a-f0-9\-]+)/$', views.observation_edit, name='public-observation-edit'),
    path('observations/', views.ObservationListView.as_view(), name='public-observation-list'),
    path('observations/closed/', views.ObservationClosedListView.as_view(), name='public-observation-list-closed'),
    re_path(r'^observations/closed/(?P<event_stream_id>[a-f0-9\-]+)/$', views.observation_closed_detail, name='public-observation-closed-detail'),

    re_path(r'^observations/(?P<observation_id>[a-f0-9\-]+)/close/$', views.observation_close, name='public-observation-close'),

    path('', views.today),
    path('', include(router.urls)),
    path('todo/', TemplateView.as_view(template_name='tree/tasks.html')),
    path('q/', views.quick_notes, name='quick-notes'),
    path('q/post/', views.add_quick_note_hx, name='quick-note-add'),

    path('api-auth/', include('rest_framework.urls', namespace='rest_framework'))
]
