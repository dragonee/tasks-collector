from django.urls import include, path

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r"elements", views.ElementViewSet)
router.register(r"challenges", views.ChallengeViewSet, basename="challenges")

urlpatterns = [
    path("", views.dashboard, name="enfp-dashboard"),
    path("summary/", views.summary, name="enfp-summary"),
    path("api/", include(router.urls)),
]
