from django.urls import include, path
from rest_framework.routers import DefaultRouter

from users.views import UserViewSet

from .views import IngredientViewSet, RecipeViewSet, TagViewSet


router = DefaultRouter()
router.register('recipes', RecipeViewSet, basename='recipes')
router.register('users', UserViewSet, basename='users')
router.register('tags', TagViewSet, basename='tags')
router.register('ingredients', IngredientViewSet, basename='ingredients')


urlpatterns = [
    path('', include(router.urls)),
    path('auth/', include('djoser.urls')),
    path('auth/', include('djoser.urls.authtoken')),
    path(
        'cart/',
        RecipeViewSet.as_view({'get': 'shopping_cart_list'}),
        name='cart'
    ),
    path(
        'cart/count/',
        RecipeViewSet.as_view({'get': 'shopping_cart_count'}),
        name='cart-count'
    ),
    path(
        'subscriptions/',
        UserViewSet.as_view({'get': 'subscriptions'}),
        name='subscriptions'
    )
]
