#!/bin/bash

set -e

echo "⌛ Waiting for database..."
sleep 10

echo "⌛ Applying database migrations..."
python manage.py migrate --noinput

echo "⌛ Loading ingredients..."
python manage.py shell -c "
import json
from api.models import Ingredient

try:
    with open('/app/data/ingredients.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    created_count = 0
    for item in data:
        obj, created = Ingredient.objects.get_or_create(
            name=item['name'],
            defaults={'measurement_unit': item['measurement_unit']}
        )
        if created:
            created_count += 1
    
    print(f'✅ Загружено {created_count} новых ингредиентов! Всего в базе: {Ingredient.objects.count()}')
    
except Exception as e:
    print(f'❌ Ошибка загрузки ингредиентов: {e}')
"

echo "⌛ Collecting static files..."
python manage.py collectstatic --noinput

echo "✅ Backend is ready!"

exec "$@"