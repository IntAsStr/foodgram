from django.db.models import F, Sum
from django.http import HttpResponse
from django.shortcuts import render
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


from .filters import RecipeFilter
from .models import (
    Favorite, Ingredient, Recipe, RecipeIngredient, ShoppingCart, Tag
)
from .permissions import IsAuthorOrReadOnly
from .serializers import (
    IngredientSerializer,
    RecipeCreateSerializer,
    RecipeSerializer,
    ShortRecipeSerializer,
    TagSerializer,
)


class RecipePagination(PageNumberPagination):
    page_size = 6
    page_size_query_param = 'page_size'


class RecipeViewSet(viewsets.ModelViewSet):
    serializer_class = RecipeSerializer
    queryset = Recipe.objects.all()
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

    def create(self, request, *args, **kwargs):
        try:
            return super().create(request, *args, **kwargs)
        except Exception as e:
            return Response(
                {"error": f"Ошибка при создании рецепта: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

    def get_queryset(self):
        queryset = super().get_queryset()

        queryset = queryset.select_related('author').prefetch_related(
            'tags', 'recipe_ingredients__ingredient'
        )

        # ФИЛЬТРАЦИЯ ПО ИЗБРАННОМУ
        is_favorited = self.request.query_params.get('is_favorited')
        if is_favorited == '1' and self.request.user.is_authenticated:
            queryset = queryset.filter(favorites__user=self.request.user)

        # фильтр корзины
        is_in_shopping_cart = self.request.query_params.get(
            'is_in_shopping_cart'
        )
        if is_in_shopping_cart == '1' and self.request.user.is_authenticated:
            queryset = queryset.filter(shopping_cart__user=self.request.user)

        # фильтрация по тегам
        tags = self.request.query_params.getlist('tags')

        if tags:
            # Фильтруем по ЛЮБОМУ из переданных тегов (OR логика)
            from django.db.models import Q
            tag_filter = Q()
            for tag_slug in tags:
                tag_filter |= Q(tags__slug=tag_slug)
            queryset = queryset.filter(tag_filter).distinct()
        # Фильтрация по автору
        author_id = self.request.query_params.get('author')
        if author_id:
            queryset = queryset.filter(author_id=author_id)
            print(f"🔍 После фильтра автора: {queryset.count()}")

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
            # Проверяем, не добавлен ли уже
            if Favorite.objects.filter(user=user, recipe=recipe).exists():
                return Response(
                    {'error': 'Рецепт уже в избранном'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Создаем запись
            Favorite.objects.create(user=user, recipe=recipe)

            # Возвращаем данные рецепта как в спецификации
            return Response({
                'id': recipe.id,
                'name': recipe.name,
                'image': request.build_absolute_uri(
                    recipe.image.url
                ) if recipe.image else None,
                'cooking_time': recipe.cooking_time
            }, status=status.HTTP_201_CREATED)

        elif request.method == 'DELETE':
            # Удаляем из избранного
            favorite = Favorite.objects.filter(user=user, recipe=recipe)
            if not favorite.exists():
                return Response(
                    {'error': 'Рецепта нет в избранном'},
                    status=status.HTTP_404_NOT_FOUND
                )

            favorite.delete()
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
            cart_item = ShoppingCart.objects.filter(user=user, recipe=recipe)
            if not cart_item.exists():
                return Response(
                    {'error': 'Рецепта нет в корзине'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            cart_item.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['get'])
    def shopping_cart_list(self, request):
        """Получить все рецепты в корзине покупок."""
        user = request.user

        # ПРАВИЛЬНЫЙ способ - фильтруем по модели ShoppingCart
        cart_recipes = Recipe.objects.filter(shopping_cart__user=user)

        print(f"🔍 Найдено рецептов в корзине: {cart_recipes.count()}")

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
        print(f"🔍 Актуальное количество в корзине: {count}")  # для отладки
        return Response({'count': count})

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

        # Получаем ингредиенты из корзины с суммированием
        shopping_list = RecipeIngredient.objects.filter(
            recipe__shopping_cart__user=user
        ).values(
            name=F('ingredient__name'),
            unit=F('ingredient__measurement_unit')
        ).annotate(total_amount=Sum('amount'))

        # Формируем текст
        text = "🍽️ Foodgram - Список покупок\n"
        text += "=" * 40 + "\n\n"

        for item in shopping_list:
            text += (
                f"• {item['name']} - "
                f"{item['total_amount']} {item['unit']}\n"
            )

        text += f"\nВсего позиций: {shopping_list.count()}\n"
        text += "Приятных покупок! 🛒"

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
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer


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

        if not recipe_id:
            return Response(
                {'error': 'recipe_id обязателен'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            recipe = Recipe.objects.get(id=recipe_id)
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


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def favorites_page(request):
    return render(request, 'index.html')
