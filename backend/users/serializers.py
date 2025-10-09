import base64
import uuid

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from djoser.serializers import UserCreateSerializer
from rest_framework import serializers


User = get_user_model()


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
