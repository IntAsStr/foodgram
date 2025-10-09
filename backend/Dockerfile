FROM python:3.11-slim

WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код проекта
COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
RUN mkdir -p /app/collected_static

# Открываем порт
EXPOSE 8000

# Запускаем Gunicorn
ENTRYPOINT ["/entrypoint.sh"]
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "foodgram_backend.wsgi:application"]