// SPDX-License-Identifier: Apache-2.0
// Presentation observes complete newly emitted guest records only. Reset
// retains UART history; that history cannot establish the next boot's Ready.
export function guestRecord(bytes, start, code) {
 return guestRecordFields(bytes,start,code)!==null;
}
export function guestRecordFields(bytes, start, code) {
 if(!(bytes instanceof Uint8Array)||!Number.isSafeInteger(start)||start<0||start>bytes.length)
  throw Error('Guest UART history was truncated or has an invalid observation boundary');
 if(!/^[0-9a-f]{16}$/.test(code))throw Error('Invalid guest record kind');
 const text=new TextDecoder().decode(bytes.subarray(start));
 const record=new RegExp('(?:^|\\n)K1 '+code+' ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\\r?(?=\\n)','g');
 let fields=null,match;
 while((match=record.exec(text))!==null)fields=match.slice(1);
 return fields;
}

// The notebook first enters its event loop (420), then finishes upload and
// accepts an opened-page refresh (425). The RTL completion must cover that
// exact sequence before the UI may report Ready. All sequence values remain
// strings/BigInts; a browser Number cannot round a 64-bit sequence into success.
export function guestPageReady(bytes,start,paper){
 if(!guestRecord(bytes,start,'0000000000000420'))return false;
 const opened=guestRecordFields(bytes,start,'0000000000000425');
 if(opened===null)return false;
 if(!paper||typeof paper.completed!=='string'||typeof paper.accepted!=='string'||
    !/^\d+$/.test(paper.completed)||!/^\d+$/.test(paper.accepted))
  throw Error('Invalid controller sequence observation');
 const sequence=BigInt('0x'+opened[0]);
 return sequence>0n&&BigInt(paper.completed)>=sequence&&BigInt(paper.accepted)>=sequence;
}
