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

// Publication is presented only as a complete newly emitted guest report.
// This observer neither inspects documents nor completes a backing barrier.
export function guestCommitState(bytes,start){
 if(!(bytes instanceof Uint8Array)||!Number.isSafeInteger(start)||start<0||start>bytes.length)
  throw Error('Guest UART history was truncated or has an invalid observation boundary');
 const text=new TextDecoder().decode(bytes.subarray(start));
 const record=/(?:^|\n)K1 (000000000000042[134]) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16}) ([0-9a-f]{16})\r?(?=\n)/g;
 let result=null,match;
 while((match=record.exec(text))!==null){
  const fields=match.slice(2).map(value=>BigInt('0x'+value).toString());
  result={authority:'compiled-guest-report',state:match[1].endsWith('1')?'saved':match[1].endsWith('3')?'pending':'failed',
   recordKind:match[1],value:fields[0],page:fields[1],namespace:fields[2],detail:fields[3]};
 }
 return result;
}

// Observe only complete guest installer reports. Transport admission, parsing
// and a queued write never establish installation or durability here.
export function guestCourseInstallState(bytes,start){
 const fields=guestRecordFields(bytes,start,'00000000000004b1');
 if(fields===null)return null;
 const [outcome,sequence,object,crc]=fields.map(value=>BigInt('0x'+value));
 const operation=outcome&255n,status=outcome>>8n;
 if(operation!==1n||status>255n||object>>48n||crc>0xffffffffn)return null;
 const identity=object&65535n,edition=object>>16n;
 if(identity===0n||edition===0n||(status===0n&&sequence===0n))return null;
 return {authority:'compiled-guest-report',state:status===0n?'installed':'failed',
  status:status.toString(),identity:identity.toString(),edition:edition.toString(),
  sequence:sequence.toString(),crc32:crc.toString()};
}
