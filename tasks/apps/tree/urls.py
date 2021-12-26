from django.urls import include, path
from django.views.generic import TemplateView

from rest_framework import routers
from . import views

router = routers.DefaultRouter()
router.register(r'boards', views.BoardViewSet, basename='boards')
router.register(r'threads', views.ThreadViewSet)
router.register(r'plans', views.PlanViewSet)
router.register(r'reflections', views.ReflectionViewSet)
router.register(r'observation-api', views.ObservationViewSet)


urlpatterns = [
    path('boards/<int:id>/summary/', views.board_summary),
    path('summaries/', views.summaries),

    path('boards/<int:id>/commit/', views.commit_board),
    path('periodical/', views.periodical),
    path('observations/', views.ObservationListView.as_view(), name='observation-list'),
    path('observations/closed/', views.ObservationClosedListView.as_view(), name='observation-list-closed'),

    path('', views.today),
    path('', include(router.urls)),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework'))
]
