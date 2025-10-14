from django.contrib import admin

from .models import User


@admin.register(User)
class CustomUserAdmin(admin.ModelAdmin):
    """Админка для пользователей."""

    list_display = ('id', 'username', 'email', 'first_name', 'last_name')
    search_fields = ('username', 'email')
    list_filter = ('is_staff', 'is_superuser', 'is_active')
