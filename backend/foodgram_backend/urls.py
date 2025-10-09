from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from api.views import RecipeViewSet, favorites_page
from users.views import UserViewSet


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('api.urls')),
    path('cart/', RecipeViewSet.as_view({'get': 'shopping_cart_list'}), name='cart'),
    path('cart/count/', RecipeViewSet.as_view({'get': 'shopping_cart_count'}), name='cart-count'),
    path('subscriptions/', UserViewSet.as_view({'get': 'subscriptions'}), name='subscriptions'),
    path('favorites/', favorites_page, name='favorites-page'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL,
                          document_root=settings.MEDIA_ROOT)
