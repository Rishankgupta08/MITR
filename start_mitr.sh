#!/bin/bash

cd home/omeeshahah/mitr/

source venv/bin/activate

# Check if Redis is running
if ! pgrep redis-server > /dev/null; then
    echo "Starting Redis server..."
    redis-server &
fi

# Start Celery beat
celery -A config beat -l info &

# Start Celery worker
celery -A config worker --pool=solo -l info &

#Clear screen for application logs
sleep 3 && clear

#Django development server
#python manage.py runserver_plus 0.0.0.0:8080 --cert-file certificates/cert.crt --key-file certificates/cert.key

#Gunicorn production server
gunicorn --certfile=certificates/cert.crt --keyfile=certificates/cert.key --bind 0.0.0.0:8080 config.wsgi:application
