from django.contrib import admin

from api.models import (
    Favorite,
    Ingredient,
    Recipe,
    RecipeIngredient,
    ShoppingCart,
    Tag,
)


class RecipeIngredientInline(admin.TabularInline):
    """Инлайн для отображения ингредиентов в рецепте."""

    model = RecipeIngredient
    extra = 1
    min_num = 1


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    """Админка для тегов."""

    list_display = ('id', 'name', 'slug')
    list_display_links = ('name',)
    search_fields = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    """Админка для ингредиентов."""

    list_display = ('id', 'name', 'measurement_unit')
    list_display_links = ('name',)
    search_fields = ('name',)
    list_filter = ('measurement_unit',)


@admin.register(Recipe)
class RecipeAdmin(admin.ModelAdmin):
    """Админка для рецептов."""

    list_display = (
        'id', 'name', 'author', 'cooking_time',
        'pub_date', 'favorites_count'
    )
    list_display_links = ('name',)
    search_fields = ('name', 'author__username', 'tags__name')
    list_filter = ('tags', 'pub_date', 'author')
    filter_horizontal = ('tags',)
    inlines = (RecipeIngredientInline,)
    readonly_fields = ('pub_date',)

    def favorites_count(self, obj):
        return obj.favorites.count()


@admin.register(RecipeIngredient)
class RecipeIngredientAdmin(admin.ModelAdmin):
    """Админка для связи рецепт-ингредиент."""

    list_display = ('id', 'recipe', 'ingredient', 'amount')
    list_display_links = ('recipe',)
    search_fields = ('recipe__name', 'ingredient__name')
    list_filter = ('recipe', 'ingredient')


@admin.register(Favorite)
class FavoriteAdmin(admin.ModelAdmin):
    """Админка для избранных рецептов."""

    list_display = ('id', 'user', 'recipe')
    list_display_links = ('user',)
    search_fields = ('user__username', 'recipe__name')
    list_filter = ('user', 'recipe')


@admin.register(ShoppingCart)
class ShoppingCartAdmin(admin.ModelAdmin):
    """Админка для корзины покупок."""

    list_display = ('id', 'user', 'recipe')
    list_display_links = ('user',)
    search_fields = ('user__username', 'recipe__name')
    list_filter = ('user', 'recipe')