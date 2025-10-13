from django.conf import settings
from django.shortcuts import get_object_or_404
from django.db.models import F, Sum
from django.http import HttpResponse
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets, filters
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .filters import RecipeFilter
from .models import (
    Favorite, Recipe, Ingredient, RecipeIngredient, ShoppingCart, Tag
)
from .permissions import IsAuthorOrReadOnly
from .serializers import (
    IngredientSerializer,
    RecipeCreateSerializer,
    RecipeSerializer,
    ShortRecipeSerializer,
    TagSerializer,
    FavoritesSerializer
)


class RecipePagination(PageNumberPagination):
    page_size = settings.RECIPE_PAGE_SIZE
    page_size_query_param = 'page_size'


class RecipeViewSet(viewsets.ModelViewSet):
    serializer_class = RecipeSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly, IsAuthorOrReadOnly
    ]
    pagination_class = RecipePagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = RecipeFilter

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return RecipeCreateSerializer
        return RecipeSerializer

    def get_queryset(self):
        queryset = Recipe.objects.all()

        queryset = queryset.select_related('author').prefetch_related(
            'tags', 'recipe_ingredients__ingredient'
        )

        # Аннотируем is_favorited и is_in_shopping_cart
        if self.request.user.is_authenticated:
            from django.db.models import Exists, OuterRef

            from .models import Favorite, ShoppingCart

            favorited = Favorite.objects.filter(
                user=self.request.user,
                recipe=OuterRef('pk')
            )
            in_cart = ShoppingCart.objects.filter(
                user=self.request.user,
                recipe=OuterRef('pk')
            )

            queryset = queryset.annotate(
                is_favorited=Exists(favorited),
                is_in_shopping_cart=Exists(in_cart)
            )

        return queryset.distinct()

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[permissions.IsAuthenticated],
        url_path='favorite',
        url_name='favorite'
    )
    def favorite_action(self, request, pk=None):
        """Добавить/удалить рецепт в избранное."""
        recipe = self.get_object()
        user = request.user

        if request.method == 'POST':
            if Favorite.objects.filter(user=user, recipe=recipe).exists():
                return Response(
                    {'error': 'Рецепт уже в избранном'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            serializer = FavoritesSerializer(data={
                'user': user.id,
                'recipe': recipe.id
            })
            serializer.is_valid(raise_exception=True)
            serializer.save()

            return Response(serializer.data, status=status.HTTP_201_CREATED)

        elif request.method == 'DELETE':
            deleted_count, _ = Favorite.objects.filter(
                user_id=user.id,
                recipe_id=recipe.id
            ).delete()

            if deleted_count == 0:
                return Response(
                    {'errors': 'Рецепта нет в избранном'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[permissions.IsAuthenticated],
    )
    def shopping_cart(self, request, pk=None):
        recipe = self.get_object()
        user = request.user

        if request.method == 'POST':
            cart_item, created = ShoppingCart.objects.get_or_create(
                user=user,
                recipe=recipe
            )
            if not created:
                return Response(
                    {'error': 'Рецепт уже в корзине'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            # Используем укороченный сериализатор
            serializer = ShortRecipeSerializer(recipe)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        elif request.method == 'DELETE':
            deleted_count, _ = ShoppingCart.objects.filter(
                user_id=user.id,
                recipe_id=recipe.id
            ).delete()

            if deleted_count == 0:
                return Response(
                    {'errors': 'Рецепта нет в корзине'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def shopping_cart_list(self, request):
        """Получить все рецепты в корзине покупок."""
        user = request.user

        cart_recipes = Recipe.objects.filter(shopping_cart__user=user)

        page = self.paginate_queryset(cart_recipes)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(cart_recipes, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def shopping_cart_count(self, request):
        """Получить актуальное количество рецептов в корзине."""
        user = request.user
        count = ShoppingCart.objects.filter(user=user).count()
        return Response({'count': count})

    def generate_shopping_list_text(self, user):
        """Генерирует текст списка покупок для пользователя."""
        shopping_list = RecipeIngredient.objects.filter(
            recipe__shopping_cart__user=user
        ).values(
            name=F('ingredient__name'),
            unit=F('ingredient__measurement_unit')
        ).annotate(total_amount=Sum('amount'))

        # Формируем текст
        text = "Foodgram - Список покупок\n"
        text += "=" * 40 + "\n\n"

        for item in shopping_list:
            text += (
                f"• {item['name']} - "
                f"{item['total_amount']} {item['unit']}\n"
            )

        text += f"\nВсего позиций: {shopping_list.count()}\n"
        text += "Приятных покупок! 🛒"

        return text

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[permissions.IsAuthenticated],
        url_path='download_shopping_cart',
        url_name='download_shopping_cart'
    )
    def download_shopping_cart(self, request):
        """Скачать список покупок в формате TXT"""
        user = request.user

        text = self.generate_shopping_list_text(user)

        # Создаем HTTP response с файлом
        response = HttpResponse(text, content_type='text/plain; charset=utf-8')
        response['Content-Disposition'] = (
            'attachment; filename="shopping_list.txt"'
        )

        return response


class TagViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer


class IngredientViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = IngredientSerializer
    queryset = Ingredient.objects.all()
    filter_backends = [filters.SearchFilter]
    search_fields = ['name']


class FavoriteViewSet(viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ShortRecipeSerializer
    pagination_class = RecipePagination

    def get_queryset(self):
        return Recipe.objects.filter(
            favorites__user=self.request.user
        ).select_related('author').prefetch_related('tags')

    def create(self, request, *args, **kwargs):
        """Добавить рецепт в избранное."""
        recipe_id = request.data.get('recipe_id')

        try:
            recipe = get_object_or_404(Recipe, id=recipe_id)
        except Recipe.DoesNotExist:
            return Response(
                {'error': 'Рецепт не найден'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Проверяем, не добавлен ли уже в избранное
        if Favorite.objects.filter(user=request.user, recipe=recipe).exists():
            return Response(
                {'error': 'Рецепт уже в избранном'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Создаем запись в избранном
        Favorite.objects.create(user=request.user, recipe=recipe)

        # Возвращаем данные рецепта
        serializer = ShortRecipeSerializer(
            recipe, context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Удалить рецепт из избранного."""
        try:
            recipe_id = kwargs.get('pk')
            favorite = Favorite.objects.get(
                user=request.user, recipe_id=recipe_id
            )
            favorite.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        except Favorite.DoesNotExist:
            return Response(
                {'error': 'Рецепт не найден в избранном'},
                status=status.HTTP_404_NOT_FOUND
            )
