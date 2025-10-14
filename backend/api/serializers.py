import base64
import uuid

from django.core.files.base import ContentFile
from djoser.serializers import UserCreateSerializer
from rest_framework import serializers

from users.models import Subscription, User

from recipes.models import (
    Favorite, Ingredient, Recipe, RecipeIngredient, ShoppingCart, Tag
)


class Base64AvatarField(serializers.ImageField):
    def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith('data:image'):
            try:
                # Разделяем header и данные
                format, imgstr = data.split(';base64,')
                # Получаем расширение файла
                ext = format.split('/')[-1]

                # Декодируем base64
                decoded_file = base64.b64decode(imgstr)

                # Создаем уникальное имя файла
                file_name = f"{uuid.uuid4().hex[:10]}.{ext}"
                # Создаем ContentFile для Django
                data = ContentFile(decoded_file, name=file_name)

            except (ValueError, TypeError, AttributeError) as e:
                raise serializers.ValidationError(
                    f"Ошибка декодирования изображения: {str(e)}"
                )
            except Exception as e:
                raise serializers.ValidationError(
                    f"Ошибка обработки изображения: {str(e)}"
                )

        return super().to_internal_value(data)


class CustomUserCreateSerializer(UserCreateSerializer):
    class Meta(UserCreateSerializer.Meta):
        model = User
        fields = ('email', 'username', 'first_name', 'last_name', 'password')


class UserAvatarSerializer(serializers.ModelSerializer):
    avatar = Base64AvatarField(required=False, allow_null=True)

    class Meta:
        model = User
        fields = ('avatar',)


