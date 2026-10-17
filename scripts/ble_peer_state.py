"""Fail-closed raw hosted BLE peer/2 response and private-state framing.

This is host transport validation. It neither generates link transitions nor
accepts a mathematical/document result or a companion durability receipt.
"""
from dataclasses import dataclass
import re

MAX_COUNTER=0x7fffffffffffffff
STATE_MASK=0x30f
DECIMAL=r'(?:0|[1-9][0-9]*)'
ACTION=re.compile(r'(?:BLEPEER/2 OPEN_MANUAL_UNAUTHENTICATED_CONTEXT|RESTORED PRIVATE_CONTEXT|'
                  r'TX '+DECIMAL+r' 0 -|EMPTY_RX|STATUS|CREDIT 1|'
                  r'ERROR '+DECIMAL+r' (?:RESTORE|SIZE|FORMAT|COMMAND|COUNTER|CONTEXT|FROZEN|HEADER))')
@dataclass(frozen=True)
class PeerState:
 state:int
 accepted:int
 duplicates:int
 pending:bytes
 def restore_command(self):
  return f'RESTORE {self.state} {self.accepted} {self.duplicates} '+(self.pending.hex() if self.pending else '-')

def parse_response(line):
 if not isinstance(line,str) or len(line)>256 or '\n' in line or '\r' in line:
  raise ValueError('peer response exceeds bounded frame')
 parts=line.split(' | ')
 if len(parts)!=2 or not ACTION.fullmatch(parts[0]):raise ValueError('unknown peer/2 response action')
 fields=parts[1].split(' ')
 if len(fields)!=9 or fields[0]!='STATE' or fields[2]!='ACCEPTED' or fields[4]!='DUPLICATES' or fields[6]!='PENDING':
  raise ValueError('incomplete peer/2 authoritative state')
 if any(not re.fullmatch(DECIMAL,fields[index]) for index in [1,3,5,7]):raise ValueError('invalid peer state number')
 state,accepted,duplicates,length=[int(fields[index]) for index in [1,3,5,7]]
 data=fields[8]
 if data!='-' and not re.fullmatch(r'(?:[0-9a-f]{2}){1,27}',data):raise ValueError('invalid opaque peer head')
 pending=b'' if data=='-' else bytes.fromhex(data)
 if len(pending)!=length or not 0<=length<=27 or (pending and accepted==0):raise ValueError('peer head length/receipt count differs')
 if not 0<=accepted<=MAX_COUNTER or not 0<=duplicates<=MAX_COUNTER:raise ValueError('peer counter outside declared bound')
 attempts=(state>>8)&3
 outstanding=bool(state&4)
 frozen=bool(state&8)
 if state&STATE_MASK!=state or (frozen and outstanding) or (bool(attempts)!=outstanding):
  raise ValueError('invalid complete peer link state')
 words=parts[0].split()
 if words[0]=='TX' and (int(words[1])>255 or frozen or not outstanding):raise ValueError('peer TX violates state admission')
 return parts[0],PeerState(state,accepted,duplicates,pending)
