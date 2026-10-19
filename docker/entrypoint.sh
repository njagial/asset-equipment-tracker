#!/bin/sh
set -e

export DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-config.settings.prod}"

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ "$RUN_WEB" = "1" ]; then
    exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-4}"
elif [ "$RUN_CELERY_BEAT" = "1" ]; then
    exec celery -A config beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler
else
    exec celery -A config worker -l info --concurrency="${CELERY_CONCURRENCY:-2}"
fi
