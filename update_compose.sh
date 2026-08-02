#!/bin/bash
# Update docker-compose.yml on production server
REMOTE_USER="intexus"
REMOTE_HOST="192.168.1.116"
REMOTE_PASS="Intexus01"
REMOTE_PATH="/home/intexus/app/cdc/docker-compose.yml"
COMPOSE_CONTENT="version: '3.8'

services:
  # ----------------------------------------------------
  # SERVICIO 0: POSTGRESQL (Base de Datos Relacional)
  # ----------------------------------------------------
  postgres:
    image: postgres:15-alpine
    container_name: cdc_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: ${DB_USER:-intexus}
      POSTGRES_PASSWORD: ${DB_PASSWORD:-intexus01}
      POSTGRES_DB: ${DB_NAME:-cdc_database}
    volumes:
      - ./volumen_compartido/postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"

  # ----------------------------------------------------
  # SERVICIO 1: FRONTEND Y BACKEND (El Auditor Web 24/7)
  # ----------------------------------------------------
  cdc_web:
    build:
      context: ./web_app
    container_name: cdc_web
    ports:
      - "5000:5000"
    environment:
      - PYTHONUNBUFFERED=1
      - SECRET_KEY=${SECRET_KEY:-intexus_key}
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
      - ENVIRONMENT=${ENVIRONMENT:-LOCAL}
      - DB_TYPE=${DB_TYPE:-sqlite}
      - DB_HOST=${DB_HOST:-postgres}
      - DB_USER=${DB_USER:-intexus}
      - DB_PASSWORD=${DB_PASSWORD:-intexus01}
      - DB_NAME=${DB_NAME:-cdc_database}
      - DB_PORT=${DB_PORT:-5432}
    depends_on:
      - redis
      - postgres
    volumes:
      - ./web_app:/app
      - ./volumen_compartido:/volumen_compartido
      - ./volumen_compartido/paddle_modelos:/home/appuser/.paddleocr
    restart: unless-stopped

  # ----------------------------------------------------
  # SERVICIO 2: EL ENTRENADOR DE IA (Bajo Demanda)
  # ----------------------------------------------------
  ia_trainer:
    build:
      context: ./trainer_app
    container_name: cdc_trainer
    environment:
      - PYTHONUNBUFFERED=1
      - SECRET_KEY=${SECRET_KEY:-intexus_key}
      - ENVIRONMENT=${ENVIRONMENT:-LOCAL}
      - DB_TYPE=${DB_TYPE:-sqlite}
      - DB_HOST=${DB_HOST:-postgres}
      - DB_USER=${DB_USER:-intexus}
      - DB_PASSWORD=${DB_PASSWORD:-intexus01}
      - DB_NAME=${DB_NAME:-cdc_database}
      - DB_PORT=${DB_PORT:-5432}
    depends_on:
      - postgres
    volumes:
      - ./trainer_app:/app
      - ./volumen_compartido:/volumen_compartido
      - ./volumen_compartido/paddle_modelos:/home/appuser/.paddleocr
    restart: unless-stopped

  # ----------------------------------------------------
  # SERVICIO 3: REDIS (Intermediario de Tareas)
  # ----------------------------------------------------
  redis:
    image: redis:alpine
    container_name: cdc_redis
    restart: unless-stopped
    ports:
      - "6379:6379"

  # ----------------------------------------------------
  # SERVICIO 4: CELERY WORKER (Procesamiento de IA en 2do Plano)
  # ----------------------------------------------------
  celery_worker:
    build:
      context: ./web_app
    container_name: cdc_celery
    environment:
      - PYTHONUNBUFFERED=1
      - CELERY_BROKER_URL=redis://redis:6379/0
      - CELERY_RESULT_BACKEND=redis://redis:6379/0
      - ENVIRONMENT=${ENVIRONMENT:-LOCAL}
      - DB_TYPE=${DB_TYPE:-sqlite}
      - DB_HOST=${DB_HOST:-postgres}
      - DB_USER=${DB_USER:-intexus}
      - DB_PASSWORD=${DB_PASSWORD:-intexus01}
      - DB_NAME=${DB_NAME:-cdc_database}
      - DB_PORT=${DB_PORT:-5432}
    volumes:
      - ./web_app:/app
      - ./volumen_compartido:/volumen_compartido
      - ./volumen_compartido/paddle_modelos:/home/appuser/.paddleocr
    command: celery -A celery_app.celery worker --loglevel=info
    restart: unless-stopped
    depends_on:
      - redis
      - postgres
"
