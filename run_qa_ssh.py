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

pid, fd = pty.fork()
if pid == 0:
    os.execvp("ssh", ["ssh", "-o", "StrictHostKeyChecking=no", "narix@10.0.0.54", "cd /home/narix/app/ProyectoCdc && echo '--- GIT ---' && git status && echo '--- LOG ---' && git log --oneline -5"])
else:
    flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    
    out = read_until(fd, b"assword:")
    sys.stdout.write(out.decode('utf-8', 'ignore'))
    os.write(fd, b"3346041\n")
    
    time.sleep(3)
    start = time.time()
    while time.time() - start < 5:
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
