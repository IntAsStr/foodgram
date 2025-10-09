import json

from django.core.management.base import BaseCommand

from api.models import Ingredient


class Command(BaseCommand):
    help = 'Load ingredients from JSON file'

    def handle(self, *args, **options):
        try:
            with open('data/ingredients.json', 'r', encoding='utf-8') as f:
                data = json.load(f)

            ingredients = []
            for item in data:
                ingredients.append(Ingredient(
                    name=item['name'],
                    measurement_unit=item['measurement_unit']
                ))

            Ingredient.objects.bulk_create(ingredients)
            self.stdout.write(
                self.style.SUCCESS(
                    f'Успешно загружено {len(ingredients)} ингредиентов'
                )
            )
        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR('Файл data/ingredients.json не найден')
            )
