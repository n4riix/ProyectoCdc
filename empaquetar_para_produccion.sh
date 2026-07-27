#!/bin/bash
# Script para empaquetar el sistema CDC completo para Producción (Offline)

echo "📦 1. Compilando imágenes Docker locales por si acaso..."
docker compose build

echo "📦 2. Exportando imágenes Docker a un archivo TAR (esto puede tardar unos minutos)..."
# Guardamos las imágenes de Redis y las de CDC
docker save redis:alpine cdc-web_auditor cdc-ia_trainer cdc-celery_worker -o imagenes_produccion.tar

echo "📦 3. Comprimiendo el código fuente y las imágenes (excluyendo basura)..."
cd ..
tar -czvf cdc_produccion_offline.tar.gz cdc/ --exclude="cdc/volumen_compartido/logs/*" --exclude="cdc/volumen_compartido/lote_kofax/*" --exclude="cdc/web_app/__pycache__"

echo "✅ Empaquetado completado. Archivo generado: ~/app/cdc_produccion_offline.tar.gz"
echo ""
echo "🚀 PASO FINAL PARA TI: Ejecuta el siguiente comando para transferirlo a producción:"
echo "scp ~/app/cdc_produccion_offline.tar.gz intexus@192.168.1.116:/home/intexus/"
