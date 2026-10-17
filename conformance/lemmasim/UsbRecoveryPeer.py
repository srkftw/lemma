import os,sys,time,fcntl
from pathlib import Path
root=Path(sys.argv[1]);fd=os.open(root/'spawn-count',os.O_CREAT|os.O_RDWR,0o600);fcntl.flock(fd,fcntl.LOCK_EX);raw=os.read(fd,32);n=int(raw or b'0')+1;os.lseek(fd,0,0);os.ftruncate(fd,0);os.write(fd,str(n).encode());os.fsync(fd);os.close(fd)
print('USBHOST/2 PACKET_BYTES_DEV',flush=True)
assert sys.stdin.readline()=='OPEN\n'
if n==1:
 print('WAIT 100000',flush=True)
 limit=time.monotonic()+30
 while not (root/'observed-pending').exists():
  assert time.monotonic()<limit
  time.sleep(.001)
 # Actual independent process/socket EOF after the machine observed Pending.
else:
 print('RESET 5000000',flush=True)
 assert sys.stdin.readline()=='RESET_DONE\n'
