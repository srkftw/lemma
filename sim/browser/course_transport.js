// SPDX-License-Identifier: Apache-2.0
// Raw transport only. Package contents, CRC, publication and durable receipts
// are checked by the RV64 guest; declared header fields remain untrusted.
const MAX_TRANSACTION=(1n<<63n)-1n;
export function courseInstallFrame(bytes,transaction){
 if(!(bytes instanceof ArrayBuffer)||bytes.byteLength<128||bytes.byteLength>32768)
  throw Error('Choose a package containing 128 to32768 bytes');
 if(typeof transaction!=='string'||!/^[1-9][0-9]{0,18}$/.test(transaction))
  throw Error('Use a positive decimal installation transaction');
 const tx=BigInt(transaction);
 if(tx>MAX_TRANSACTION)throw Error('Installation transaction exceeds its bound');
 const header=new DataView(bytes),identity=header.getBigUint64(24,true),edition=header.getBigUint64(32,true),crc=header.getBigUint64(80,true);
 if(identity<1n||identity>65535n||edition<1n||edition>0xffffffffn||crc>0xffffffffn)
  throw Error('Declared package identity, edition or checksum exceeds the transport bound');
 const packet=new Uint8Array(bytes.byteLength+64),view=new DataView(packet.buffer);
 const fields=[0x31504b43414d454cn,1n,1n,identity,edition,BigInt(bytes.byteLength),tx,crc];
 for(let i=0;i<fields.length;i++)view.setBigUint64(i*8,fields[i],true);
 packet.set(new Uint8Array(bytes),64);
 return packet;
}

// Additive guest-selected publication command. Old installers keep v1 only.
export function schoolSelectionRequested(operation,guestSupportsSelection){
 return guestSupportsSelection&&['sample','install','review'].includes(operation);
}
export function courseSelectionFrame(bytes,transaction,node=0){
 const packet=courseInstallFrame(bytes,transaction).slice(0,64),view=new DataView(packet.buffer);
 if(!Number.isSafeInteger(node)||node<0||node>15)throw Error('Selected node ordinal exceeds its bound');
 view.setBigUint64(8,4n,true);view.setBigUint64(16,9n,true);view.setBigUint64(40,BigInt(node),true);
 return packet;
}
export function courseSchoolFrames(bytes,transaction,selected,node=0){
 const install=courseInstallFrame(bytes,transaction);
 if(!selected)return install;
 const selection=courseSelectionFrame(bytes,transaction,node),all=new Uint8Array(install.length+selection.length);
 all.set(install);all.set(selection,install.length);return all;
}

// Each event fits the existing raw-device line bound even at UINT64_MAX.
// All rows have one virtual timestamp; the machine retains their byte order.
export function courseInstallRows(packet,cycle){
 if(!(packet instanceof Uint8Array)||packet.length<64||packet.length>32896||
    typeof cycle!=='string'||!/^\d+$/.test(cycle)||BigInt(cycle)>(1n<<64n)-1n)
  throw Error('Invalid bounded course transport packet or virtual cycle');
 const rows=[];
 for(let offset=0;offset<packet.length;offset+=112){
  const hex=Array.from(packet.subarray(offset,offset+112),value=>value.toString(16).padStart(2,'0')).join('');
  rows.push(`${cycle} uart ${hex}`);
 }
 return rows;
}