class UserSerializer(serializers.ModelSerializer):
    is_subscribed = serializers.SerializerMethodField()
    avatar = serializers.ImageField(read_only=True)

    class Meta:
        model = User
        fields = (
            'id',
            'email',
            'username',
            'first_name',
            'last_name',
            'avatar',
            'is_subscribed'
        )

    def get_is_subscribed(self, obj):
        """Проверяет, подписан ли текущий пользователь на этого автора."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Subscription.objects.filter(
                user=request.user,
                author=obj
            ).exists()
        return False


class TagSerializer(serializers.ModelSerializer):
    class Meta:
        model = Tag
        fields = ('id', 'name', 'slug')


class IngredientSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ingredient
        fields = ('id', 'name', 'measurement_unit')


class RecipeIngredientSerializer(serializers.ModelSerializer):
    ingredient = IngredientSerializer(read_only=True)

    class Meta:
        model = RecipeIngredient
        fields = ('ingredient', 'amount')


class RecipeIngredientCreateSerializer(serializers.ModelSerializer):
    # Меняем на id вместо name, так как фронтенд отправляет id
    id = serializers.IntegerField()
    amount = serializers.IntegerField()

    class Meta:
        model = RecipeIngredient
        fields = ('id', 'amount')

    def to_internal_value(self, data):
        # Обрабатываем входящие данные (id и amount)
        return {
            'ingredient_id': data.get('id'),  # Сохраняем как ingredient_id
            'amount': data.get('amount')
        }


class RecipeCreateSerializer(serializers.ModelSerializer):
    ingredients = serializers.ListField(
        child=serializers.DictField(),
        required=False
    )
    tags = serializers.PrimaryKeyRelatedField(
        queryset=Tag.objects.all(),
        many=True,
        required=False
    )
    image = Base64AvatarField(required=False, allow_null=True)
    cooking_time = serializers.IntegerField(required=False)

    class Meta:
        model = Recipe
        fields = (
            'name', 'image', 'text', 'ingredients', 'tags', 'cooking_time'
        )

    def to_representation(self, instance):
        return RecipeSerializer(instance, context=self.context).data

    def to_internal_value(self, data):
        result = super().to_internal_value(data)
        return result

    def validate(self, data):
        """Валидация для создания и обновления рецепта."""
        # Для создания рецепта проверяем все обязательные поля
        if self.context['request'].method == 'POST':
            required_fields = [
                'name', 'text', 'ingredients', 'tags', 'cooking_time'
            ]
            for field in required_fields:
                if field not in data or not data[field]:
                    raise serializers.ValidationError({
                        field: 'Это поле обязательно при создании рецепта.'
                    })

        # Для обновления рецепта проверяем только переданные поля
        if self.context['request'].method in ['PUT', 'PATCH']:
            # Если переданы ингредиенты - проверяем их
            if 'ingredients' in data and data['ingredients'] is not None:
                if not data['ingredients']:
                    raise serializers.ValidationError({
                        'ingredients': 'Рецепт должен содержать ингредиенты.'
                    })

            # Если переданы теги - проверяем их
            if 'tags' in data and data['tags'] is not None:
                if not data['tags']:
                    raise serializers.ValidationError({
                        'tags': 'Рецепт должен содержать теги.'
                    })

        return data

    def validate_ingredients(self, value):
        """Валидация ингредиентов с преобразованием типов."""
        if value is None:
            return value

        if not value:
            raise serializers.ValidationError(
                "Рецепт должен содержать ингредиенты"
            )

        ingredient_ids = set()
        validated_ingredients = []

        for ingredient in value:
            if not isinstance(ingredient, dict):
                raise serializers.ValidationError(
                    "Ингредиент должен быть объектом"
                )

            if 'id' not in ingredient or 'amount' not in ingredient:
                raise serializers.ValidationError(
                    "Ингредиент должен содержать id и amount"
                )

            # Преобразуем типы
            try:
                ingredient_id = int(ingredient['id'])
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    "id ингредиента должен быть числом"
                )

            try:
                amount = int(ingredient['amount'])
            except (ValueError, TypeError):
                raise serializers.ValidationError(
                    "amount ингредиента должен быть числом"
                )

            if amount <= 0:
                raise serializers.ValidationError(
                    "amount ингредиента должен быть положительным числом"
                )

            # Проверяем уникальность
            if ingredient_id in ingredient_ids:
                raise serializers.ValidationError(
                    "Ингредиенты не должны повторяться"
                )
            ingredient_ids.add(ingredient_id)

            # Сохраняем преобразованные данные
            validated_ingredients.append({
                'id': ingredient_id,
                'amount': amount
            })

        return validated_ingredients

    def _create_or_update_tags(self, recipe, tags_data):
        """Создать или обновить теги рецепта."""
        recipe.tags.set(tags_data)

    def _create_or_update_ingredients(self, recipe, ingredients_data):
        """Создать или обновить ингредиенты рецепта."""
        # Удаляем старые ингредиенты
        recipe.recipe_ingredients.all().delete()

        # Создаем новые пачкой
        ingredients_to_create = [
            RecipeIngredient(
                recipe=recipe,
                ingredient_id=ingredient_data['id'],
                amount=ingredient_data['amount']
            )
            for ingredient_data in ingredients_data
        ]
        RecipeIngredient.objects.bulk_create(ingredients_to_create)

    def create(self, validated_data):
        ingredients_data = validated_data.pop('ingredients')
        tags = validated_data.pop('tags')

        # Создаем рецепт
        recipe = Recipe.objects.create(
            author=self.context['request'].user,
            **validated_data
        )

        # Добавляем теги
        self._create_or_update_tags(recipe, tags)

        # Создаем связи с ингредиентами
        self._create_or_update_ingredients(recipe, ingredients_data)

        return recipe

    def update(self, instance, validated_data):
        """Обновление рецепта с поддержкой частичного обновления."""
        # Извлекаем ingredients и tags если они есть
        ingredients_data = validated_data.pop('ingredients', None)
        tags_data = validated_data.pop('tags', None)

        # Обновляем основные поля
        instance = super().update(instance, validated_data)

        # Обновляем теги и ингредиенты через общие методы
        if tags_data is not None:
            self._create_or_update_tags(instance, tags_data)
        if ingredients_data is not None:
            self._create_or_update_ingredients(instance, ingredients_data)

        return instance


class RecipeIngredientReadSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='ingredient.id')
    name = serializers.ReadOnlyField(source='ingredient.name')
    measurement_unit = serializers.ReadOnlyField(
        source='ingredient.measurement_unit'
    )

    class Meta:
        model = RecipeIngredient
        fields = ('id', 'name', 'measurement_unit', 'amount')


class RecipeSerializer(serializers.ModelSerializer):
    author = UserSerializer(read_only=True)
    tags = serializers.SerializerMethodField()
    ingredients = serializers.SerializerMethodField()
    is_favorited = serializers.SerializerMethodField()
    is_in_shopping_cart = serializers.SerializerMethodField()
    image = serializers.ImageField(read_only=True)

    class Meta:
        model = Recipe
        fields = (
            'id', 'author', 'name', 'image', 'text',
            'ingredients', 'tags', 'cooking_time', 'pub_date',
            'is_favorited', 'is_in_shopping_cart'
        )

    def get_ingredients(self, obj):
        """Получаем ингредиенты с названиями и единицами измерения."""
        return RecipeIngredientReadSerializer(
            obj.recipe_ingredients.select_related('ingredient').all(),
            many=True
        ).data

    def get_tags(self, obj):
        """Безопасное получение тегов."""
        return TagSerializer(obj.tags.all(), many=True).data

    def get_is_favorited(self, obj):
        """Проверяет, в избранном ли рецепт у текущего пользователя."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return Favorite.objects.filter(
                user=request.user,
                recipe=obj
            ).exists()
        return False

    def get_is_in_shopping_cart(self, obj):
        """Проверяет, в корзине ли рецепт у текущего пользователя."""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return ShoppingCart.objects.filter(
                user=request.user,
                recipe=obj
            ).exists()
        return False


