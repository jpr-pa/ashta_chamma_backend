# game/urls.py
from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import GameViewSet

router = DefaultRouter()
router.register(r'games', GameViewSet, basename='game')

urlpatterns = router.urls

