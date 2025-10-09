import base64
import uuid
from django.core.files.base import ContentFile
from rest_framework import serializers
from users.models import User, Subscription
from .models import (
    Recipe, Ingredient, Tag, RecipeIngredient, ShoppingCart, Favorite
)


class Base64ImageField(serializers.ImageField):
    """
    Кастомное поле для Django REST Framework для обработки base64 изображений.
    """

    def to_internal_value(self, data):
        if isinstance(data, str) and data.startswith('data:image'):
            # Формат: data:image/png;base64,iVBORw0KGgo...
            try:
                # Разделяем header и данные
                header, base64_data = data.split(';base64,')
                # Получаем расширение файла
                file_extension = header.split('/')[-1]

                # Декодируем base64
                decoded_file = base64.b64decode(base64_data)

                # Создаем имя файла
                file_name = f"{uuid.uuid4()}.{file_extension}"

                # Создаем ContentFile для Django
                data = ContentFile(decoded_file, name=file_name)

            except (ValueError, TypeError, AttributeError) as e:
                raise serializers.ValidationError(f"Ошибка декодирования base64: {str(e)}")
            except Exception as e:
                raise serializers.ValidationError(f"Ошибка обработки изображения: {str(e)}")

        return super().to_internal_value(data)


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
    image = Base64ImageField(required=False, allow_null=True)
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

    def create(self, validated_data):
        try:
            ingredients_data = validated_data.pop('ingredients')
            tags = validated_data.pop('tags')

            # Создаем рецепт
            recipe = Recipe.objects.create(
                author=self.context['request'].user,
                **validated_data
            )

            # Добавляем теги
            for tag in tags:
                recipe.tags.add(tag)

            # Создаем связи с ингредиентами
            for ingredient_data in ingredients_data:
                RecipeIngredient.objects.create(
                    recipe=recipe,
                    ingredient_id=ingredient_data['id'],
                    amount=ingredient_data['amount']
                )

            return recipe

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise serializers.ValidationError(
                f"Ошибка при создании рецепта: {str(e)}"
            )

    def update(self, instance, validated_data):
        """Обновление рецепта с поддержкой частичного обновления."""
        try:
            # Извлекаем ingredients и tags если они есть
            ingredients_data = validated_data.pop('ingredients', None)
            tags_data = validated_data.pop('tags', None)

            # Обновляем основные поля
            for attr, value in validated_data.items():
                setattr(instance, attr, value)

            instance.save()

            # Обновляем теги если они переданы
            if tags_data is not None:
                instance.tags.set(tags_data)

            # Обновляем ингредиенты если они переданы
            if ingredients_data is not None:
                # Удаляем старые ингредиенты
                instance.recipe_ingredients.all().delete()

                # Создаем новые
                for ingredient_data in ingredients_data:
                    RecipeIngredient.objects.create(
                        recipe=instance,
                        ingredient_id=ingredient_data['id'],
                        amount=ingredient_data['amount']
                    )

            return instance

        except Exception as e:
            import traceback
            traceback.print_exc()
            raise serializers.ValidationError(
                f"Ошибка при обновлении рецепта: {str(e)}"
            )


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
        try:
            # Используем prefetch_related для оптимизации запросов
            recipe_ingredients = obj.recipe_ingredients.select_related(
                'ingredient'
            ).all()

            ingredients_data = []
            for recipe_ingredient in recipe_ingredients:
                ingredients_data.append({
                    'id': recipe_ingredient.ingredient.id,
                    'name': recipe_ingredient.ingredient.name,
                    'measurement_unit': (
                        recipe_ingredient.ingredient.measurement_unit
                        ),
                    'amount': recipe_ingredient.amount
                })

            return ingredients_data

        except Exception as e:
            print(f"⚠️ Ошибка при сериализации ингредиентов: {str(e)}")
            return []

    def get_tags(self, obj):
        """Безопасное получение тегов."""
        try:
            # Если это ManyRelatedManager - преобразуем в список
            if hasattr(obj.tags, 'all'):
                tags = obj.tags.all()
            else:
                tags = obj.tags
            return TagSerializer(tags, many=True).data
        except Exception as e:
            print(f"⚠️ Ошибка при сериализации тегов: {str(e)}")
            return []

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
    recipes_count = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = (
            'id', 'email', 'username', 'first_name', 'last_name',
            'avatar', 'is_subscribed', 'recipes', 'recipes_count'
        )

    def get_recipes(self, obj):
        """Получить рецепты автора с лимитом."""
        request = self.context.get('request')
        recipes_limit = request.query_params.get(
            'recipes_limit'
        ) if request else None

        try:
            recipes_limit = int(recipes_limit) if recipes_limit else None
        except ValueError:
            recipes_limit = None

        recipes = obj.recipes.all()
        if recipes_limit:
            recipes = recipes[:recipes_limit]

        return ShortRecipeSerializer(
            recipes,
            many=True,
            context=self.context
        ).data

    def get_recipes_count(self, obj):
        """Количество рецептов автора."""
        return obj.recipes.count()


class FavoritesSerializer(serializers.ModelSerializer):
    id = serializers.ReadOnlyField(source='recipe.id')
    name = serializers.ReadOnlyField(source='recipe.name')
    image = serializers.ImageField(source='recipe.image', read_only=True)
    cooking_time = serializers.ReadOnlyField(source='recipe.cooking_time')

    class Meta:
        model = Favorite
        fields = ('id', 'name', 'image', 'cooking_time')