class ShortRecipeSerializer(serializers.ModelSerializer):
    """Укороченный сериализатор для избранного и корзины."""
    image = serializers.ImageField(read_only=True)

    class Meta:
        model = Recipe
        fields = ('id', 'name', 'image', 'cooking_time')


class CartRecipeSerializer(serializers.ModelSerializer):
    """Сериализатор для отображения рецептов в корзине"""
    image = serializers.ImageField(read_only=True)

    class Meta:
        model = Recipe
        fields = ('id', 'name', 'image', 'cooking_time')


class SubscriptionSerializer(serializers.ModelSerializer):
    is_subscribed = serializers.BooleanField(default=True, read_only=True)
    recipes = serializers.SerializerMethodField()
    recipes_count = serializers.IntegerField(default=0, read_only=True)

    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'first_name', 'last_name',
            'avatar', 'is_subscribed', 'recipes', 'recipes_count'
        )

    def validate(self, data):
        """Валидация данных подписки."""
        user = data['user']
        author = data['author']

        if user == author:
            raise serializers.ValidationError(
                'Нельзя подписаться на самого себя'
            )

        if Subscription.objects.filter(user=user, author=author).exists():
            raise serializers.ValidationError(
                'Вы уже подписаны на этого пользователя'
            )

        return data

    def get_recipes(self, obj):
        """Получить рецепты автора с лимитом."""
        request = self.context.get('request')
        recipes_limit = request.query_params.get(
            'recipes_limit'
        ) if request else None

        if recipes_limit and recipes_limit.isdigit():
            recipes_limit = int(recipes_limit)
        else:
            recipes_limit = None

        recipes = obj.recipes.all()
        if recipes_limit:
            recipes = recipes[:recipes_limit]

        return ShortRecipeSerializer(
            recipes,
            many=True,
            context=self.context
        ).data


class SubscriptionCreateSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    author = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

    class Meta:
        model = Subscription
        fields = ('user', 'author')

    def validate(self, data):
        """Валидация данных подписки."""
        user = data['user']
        author = data['author']

        if user == author:
            raise serializers.ValidationError(
                'Нельзя подписаться на самого себя'
            )

        if Subscription.objects.filter(user=user, author=author).exists():
            raise serializers.ValidationError(
                'Вы уже подписаны на этого пользователя'
            )
        return data


class FavoritesSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='recipe.id')
    name = serializers.ReadOnlyField(source='recipe.name')
    image = serializers.ImageField(source='recipe.image', read_only=True)
    cooking_time = serializers.ReadOnlyField(source='recipe.cooking_time')
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    recipe = serializers.PrimaryKeyRelatedField(queryset=Recipe.objects.all())

    class Meta:
        model = Favorite
        fields = ('id', 'name', 'image', 'cooking_time', 'user', 'recipe')

    def create(self, validated_data):
        """Создаем запись в избранном."""
        # Извлекаем user и recipe из validated_data
        user = validated_data['user']
        recipe = validated_data['recipe']

        favorite = Favorite.objects.create(user=user, recipe=recipe)
        return favorite
