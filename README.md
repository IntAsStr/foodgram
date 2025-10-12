# Foodgram - «Продуктовый помощник»

## Описание проекта
Foodgram - это веб-приложение для публикации рецептов. Пользователи могут создавать рецепты, добавлять их в избранное, подписываться на других авторов и формировать список покупок.

## Локальный запуск проекта

### Предварительные требования
- Docker
- Docker Compose

### Запуск
Клонируйте репозиторий:
git clone <repository-url>
cd foodgram/infra
Запустите контейнеры:

docker-compose up -d

Примените миграции и создайте суперпользователя:

docker-compose exec backend python manage.py migrate
docker-compose exec backend python manage.py createsuperuser
docker-compose exec backend python manage.py collectstatic --no-input


Основные возможности
📝 Создание и редактирование рецептов

❤️ Добавление рецептов в избранное

👥 Подписка на авторов

🛒 Формирование списка покупок

📥 Скачивание списка покупок в формате TXT