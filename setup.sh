#!/bin/bash
echo "_____________________________________________"
echo "   Установка системы информационного табло   "
echo "_____________________________________________"
read -p "Введите логин для админ-панели [admin]: " admin_user
admin_user=${admin_user:-admin}

read -sp "Введите пароль для админ-панели: " admin_pass
echo ""

echo "ADMIN_USERNAME=$admin_user" > .env
echo "ADMIN_PASSWORD"=$admin_pass >> .env

echo "Файл .env успешно создан!"
echo "Запускается сборка и старт контейнера..."


docker-compose up -d --build

echo "Готово! Админ-панель доступна по адресу: http://localhost:8000/admin"
echo "Логин: $admin_user"
