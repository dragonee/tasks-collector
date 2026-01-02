from django.urls import include, path

from rest_framework import routers

from . import views

router = routers.DefaultRouter()
router.register(r"claim", views.ClaimViewSet)
router.register(r"claimed", views.ClaimedViewSet, basename="claimed")

urlpatterns = [
    path("<int:id>/", views.claim_view, name="claim"),
    path("", include(router.urls)),
]
