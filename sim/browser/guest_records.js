// SPDX-License-Identifier: Apache-2.0
// Presentation observes complete newly emitted guest records only. Reset
// retains UART history; that history cannot establish the next boot's Ready.
export function guestRecord(bytes, start, code) {
 if(!(bytes instanceof Uint8Array)||!Number.isSafeInteger(start)||start<0||start>bytes.length)
  throw Error('Guest UART history was truncated or has an invalid observation boundary');
 if(!/^[0-9a-f]{16}$/.test(code))throw Error('Invalid guest record kind');
 const text=new TextDecoder().decode(bytes.subarray(start));
 const record=new RegExp('(?:^|\\n)K1 '+code+'(?: [0-9a-f]{16}){4}\\r?\\n');
 return record.test(text);
}
