#!/bin/bash
# Improved connector script for production diagnostics
# Uses sshpass with forced pseudo‑tty (-tt) and disables host‑key checking.
# All stdout/stderr are captured in conector.log for later review.

LOGFILE="/home/ecastro/app/cdc/conector.log"

# Execute SSH command
sshpass -p 'Intexus01' ssh -tt -o StrictHostKeyChecking=no \
    intexus@192.168.1.116 "cd /home/intexus/app/cdc && bash --login" \
    > "$LOGFILE" 2>&1

echo "Ejecución completada. Salida guardada en $LOGFILE"
