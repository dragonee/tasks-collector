from django.urls import include, path

from rest_framework import routers
from . import views

router = routers.DefaultRouter()
router.register(r'entries', views.QuestViewSet)
router.register(r'journal', views.QuestJournalViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
