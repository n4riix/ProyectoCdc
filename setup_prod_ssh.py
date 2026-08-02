import pty
import os
import sys
import time
import fcntl

def read_until(fd, text, timeout=10):
    start = time.time()
    out = b""
    while time.time() - start < timeout:
        try:
            data = os.read(fd, 1024)
            out += data
            if text in out:
                return out
        except BlockingIOError:
            time.sleep(0.1)
    return out

commands = """
rm -rf /home/intexus/app/cdc/.git
mkdir -p /home/intexus/cdc.git
cd /home/intexus/cdc.git
git init --bare

cat << 'EOF' > hooks/post-receive
#!/bin/bash
TARGET="/home/intexus/app/cdc"
GIT_DIR="/home/intexus/cdc.git"
echo "📦 Desplegando nuevos cambios a Producción..."
mkdir -p $TARGET
git --work-tree=$TARGET --git-dir=$GIT_DIR checkout -f
echo "🔄 Reiniciando contenedores para aplicar cambios..."
cd $TARGET
docker compose restart cdc_web cdc_celery
echo "✅ Despliegue Exitoso."
EOF

chmod +x hooks/post-receive
echo "SETUP_DONE"
exit
"""

pid, fd = pty.fork()
if pid == 0:
    os.execvp("ssh", ["ssh", "-o", "StrictHostKeyChecking=no", "intexus@192.168.1.116"])
else:
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    
    out = read_until(fd, b"assword:")
    sys.stdout.write(out.decode('utf-8', 'ignore'))
    os.write(fd, b"Intexus01\n")
    
    time.sleep(2)
    os.write(fd, commands.encode('utf-8'))
    
    start = time.time()
    while time.time() - start < 15:
        try:
            data = os.read(fd, 4096)
            if not data: break
            sys.stdout.write(data.decode('utf-8', 'ignore'))
            start = time.time()
        except BlockingIOError:
            time.sleep(0.1)
            continue
        except OSError:
            break
