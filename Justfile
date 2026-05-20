down:
    docker compose down --remove-orphans

up:
    docker compose -f docker-compose.yml up -d

build:
    docker compose -f docker-compose.yml build

logs *args:
    @docker compose logs -f {{ args }}

makemigrations *args:
    docker compose exec web python manage.py makemigrations {{ args }}

migrate:
    docker compose exec web python manage.py migrate

run *args:
    docker compose exec web python manage.py {{ args }}
