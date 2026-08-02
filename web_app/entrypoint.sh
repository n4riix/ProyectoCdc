#!/bin/bash
# =======================================================
# Script de Arranque Inteligente CDC
# Lee ENVIRONMENT y elige el servidor correcto.
# =======================================================

ENVIRONMENT="${ENVIRONMENT:-LOCAL}"

echo ""
echo "========================================"
echo "  CDC Auditor Inteligente - Iniciando"
echo "  Entorno: $ENVIRONMENT"
echo "========================================"

if [ "$ENVIRONMENT" = "LOCAL" ] || [ "$ENVIRONMENT" = "DEV" ]; then
    echo "🔧 Modo Desarrollo — Flask Dev Server (debug + auto-reload activos)"
    echo "   ⚠️  NO usar este modo en servidores reales."
    echo ""
    exec python app.py
else
    echo "🚀 Modo $ENVIRONMENT — Gunicorn (producción, multi-worker, robusto)"
    echo ""
    exec gunicorn \
        --workers 2 \
        --bind 0.0.0.0:5000 \
        --timeout 600 \
        --preload \
        --access-logfile - \
        --error-logfile - \
        app:app
fi
