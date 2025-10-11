from django.urls import include, path, re_path
from django.views.generic import TemplateView


from rest_framework import routers
from . import views
from . import views_today

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
router.register(r'habit-api', views.HabitViewSet)
router.register(r'profile', views.ProfileViewSet, basename='profile')

urlpatterns = [
    path('boards/<int:id>/summary/', views.board_summary),
    path('summaries/', views.summaries),

    path('boards/<int:id>/commit/', views.commit_board),
    path('boards/append/', views.add_task),
    path('plans/add-task/', views.add_task_to_plan, name='plan-add-task'),
    path('observations/add/', views.observation_edit, name='public-observation-add'),
    re_path(r'^observations/(?P<observation_id>[a-f0-9\-]+)/$', views.observation_edit, name='public-observation-edit'),
    path('observations/', views.ObservationMineListView.as_view(), name='public-observation-list'),
    path('observations/all/', views.ObservationListView.as_view(), name='public-observation-list-all'),
    path('observations/closed/', views.ObservationClosedListView.as_view(), name='public-observation-list-closed'),
    path('lessons/', views.LessonsListView.as_view(), name='public-lessons-list'),
    path('observations/<int:observation_id>/journalize/', views.migrate_observation_updates_to_journal, name='public-observation-journalize'),
    path('diary/<int:year>/<int:month>/', views.JournalArchiveMonthView.as_view(month_format="%m"), name='public-diary-archive-month'),
    path('diary/', views.JournalCurrentMonthArchiveView.as_view(month_format="%m"), name='public-diary-archive-current-month'),
    path('diary/<slug:slug>/', views.JournalTagCurrentMonthArchiveView.as_view(month_format="%m"), name='public-diary-archive-current-month-tag'),
    path('diary/<slug:slug>/<int:year>/<int:month>/', views.JournalTagArchiveMonthView.as_view(month_format="%m"), name='public-diary-archive-month-tag'),
    path('events/', views.EventCurrentMonthArchiveView.as_view(month_format="%m"), name='public-event-archive-current-month'),
    path('events/<int:year>/<int:month>/', views.EventArchiveMonthView.as_view(month_format="%m"), name='public-event-archive-month'),
    path('habits/<slug:slug>/', views.HabitDetailView.as_view(), name='public-habit-detail'),
    path('habit/track/', views.track_habit, name='public-habit-track'),
    path('habits/', views.HabitListView.as_view(), name='public-habit-list'),
    re_path(r'^observations/closed/(?P<event_stream_id>[a-f0-9\-]+)/$', views.observation_closed_detail, name='public-observation-closed-detail'),

    re_path(r'^observations/(?P<observation_id>[a-f0-9\-]+)/close/$', views.observation_close, name='public-observation-close'),
    re_path(r'^observations/(?P<observation_id>[a-f0-9\-]+)/attach/$', views.observation_attach, name='public-observation-attach'),
    re_path(r'^observations/(?P<observation_id>[a-f0-9\-]+)/detach/$', views.observation_detach, name='public-observation-detach'),
    re_path(r'^observations/(?P<observation_id>[a-f0-9\-]+)/attachments/$', views.observation_attachments, name='public-observation-attachments'),
    path('observations/search/', views.observation_search, name='public-observation-search'),

    path('', views_today.today, name='public-today'),
    path('', include(router.urls)),
    path('todo/', views.todo, name='todo'),
    path('q/', views.quick_notes, name='quick-notes'),
    path('q/post/', views.add_quick_note_hx, name='quick-note-add'),

    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('breakthrough/<int:year>/', views.breakthrough, name='breakthrough'),
    re_path(r'^projected-outcome/(?P<event_stream_id>[a-f0-9\-]+)/events/$', views.projected_outcome_events_history, name='projected-outcome-events-history'),
    path('stats/', views.stats, name='stats'),
    path('api/events/daily/', views.daily_events, name='daily-events'),
    path('accounts/settings/', views.account_settings, name='account-settings'),
]
