import pexpect
import sys

print("Connecting to 192.168.1.116...")
child = pexpect.spawn("ssh -o StrictHostKeyChecking=no intexus@192.168.1.116", encoding='utf-8')
child.logfile = sys.stdout

try:
    i = child.expect(['assword:', pexpect.EOF, pexpect.TIMEOUT], timeout=10)
    if i == 0:
        child.sendline("Intexus01")
        child.expect(r'\$')
        
        # We are in. Let's check the hook
        print("\n\n--- CONNECTED ---")
        child.sendline("cat /home/intexus/cdc.git/hooks/post-receive")
        child.expect(r'\$')
        
        print("\n--- HOOK CONTENTS ---")
        print(child.before)
        
        child.sendline("ls -l /home/intexus/cdc.git/hooks/post-receive")
        child.expect(r'\$')
        print("\n--- HOOK PERMISSIONS ---")
        print(child.before)
        
        child.sendline("exit")
    else:
        print("Failed to get password prompt.")
        print(child.before)
except Exception as e:
    print(f"Exception: {e}")
