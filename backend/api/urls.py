from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    RecipeViewSet, TagViewSet, IngredientViewSet, FavoriteViewSet
)
from users.views import UserViewSet

router = DefaultRouter()
router.register('recipes', RecipeViewSet, basename='recipes')
router.register('users', UserViewSet, basename='users')
router.register('tags', TagViewSet, basename='tags')
router.register('ingredients', IngredientViewSet, basename='ingredients')


urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')),
]
