from django.conf import settings
from django.db.models import Count, Exists, OuterRef
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from api.serializers import SubscriptionSerializer, UserSerializer

from .models import Subscription, User
from .serializers import CustomUserCreateSerializer, UserAvatarSerializer


class UserPagination(PageNumberPagination):
    page_size = settings.USERS_PAGE_SIZE
    page_size_query_param = 'page_size'


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    pagination_class = UserPagination
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return CustomUserCreateSerializer
        return UserSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        queryset = super().get_queryset()

        # Аннотируем is_subscribed для АВТОРА (того, на кого смотрим)
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

    def retrieve(self, request, *args, **kwargs):
        return super().retrieve(request, *args, **kwargs)

    @action(
        detail=False,
        methods=['get', 'put', 'delete'],
        url_path='me/avatar'
    )
    def avatar(self, request):
        user = request.user

        if request.method == 'GET':
            avatar_url = None
            if user.avatar:
                avatar_url = request.build_absolute_uri(user.avatar.url)
            return Response({'avatar': avatar_url})

        elif request.method == 'PUT':
            try:
                print(f"🔍 Полученные данные: {request.data}")  # для отладки

                serializer = UserAvatarSerializer(
                    user, data=request.data, partial=True
                )

                if not serializer.is_valid():
                    return Response(
                        serializer.errors, status=status.HTTP_400_BAD_REQUEST
                    )

                serializer.save()

                # Возвращаем новый URL аватара
                avatar_url = None
                if user.avatar:
                    avatar_url = request.build_absolute_uri(user.avatar.url)
                return Response({'avatar': avatar_url})

            except Exception as e:
                import traceback
                traceback.print_exc()
                return Response(
                    {'error': f'Ошибка при обновлении аватара: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        elif request.method == 'DELETE':
            if not user.avatar:
                return Response(
                    {'error': 'Аватар не установлен'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Удаляем аватар
            user.avatar.delete(save=False)
            user.avatar = None
            user.save()

            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post', 'delete'])
    def subscribe(self, request, pk=None):
        author = self.get_object()
        user = request.user

        if request.method == 'POST':
            # Проверяем, не подписан ли уже
            if Subscription.objects.filter(user=user, author=author).exists():
                return Response(
                    {'error': 'Вы уже подписаны на этого пользователя'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Проверяем, не пытается подписаться на себя
            if user == author:
                return Response(
                    {'error': 'Нельзя подписаться на самого себя'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Создаем подписку
            Subscription.objects.create(user=user, author=author)

            # Возвращаем данные автора с is_subscribed=True
            serializer = self.get_serializer(author)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        elif request.method == 'DELETE':
            # Удаляем подписку
            subscription = Subscription.objects.filter(
                user=user, author=author
            )
            if not subscription.exists():
                return Response(
                    {'error': 'Вы не подписаны на этого пользователя'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            subscription.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        methods=['post'],
        permission_classes=[permissions.IsAuthenticated]
    )
    def set_password(self, request):
        """Смена пароля."""
        user = request.user
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')

        if not current_password or not new_password:
            return Response(
                {'error': 'Требуются current_password и new_password'},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not user.check_password(current_password):
            return Response(
                {'error': 'Неверный текущий пароль'},
                status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(new_password)
        user.save()
        return Response({'message': 'Пароль успешно изменен'})

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
