#!/bin/bash
sshpass -p 'intexus01' ssh -o StrictHostKeyChecking=no intexus@10.1.1.62 "
echo '=== CONSULTANDO ULTIMO LOTE ==='
docker exec cdc_postgres psql -U intexus -d cdc_database -c \"SELECT id, estado, documentos_procesados, total_documentos, fecha_inicio, fecha_fin FROM auditorias_lotes ORDER BY fecha_inicio DESC LIMIT 1;\"

echo ''
echo '=== ULTIMAS 10 LINEAS INSERTADAS EN RESULTADOS DE ESE LOTE ==='
docker exec cdc_postgres psql -U intexus -d cdc_database -c \"SELECT linea_indice, archivo, matriz, subproceso, esperado, prediccion, estado FROM auditoria_resultados WHERE auditoria_id = (SELECT id FROM auditorias_lotes ORDER BY fecha_inicio DESC LIMIT 1) ORDER BY linea_indice DESC LIMIT 10;\"

echo ''
echo '=== ULTIMAS 10 DISCREPANCIAS (danger) POR LINEA INDICE ==='
docker exec cdc_postgres psql -U intexus -d cdc_database -c \"SELECT linea_indice, archivo, matriz, subproceso, esperado, prediccion, estado FROM auditoria_resultados WHERE auditoria_id = (SELECT id FROM auditorias_lotes ORDER BY fecha_inicio DESC LIMIT 1) AND estado = 'danger' ORDER BY linea_indice DESC LIMIT 10;\"
"
