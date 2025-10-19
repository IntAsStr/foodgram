from django.db.models import Count, Exists, F, OuterRef, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from foodgram_backend.constants import RECIPE_PAGE_SIZE
from recipes.models import (
    Favorite,
    Ingredient,
    Recipe,
    RecipeIngredient,
    ShoppingCart,
    Tag,
)
from users.models import Subscription, User

from .filters import RecipeFilter
from .permissions import IsAuthorOrReadOnly
from .serializers import (
    CustomUserCreateSerializer,
    FavoritesSerializer,
    IngredientSerializer,
    RecipeCreateSerializer,
    RecipeSerializer,
    ShortRecipeSerializer,
    SubscriptionCreateSerializer,
    SubscriptionSerializer,
    TagSerializer,
    UserAvatarSerializer,
    UserSerializer,
    ShoppingCartSerializer
)


class RecipePagination(PageNumberPagination):
    page_size = RECIPE_PAGE_SIZE
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

        if self.request.user.is_authenticated:

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
                'recipe': recipe.id
            }, context={'request': request})
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
            if ShoppingCart.objects.filter(user=user, recipe=recipe).exists():
                return Response(
                    {'error': 'Рецепт уже в корзине'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            cart_serializer = ShoppingCartSerializer(
                data={'recipe': recipe.id},
                context={'request': request}
            )

            if not cart_serializer.is_valid():
                return Response(
                    cart_serializer.errors,
                    status=status.HTTP_400_BAD_REQUEST
                )

            cart_serializer.save(user=user)

            return Response(
                cart_serializer.data, status=status.HTTP_201_CREATED
            )

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

    def generate_shopping_list_text(self, user):
        """Генерирует текст списка покупок для пользователя."""
        shopping_list = RecipeIngredient.objects.filter(
            recipe__shopping_cart__user=user
        ).values(
            name=F('ingredient__name'),
            unit=F('ingredient__measurement_unit')
        ).annotate(total_amount=Sum('amount'))

        text = 'Foodgram - Список покупок\n'
        text += '=' * 40 + '\n\n'

        for item in shopping_list:
            text += (
                f'• {item["name"]} - '
                f'{item["total_amount"]} {item["unit"]}\n'
            )

        text += f'\nВсего позиций: {shopping_list.count()}\n'
        text += 'Приятных покупок!'

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
    search_fields = ['^name']

    def filter_queryset(self, queryset):
        search_term = self.request.query_params.get('name')
        if search_term:
            return queryset.filter(name__istartswith=search_term)
        return queryset


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

        recipe = get_object_or_404(Recipe, id=recipe_id)

        if Favorite.objects.filter(user=request.user, recipe=recipe).exists():
            return Response(
                {'error': 'Рецепт уже в избранном'},
                status=status.HTTP_400_BAD_REQUEST
            )

        favorite_data = {'user': request.user.id, 'recipe': recipe_id}
        favorite_serializer = FavoritesSerializer(data=favorite_data)

        if not favorite_serializer.is_valid():
            return Response(
                favorite_serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )

        favorite_serializer.save()

        serializer = ShortRecipeSerializer(
            recipe, context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """Удалить рецепт из избранного."""
        recipe_id = kwargs.get('pk')

        deleted_count, _ = Favorite.objects.filter(
            user=request.user,
            recipe_id=recipe_id
        ).delete()

        if deleted_count == 0:
            return Response(
                {'error': 'Рецепт не найден в избранном'},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(status=status.HTTP_204_NO_CONTENT)


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    pagination_class = RecipePagination
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.action == 'create':
            return CustomUserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticatedOrReadOnly()]

    def get_queryset(self):
        queryset = super().get_queryset()

        if self.request.user.is_authenticated:
            subscribed = Subscription.objects.filter(
                user=self.request.user,
                author=OuterRef('pk')
            )
            queryset = queryset.annotate(
                is_subscribed=Exists(subscribed)
            )
        return queryset

    def perform_create(self, serializer):
        """Сохраняет пользователя и возвращает его."""
        user = serializer.save()
        return user

    def get_serializer_context(self):
        """Передаем request в сериализатор для построения полных URL."""
        context = super().get_serializer_context()
        context['request'] = self.request
        return context

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[permissions.IsAuthenticated]
    )
    def me(self, request):
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(
        detail=False,
        methods=['get', 'put', 'delete'],
        url_path='me/avatar',
        permission_classes=[permissions.IsAuthenticated]
    )
    def avatar(self, request):
        user = request.user

        if request.method == 'GET':
            avatar_url = None
            if user.avatar:
                avatar_url = request.build_absolute_uri(user.avatar.url)
            return Response({'avatar': avatar_url})

        elif request.method == 'PUT':
            serializer = UserAvatarSerializer(
                user, data=request.data, partial=True
            )

            if not serializer.is_valid():
                return Response(
                    serializer.errors, status=status.HTTP_400_BAD_REQUEST
                )

            serializer.save()

            avatar_url = None
            if user.avatar:
                avatar_url = request.build_absolute_uri(user.avatar.url)
            return Response({'avatar': avatar_url})

        elif request.method == 'DELETE':
            if not user.avatar:
                return Response(
                    {'error': 'Аватар не установлен'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            user.avatar.delete()

            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[permissions.IsAuthenticated]
    )
    def subscribe(self, request, pk=None):
        author = self.get_object()
        user = request.user

        if request.method == 'POST':
            serializer = SubscriptionCreateSerializer(
                data={'author': author.id},
                context={'request': request}
            )
            serializer.is_valid(raise_exception=True)

            serializer.save()

            author_serializer = SubscriptionSerializer(
                author,
                context={'request': request}
            )
            return Response(
                author_serializer.data,
                status=status.HTTP_201_CREATED
            )

        elif request.method == 'DELETE':
            deleted_count, _ = Subscription.objects.filter(
                user_id=user.id,
                author_id=author.id
            ).delete()
            if deleted_count == 0:
                return Response(
                    {'error': 'Вы не подписаны на этого пользователя'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=['get'],
        permission_classes=[permissions.IsAuthenticated]
    )
    def subscriptions(self, request):
        """Список моих подписок."""
        user = request.user
        subscribed_authors = User.objects.filter(
            subscribed_to__user=user
        ).annotate(
            recipes_count=Count('recipes', distinct=True)
        ).prefetch_related('recipes')

        page = self.paginate_queryset(subscribed_authors)
        if page is not None:
            serializer = SubscriptionSerializer(
                page, many=True, context={'request': request}
            )
            response = self.get_paginated_response(serializer.data)
            return response

        serializer = SubscriptionSerializer(
            subscribed_authors, many=True, context={'request': request}
        )
        response_data = serializer.data
        return Response(response_data)
