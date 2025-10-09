from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError


class User(AbstractUser):
    username = models.CharField(
        'username',
        max_length=150,
        unique=True
    )
    email = models.EmailField(
        'email address',
        unique=True,
        help_text='Обязательное поле. Укажите действующий email.'
    )
    first_name = models.CharField(
        'first name',
        max_length=150,
        help_text='Обязательное поле. Укажите ваше имя.'
    )
    last_name = models.CharField(
        'last name',
        max_length=150,
        help_text='Обязательное поле. Укажите вашу фамилию.'
    )
    avatar = models.ImageField(
        'Аватар',
        upload_to='users/avatars/',
        blank=True,
        null=True,
        max_length=500
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        ordering = ['email']

    def __str__(self):
        return self.email


class Subscription(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='subscriber',  # кто подписывается
        verbose_name='Подписчик'
    )
    author = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='subscribed_to',  # на кого подписываются
        verbose_name='Автор'
    )

    class Meta:
        verbose_name = 'Подписка'
        verbose_name_plural = 'Подписки'
        # Один пользователь не может подписаться на одного автора дважды
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'author'],
                name='unique_subscription'
            )
        ]
        # Нельзя подписаться на самого себя
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'author'],
                name='unique_subscription'
            ),
            models.CheckConstraint(
                check=~models.Q(user=models.F('author')),
                name='prevent_self_subscription'
            )
        ]

    def clean(self):
        """Валидация на уровне модели."""
        if self.user == self.author:
            raise ValidationError('Нельзя подписаться на самого себя')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.user} подписан на {self.author}'
