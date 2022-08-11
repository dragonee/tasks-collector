from django.urls import include, path

from rest_framework import routers
from . import views

router = routers.DefaultRouter()
router.register(r'entries', views.QuestViewSet)
router.register(r'journal', views.QuestJournalViewSet)

urlpatterns = [
    path('view/<slug:slug>/', views.show_quest, name='show_quest'),
    path('', views.QuestListView.as_view(), name='quest-list'),
    path('view/', views.QuestJournalListView.as_view(), name='questjournal-list'),

    path('', include(router.urls)),
]
