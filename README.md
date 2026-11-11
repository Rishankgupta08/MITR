# MITR v2.0.1

Multi-tenant task management and subscription 
monitoring platform.

## Stack
- Django 6.1 + Gunicorn
- PostgreSQL (Supabase)
- django-q2 (task queue)
- Docker + supervisord (single container)

## Local Development
source .venv/bin/activate
python manage.py runserver 9000

## Docker
docker build -t mitr:local .
docker run -p 8000:8000 --env-file .env -e PORT=8000 mitr:local

## Deploy
Railway → single container
Supabase → managed PostgreSQL
