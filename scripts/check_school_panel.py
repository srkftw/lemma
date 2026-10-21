#!/usr/bin/env python3
"""Actual native panel/Lean transport checks and optional isolated Xvfb rendering."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import select
import socket
import struct
import subprocess
import sys
import time
import zlib

from core0_common import Core0Error,repo_root,sha256,write_json
from check_school_job_worker import check_production
from lemmasim_school_panel import Connection,Panel,SAMPLE,review_photo_image


def capture(window,path):
    """Read the isolated test X server pixels with XGetImage and encode PNG."""
    import ctypes.util
    library=ctypes.util.find_library("X11")
    if not library:
        for line in Path("/proc/self/maps").read_text().splitlines():
            if "libX11.so" in line:library=line.split()[-1];break
    if not library:raise Core0Error("actual X11 screenshot library unavailable")
    x=ctypes.CDLL(library)
    class XImage(ctypes.Structure):
        _fields_=[("width",ctypes.c_int),("height",ctypes.c_int),("xoffset",ctypes.c_int),("format",ctypes.c_int),
                  ("data",ctypes.c_void_p),("byte_order",ctypes.c_int),("bitmap_unit",ctypes.c_int),
                  ("bitmap_bit_order",ctypes.c_int),("bitmap_pad",ctypes.c_int),("depth",ctypes.c_int),
                  ("bytes_per_line",ctypes.c_int),("bits_per_pixel",ctypes.c_int),
                  ("red_mask",ctypes.c_ulong),("green_mask",ctypes.c_ulong),("blue_mask",ctypes.c_ulong)]
    x.XOpenDisplay.restype=ctypes.c_void_p;x.XOpenDisplay.argtypes=[ctypes.c_char_p]
    x.XDefaultRootWindow.restype=ctypes.c_ulong;x.XDefaultRootWindow.argtypes=[ctypes.c_void_p]
    x.XGetImage.restype=ctypes.POINTER(XImage)
    x.XGetImage.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_int,ctypes.c_uint,ctypes.c_uint,ctypes.c_ulong,ctypes.c_int]
    x.XDestroyImage.argtypes=[ctypes.POINTER(XImage)];x.XCloseDisplay.argtypes=[ctypes.c_void_p]
    display=x.XOpenDisplay(None)
    if not display:raise Core0Error("isolated test display unavailable")
    width,height=window.winfo_width(),window.winfo_height()
    image=x.XGetImage(display,x.XDefaultRootWindow(display),window.winfo_rootx(),window.winfo_rooty(),width,height,ctypes.c_ulong(-1).value,2)
    if not image:raise Core0Error("actual XGetImage failed")
    try:
        info=image.contents
        if info.bits_per_pixel!=32 or info.byte_order!=0 or (info.red_mask,info.green_mask,info.blue_mask)!=(0xff0000,0xff00,0xff):
            raise Core0Error("unsupported actual screenshot pixel representation")
        raw=ctypes.string_at(info.data,info.bytes_per_line*height)
        pixels=bytearray()
        for y in range(height):
            pixels.append(0)
            for offset in range(y*info.bytes_per_line,y*info.bytes_per_line+width*4,4):
                pixels.extend((raw[offset+2],raw[offset+1],raw[offset]))
        def chunk(kind,data):return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
        path.write_bytes(b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",width,height,8,2,0,0,0))+chunk(b"IDAT",zlib.compress(pixels))+chunk(b"IEND",b""))
    finally:x.XDestroyImage(image);x.XCloseDisplay(display)


def check(args):
    root=repo_root();out=args.work_dir.resolve();out.mkdir(parents=True,exist_ok=False)
    production=check_production(args.school_production,args.binary,args.curriculum)
    connection=Connection(out/"authority",args.session_dir,"panel-school","owner",args.binary,args.curriculum)
    connection.command("init",deployment="panel-local-a",clockModel="monotonic-ms")
    original=connection.curriculum_command("fixture")
    fixture=json.loads(SAMPLE.read_text(encoding="utf-8"))
    expected=json.loads(json.dumps(original));expected["course"]["identity"]="1"
    if original["course"]["identity"]!="801" or fixture!=expected:
        raise Core0Error("shared sample must preserve the original fixture except the explicit teacher identity edit")
    preview=connection.curriculum_command("preview",SAMPLE)
    compilation=connection.curriculum_command("compile",SAMPLE,out/"sample.lcp")
    if compilation["sha256"]!=sha256(out/"sample.lcp"):
        raise Core0Error("actual Lean sample compile receipt differs from retained bytes")
    published=connection.command("publish",path=str(SAMPLE.resolve()),policy=1)
    course=int(fixture["course"]["identity"])
    connection.command("enroll",learner="owner",course=course,revision=1)
    opened=connection.command("client-course",course=course,revision=1)
    if hashlib.sha256(bytes.fromhex(opened["package_hex"])).hexdigest()!=opened["artifact"]:
        raise Core0Error("panel transport altered the actual published course bytes")
    if bytes.fromhex(opened["package_hex"])!=(out/"sample.lcp").read_bytes():
        raise Core0Error("normal school publication differs from direct shared-sample Lean compilation")
    outsider=Connection(connection.school_root,args.session_dir,connection.school,"ungranted",args.binary,args.curriculum)
    try:outsider.command("progress",learner="owner")
    except RuntimeError as error:
        if "grant denied" not in str(error):raise
    else:raise Core0Error("panel bypassed scoped learner evidence authorization")
    unit=connection.edited_unit(json.dumps(fixture,ensure_ascii=False))
    if connection.curriculum_command("preview",unit)!=preview:
        raise Core0Error("teacher editor path changed shared authoring preview")
    connection.command("attempt",id="panel-explicit-work",course=course,revision=1,
                       activity="coefficients",values=[0,1,1,2,1])
    # The mutation's final append is its scheduled review; progress exposes the
    # actual immutable attempt referenced by the learner declaration.
    attempts=connection.command("progress")["attempts"]
    if len(attempts)!=1:raise Core0Error("panel typed attempt was not committed exactly once")
    attempt=attempts[0]
    choice_fields={"learner":"owner","course":course,"revision":1,"policy":1,
                   "referenceKind":"attempt","reference":attempt["key"],
                   "reason":"I choose to reconstruct these coefficients independently."}
    local_goal=connection.command("goal-set",id="panel-local-goal",newGoal="Independent reconstruction.",**choice_fields)["record"]
    with socket.socket() as candidate:candidate.bind(("127.0.0.1",0));port=candidate.getsockname()[1]
    endpoint=f"http://127.0.0.1:{port}/v1/command"
    log=(out/"service.log").open("wb")
    service=subprocess.Popen([sys.executable,str(root/"scripts/school_transport.py"),"--binary",str(args.binary.resolve()),str(connection.school_root),"run","--port",str(port)],cwd=root,stdout=log,stderr=log)
    log.close();http=Connection(connection.school_root,args.session_dir,connection.school,"owner",args.binary,args.curriculum,endpoint)
    gui=None
    try:
        deadline=time.monotonic()+10
        while True:
            try:status=http.command("status");break
            except Exception:
                if time.monotonic()>deadline:raise
                time.sleep(.05)
        before_runtime=json.loads((connection.school_root/"transport.json").read_text())
        local_status=connection.command("status")
        after_runtime=json.loads((connection.school_root/"transport.json").read_text())
        if local_status["generation"]!=status["generation"] or before_runtime!=after_runtime:
            raise Core0Error("ordinary local query did not use the existing authority generation")
        competing=subprocess.run([sys.executable,str(root/"scripts/school_transport.py"),"--binary",str(args.binary.resolve()),
            str(connection.school_root),"run","--port",str(port)],cwd=root,capture_output=True,timeout=10)
        if competing.returncode==0 or b"already owned" not in competing.stderr:
            raise Core0Error("second actual authority bypassed the singleton mutex")
        http_challenge=http.command("interpretation-challenge",id="panel-http-challenge",**choice_fields)["record"]
        choices=http.command("learner-choices")["choices"]
        if choices!=[local_goal,http_challenge] or any(row["data"]["original"]["sequence"]!=attempt["sequence"] for row in choices):
            raise Core0Error("native/HTTP panel choices lost exact original attempt identity")
        try:http.command("suggestion-override",id="panel-override-attempt",**choice_fields)
        except RuntimeError as error:
            if "recommendation override requires a suggestion reference" not in str(error):raise
        else:raise Core0Error("panel overrode an attempt without an eligible suggestion")
        if args.gui:
            import tkinter as tk
            from tkinter import ttk
            xlog=(out/"xvfb.log").open("wb")
            xvfb=subprocess.Popen(["Xvfb","-displayfd","1","-screen","0","1280x1000x24","-nolisten","tcp"],stdout=subprocess.PIPE,stderr=xlog)
            xlog.close()
            try:
                if not select.select([xvfb.stdout],[],[],10)[0]:raise Core0Error("isolated GUI test server timeout")
                os.environ["DISPLAY"]=":"+xvfb.stdout.readline().decode().strip()
                window=tk.Tk()
                # Exercise the actual Tk binary decoder, including sampled
                # gray4 nibble order; a window alone does not prove ink rendered.
                packed=bytearray([255])*(825*2200)
                packed[:7]=bytes((0x0f,0xf0,0xff,0xff,0x7f,0xff,0x00))
                packed[825:832]=bytes((0xff,0xff,0x0f,0xf0,0xff,0xff,0x00))
                picture=review_photo_image(tk,dict(width=1650,height=2200,stride=825,gray4Hex=packed.hex()))
                expected=((191,)*3,)*4+((221,)*3,(255,)*3,(0,)*3)
                if (picture.width(),picture.height())!=(825,1100) or tuple(picture.get(x,0) for x in range(7))!=expected:
                    raise Core0Error("actual Tk area reduction lost a source pixel or changed gray4 order")
                try:review_photo_image(tk,dict(width=1650,height=2200,stride=825,gray4Hex='ff'))
                except RuntimeError:pass
                else:raise Core0Error("teacher preview accepted a truncated raster")
                panel_args=argparse.Namespace(school=connection.school,actor="owner",session_dir=args.session_dir,
                    school_root=connection.school_root,school_executable=args.binary,curriculum_executable=args.curriculum,
                    controlled_now=None,school_endpoint=endpoint,port=port)
                panel=Panel(window,panel_args)
                if panel.values["course"].get()!="1" or panel.values["revision"].get()!="1":
                    raise Core0Error("immediate sample requires bounded default guest selector identity1/1")
                panel.fixture()
                deadline=time.monotonic()+10
                while panel.busy and time.monotonic()<deadline:window.update();time.sleep(.01)
                if panel.busy or json.loads(panel.editor.get("1.0","end-1c"))!=fixture:
                    raise Core0Error("actual GUI did not load exact shared sample authoring JSON")
                panel.school_action("status")
                deadline=time.monotonic()+10
                while panel.busy and time.monotonic()<deadline:window.update();time.sleep(.01)
                window.update()
                if panel.busy or "panel-school" not in panel.output.get("1.0","end"):
                    raise Core0Error("actual GUI did not deliver actual Lean status")
                def wait_activity():
                    deadline=time.monotonic()+10
                    while panel.busy and time.monotonic()<deadline:window.update();time.sleep(.01)
                    if panel.busy:raise Core0Error("actual GUI learner declaration timed out")
                revision=json.loads(json.dumps(fixture));revision["course"]["edition"]="2"
                panel.editor.delete("1.0","end");panel.editor.insert("1.0",json.dumps(revision))
                panel.publication_policy.set("2");panel.unit_action(True);wait_activity()
                def publications():
                    stored=json.loads((connection.school_root/"state.json").read_text())["payload"]
                    return [record for record in stored["records"] if record["kind"]=="publication"]
                actual_publications=publications()
                if (len(actual_publications)!=2 or actual_publications[0]!=published["record"] or
                    actual_publications[1]["data"]["revision"]!=2 or actual_publications[1]["data"]["policy"]!=2):
                    raise Core0Error("teacher panel lost the selected publication policy or changed the original edition")
                panel.editor.delete("1.0","end");panel.editor.insert("1.0",json.dumps(fixture))
                panel.unit_action(True);wait_activity()
                if "immutable publication conflict" not in panel.output.get("1.0","end") or publications()!=actual_publications:
                    raise Core0Error("teacher panel silently retargeted an old publication policy")
                revision["course"]["edition"]="3"
                panel.editor.delete("1.0","end");panel.editor.insert("1.0",json.dumps(revision))
                panel.publication_policy.set("0");panel.unit_action(True);wait_activity()
                if "policy version must be in the admitted signed range" not in panel.output.get("1.0","end") or publications()!=actual_publications:
                    raise Core0Error("teacher panel bypassed the actual Lean policy-version rejection")
                panel.editor.delete("1.0","end");panel.editor.insert("1.0",json.dumps(fixture))
                panel.publication_policy.set("2")
                panel.choice_kind.set("attempt");panel.choice_reference.set(attempt["key"])
                panel.choice_policy.set("1");panel.choice_reason.set("I request independent reconstruction of this original work.")
                panel.choice_goal.set("Reconstruct the distributive coefficients independently.")
                for op,identity in (("goal-set","panel-gui-goal"),("interpretation-challenge","panel-gui-challenge")):
                    panel.choice_id.set(identity);panel.learner_choice(op);wait_activity()
                    if identity not in panel.output.get("1.0","end"):
                        raise Core0Error("actual GUI did not display its committed learner declaration")
                panel.choice_id.set("panel-gui-invalid-override");panel.learner_choice("suggestion-override");wait_activity()
                if "recommendation override requires a suggestion reference" not in panel.output.get("1.0","end"):
                    raise Core0Error("actual GUI did not display Lean override rejection")
                panel.school_action("learner-choices");wait_activity()
                if "panel-gui-goal" not in panel.output.get("1.0","end") or "panel-gui-challenge" not in panel.output.get("1.0","end"):
                    raise Core0Error("actual GUI did not display actual learner declaration history")
                def descendants(widget):
                    for child in widget.winfo_children():yield child;yield from descendants(child)
                notebooks=[w for w in descendants(window) if isinstance(w,ttk.Notebook)]
                tabs=[notebooks[0].tab(item,"text") for item in notebooks[0].tabs()]
                if len(tabs)!=4:raise Core0Error("native activity switching surface missing")
                if panel.output.winfo_rooty()+panel.output.winfo_height()>window.winfo_rooty()+window.winfo_height():
                    raise Core0Error("actual authority result is outside the visible panel")
                screenshots={}
                for index,item in enumerate(notebooks[0].tabs()):
                    notebooks[0].select(item);window.update()
                    path=out/f"panel-tab-{index}.png";capture(window,path)
                    screenshots[tabs[index]]={"path":path.name,"sha256":sha256(path)}
                notebooks[0].select(notebooks[0].tabs()[0]);window.update()
                capture(window,out/"panel.png")
                canvas=panel.choice_frame.master.master
                canvas.yview_moveto(1);window.update()
                if not (window.winfo_rooty()<=panel.choice_frame.winfo_rooty()<panel.output.winfo_rooty()):
                    raise Core0Error("learner declaration form cannot be scrolled into view above actual results")
                capture(window,out/"panel-study-choices.png")
                gui={"result":"pass","tabs":tabs,"screenshotSha256":sha256(out/"panel.png"),
                     "tabScreenshots":screenshots,"authorityResultInsideVisibleWindow":True,
                     "learnerChoiceScreenshot":{"path":"panel-study-choices.png","sha256":sha256(out/"panel-study-choices.png")},
                     "actualGoalChallengeAndHistoryDisplayed":True,"actualAttemptOverrideRejected":True,
                     "publicationPolicySelection":{"newEdition":2,"newPolicy":2,"originalEditionUnchanged":True,
                         "oldEditionPolicyConflictRejected":True,"zeroPolicyRejectedByLean":True},
                     "teacherRasterPresentation":{"pixels":[825,1100],"areaSamplesPreserveAllFourPixelPositions":True,
                         "gray4OrderPreserved":True,"truncatedImageRejected":True,"decoder":"Tk binary PPM/PGM"},
                     "actualLeanStatusDisplayed":True,"windowPixels":[window.winfo_width(),window.winfo_height()],
                     "scope":"actual Tk rendering and status RPC in isolated Xvfb; guest drawing is a separate maintained client acceptance"}
                window.destroy()
            finally:xvfb.terminate();xvfb.wait(timeout=5)
        final_choices=http.command("learner-choices")["choices"]
        expected_ops=["goal-set","interpretation-challenge"]* (2 if args.gui else 1)
        if ([row["data"]["op"] for row in final_choices]!=expected_ops or
            http.command("progress")["attempts"]!=[attempt]):
            raise Core0Error("panel learner declarations changed original work or lost committed history")
        http.command("stop");service.wait(timeout=5)
    finally:
        if service.poll() is None:service.terminate();service.wait(timeout=5)
    check_production(args.school_production,args.binary,args.curriculum)
    report={"schema":"lemma-school-native-panel-evidence/v1","result":"pass","schoolProductionSha256":sha256(args.school_production),
            "schoolBinarySha256":sha256(args.binary),"curriculumBinarySha256":sha256(args.curriculum),
            "actualNativeAndHttpTransport":True,"scopedEvidenceDenied":True,"activeAuthorityMutexEnforced":True,
            "ordinaryLocalQueryUsesRunningAuthority":True,"secondActualAuthorityRejected":True,
            "authoringPreview":preview,"publication":published,"gui":gui,"sampleCompilation":compilation,
            "sampleAuthoringSha256":sha256(SAMPLE),"sampleIdentity":[course,1],
            "learnerChoices":{"originalAttempt":attempt,"records":final_choices,
                              "actualNativeGoalAndHttpChallenge":True,"attemptOverrideRejected":True,
                              "originalAttemptUnchanged":True,
                              "scope":"deliberately supplied local typed attempt; no fabricated guest or model suggestion; positive actual RV64 override is in job-worker checker"},
            "sampleDerivation":"sole teacher edit to actual original fixture: course.identity801 to1; original fixture preserved",
            "sourceInputs":{name:sha256(root/name) for name in ["scripts/lemmasim_school_panel.py","scripts/school_transport.py",
                "scripts/lemmasim_school.py","scripts/lemmasim","tooling/lemmasim/session.nix","examples/school/sample-unit.json"]},"runnerSha256":sha256(Path(__file__))}
    write_json(out/"panel-evidence.json",report);return report


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--work-dir",type=Path,required=True)
    parser.add_argument("--binary",type=Path,required=True);parser.add_argument("--curriculum",type=Path,required=True)
    parser.add_argument("--school-production",type=Path,required=True);parser.add_argument("--session-dir",type=Path,required=True)
    parser.add_argument("--gui",action="store_true");args=parser.parse_args()
    report=check(args);print(json.dumps({"result":report["result"],"gui":report["gui"],"receipt":str(args.work_dir/"panel-evidence.json")},indent=2))
if __name__=="__main__":main()
