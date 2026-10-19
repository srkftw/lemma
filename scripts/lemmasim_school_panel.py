#!/usr/bin/env python3
"""Native activity panel for an existing LemmaSim session and local Lean school.

This is a host presentation/byte-transport binding. Lean owns authoring,
authorization, enrollment, tutoring, assessment, jobs and durable transitions.
Guest drawing and package/tutor delivery use the existing actual session bridge.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import signal
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import uuid
import webbrowser

ROOT=Path(__file__).resolve().parents[1]
SAMPLE=ROOT/"examples/school/sample-unit.json"

@dataclass
class Connection:
    school_root: Path
    session_dir: Path
    school: str
    actor: str
    binary: Path
    curriculum: Path
    endpoint: str | None = None

    def _run(self,argv,*,label):
        out=ROOT/"build/school/panel-actions"/uuid.uuid4().hex
        out.mkdir(parents=True,exist_ok=False)
        (out/"command.json").write_text(json.dumps(argv,indent=2)+"\n")
        result=subprocess.run(argv,cwd=ROOT,capture_output=True,timeout=180)
        (out/"stdout.txt").write_bytes(result.stdout);(out/"stderr.txt").write_bytes(result.stderr)
        if result.returncode:
            raise RuntimeError(f"{label}: {result.stdout.decode(errors='replace')} {result.stderr.decode(errors='replace')}\nRetained {out}")
        try:return json.loads(result.stdout)
        except ValueError:return {"output":result.stdout.decode(errors="replace"),"receipt":str(out)}

    def command(self,op,**fields):
        request={"op":op,"school":self.school,"actor":self.actor,**fields}
        if self.endpoint:
            endpoint=urllib.parse.urlparse(self.endpoint)
            if endpoint.scheme!="http" or endpoint.hostname not in ("127.0.0.1","localhost","::1") or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path!="/v1/command":
                raise RuntimeError("The current school transport supports loopback HTTP /v1/command only.")
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args,**kwargs):return None
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            payload=json.dumps(request).encode()
            if len(payload)>1048576:raise RuntimeError("School request exceeds the development transport bound")
            with opener.open(urllib.request.Request(self.endpoint,data=payload,headers={"Content-Type":"application/json"}),timeout=180) as response:
                raw=response.read(4*1048576+1)
            if len(raw)>4*1048576:raise RuntimeError("School response exceeds the panel display bound")
            reply=json.loads(raw)
        else:
            reply=self._run([sys.executable,str(ROOT/"scripts/school_transport.py"),"--binary",str(self.binary.resolve()),
                             str(self.school_root.resolve()),json.dumps(request)],label=op)
        if reply.get("ok") is not True:raise RuntimeError(str(reply.get("error","Lean authority returned no successful result")))
        return reply["result"]

    def curriculum_command(self,*args):
        return self._run([str(self.curriculum.resolve()),*map(str,args)],label="curriculum")

    def edited_unit(self,text):
        # Preserve the actual teacher text. The Lean decoder/validator decides
        # its meaning; there is no second hidden curriculum representation.
        path=ROOT/"build/school/panel-authoring"/(uuid.uuid4().hex+".json")
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding="utf-8")
        return path

    def bridge(self,action,course,revision,**fields):
        out=ROOT/"build/school/panel-bridge"/uuid.uuid4().hex
        args=[sys.executable,str(ROOT/"scripts/lemmasim_school.py"),action,
              "--school-root",str(self.school_root.resolve()),"--session-dir",str(self.session_dir.resolve()),
              "--work-dir",str(out),"--school-executable",str(self.binary.resolve()),"--school",self.school,
              "--actor",self.actor,"--course",str(course),"--revision",str(revision)]
        for key,value in fields.items():
            if isinstance(value,bool):
                if value:args += ["--"+key.replace("_","-")]
            elif value is not None:args += ["--"+key.replace("_","-"),str(value)]
        if self.endpoint:args += ["--school-endpoint",self.endpoint]
        result=self._run(args,label="actual guest "+action)
        return {"transport":result,"retained":str(out),
                "next":"Inspect actual guest acknowledgements and completed tablet pixels; transport admission alone is not visible delivery."}

    def machine(self,action):
        from lemmasim_session import request
        return request(self.session_dir.resolve(),{"action":action},timeout=120)

    def install_sample(self):
        from lemmasim_school import actual_session,send_package
        out=ROOT/"build/school/panel-samples"/uuid.uuid4().hex;out.mkdir(parents=True,exist_ok=False)
        package=out/"sample.lcp"
        compilation=self.curriculum_command("compile",SAMPLE,package)
        metadata,observed,_=actual_session(self.session_dir.resolve())
        delivered=send_package(self.session_dir.resolve(),observed,package.read_bytes(),uuid.uuid4().int%1000000000+1)
        delivered={"status":"RAW_SAMPLE_COMMAND_ADMITTED","guestIdentity":metadata["identity"],**delivered}
        (out/"delivery.json").write_text(json.dumps(delivered,indent=2)+"\n")
        return {"compiled":compilation,"transport":delivered,"retained":str(out),
                "next":"Resume until actual 4b1 installation succeeds, then COURSE and LOAD package1/edition1. Admission alone is not visible delivery."}


class Panel:
    def __init__(self,window,args):
        import tkinter as tk
        from tkinter import ttk
        from tkinter.scrolledtext import ScrolledText
        self.tk=tk;self.ttk=ttk;self.window=window;self.args=args
        self.messages=queue.Queue();self.busy=False
        self.service=None
        window.title("LemmaSim · School workspace");window.geometry("1080x850")
        style=ttk.Style(window);style.theme_use("clam")
        style.configure("TButton",padding=7);style.configure("TLabel",font=("sans",11))
        shell=ttk.Frame(window,padding=16);shell.pack(fill="both",expand=True)
        ttk.Label(shell,text="Your school workspace",font=("sans",22,"bold")).pack(anchor="w")
        ttk.Label(shell,text="Study, teach, operate and develop with one identity. The Lean school checks every action.").pack(anchor="w",pady=(3,12))
        settings=ttk.Frame(shell);settings.pack(fill="x")
        self.values={}
        for i,(key,label,value) in enumerate([("school","School",args.school),("actor","Identity",args.actor),
                    ("course","Course","1"),("revision","Revision","1")]):
            ttk.Label(settings,text=label).grid(row=0,column=i*2,sticky="w",padx=(0,5))
            variable=tk.StringVar(value=value);self.values[key]=variable
            ttk.Entry(settings,textvariable=variable,width=18 if i<2 else 7).grid(row=0,column=i*2+1,sticky="ew",padx=(0,12))
        ttk.Label(shell,text=f"School storage: {args.school_root}\nTablet session: {args.session_dir}",foreground="#445465").pack(anchor="w",pady=10)
        endpoint=ttk.Frame(shell);endpoint.pack(fill="x",pady=(0,8))
        self.endpoint=self.tk.StringVar(value=args.school_endpoint or "")
        ttk.Label(endpoint,text="Configured endpoint (blank uses local commands)").pack(side="left",padx=(0,8))
        ttk.Entry(endpoint,textvariable=self.endpoint,width=55).pack(side="left",fill="x",expand=True)
        machine=ttk.Frame(shell);machine.pack(fill="x",pady=(0,12))
        for label,action in [("Pause tablet","pause"),("Resume tablet","resume"),("Inspect tablet","inspect")]:
            ttk.Button(machine,text=label,command=lambda a=action:self.machine(a)).pack(side="left",padx=(0,8))
        ttk.Button(machine,text="Open drawing window",command=self.open_tablet).pack(side="left")
        tabs=ttk.Notebook(shell)
        def page(title):
            outer=ttk.Frame(tabs);tabs.add(outer,text=title)
            canvas=tk.Canvas(outer,highlightthickness=0,height=320)
            scroll=ttk.Scrollbar(outer,orient="vertical",command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set)
            scroll.pack(side="right",fill="y");canvas.pack(side="left",fill="both",expand=True)
            frame=ttk.Frame(canvas,padding=14);item=canvas.create_window((0,0),window=frame,anchor="nw")
            frame.bind("<Configure>",lambda event:canvas.configure(scrollregion=canvas.bbox("all")))
            canvas.bind("<Configure>",lambda event:canvas.itemconfigure(item,width=event.width))
            return frame
        study=page("Study / join");teacher=page("Create / teach")
        operator=page("Run / customize");developer=page("Develop")
        self.study(study);self.teacher(teacher,ScrolledText);self.operator(operator);self.developer(developer)
        result_frame=ttk.Frame(shell);result_frame.pack(side="bottom",fill="x")
        ttk.Label(result_frame,text="Activity results and actionable diagnostics",font=("sans",11,"bold")).pack(anchor="w",pady=(12,4))
        self.output=ScrolledText(result_frame,height=6,wrap="word",font=("monospace",10));self.output.pack(fill="both")
        self.status=tk.StringVar(value="Ready · owner-local development transport")
        ttk.Label(result_frame,textvariable=self.status).pack(anchor="w",pady=(6,0))
        tabs.pack(fill="both",expand=True)
        window.after(100,self.poll)
        window.protocol("WM_DELETE_WINDOW",self.close)

    def connection(self):
        return Connection(self.args.school_root,self.args.session_dir,self.values["school"].get(),self.values["actor"].get(),
                          self.args.school_executable,self.args.curriculum_executable,self.endpoint.get().strip() or None)
    def close(self):
        if self.service and self.service.poll() is None:
            os.killpg(self.service.pid,signal.SIGTERM)
            try:self.service.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(self.service.pid,signal.SIGKILL);self.service.wait(timeout=3)
        self.window.destroy()
    def identity(self):return int(self.values["course"].get()),int(self.values["revision"].get())
    def run(self,label,work,on_success=None):
        if self.busy:self.status.set("An activity is still running; its result will appear below.");return
        self.busy=True;self.status.set(label+"…")
        def execute():
            try:self.messages.put((label,True,work(),on_success))
            except Exception as error:self.messages.put((label,False,str(error),None))
        threading.Thread(target=execute,daemon=True).start()
    def poll(self):
        try:
            while True:
                label,ok,result,on_success=self.messages.get_nowait();self.busy=False
                if ok and on_success:on_success(result)
                self.output.insert("end",label+(" · completed\n" if ok else " · rejected / unavailable\n")+
                                   (json.dumps(result,indent=2,ensure_ascii=False) if isinstance(result,(dict,list)) else str(result))+"\n\n")
                self.output.see("end");self.status.set("Ready" if ok else "Read the diagnostic above and retry after correcting it.")
        except queue.Empty:pass
        self.window.after(100,self.poll)
    def machine(self,action):
        connection=self.connection();self.run("Tablet "+action,lambda:connection.machine(action))
    def open_tablet(self):
        subprocess.Popen([sys.executable,str(ROOT/"scripts/lemmasim_session.py"),"view",str(self.args.session_dir.resolve())],cwd=ROOT)
    def school_action(self,op,**fields):
        connection=self.connection();self.run(op,lambda:connection.command(op,**fields))
    def study(self,frame):
        ttk=self.ttk
        ttk.Label(frame,text="Open a published course on the real tablet",font=("sans",15,"bold")).pack(anchor="w")
        ttk.Label(frame,text="Pause before install/help. Resume to let the guest process bytes, then use its COURSE and LOAD controls.",wraplength=950).pack(anchor="w",pady=8)
        ttk.Button(frame,text="Install local sample · no account",command=self.install_sample).pack(anchor="w",pady=(0,8))
        row=ttk.Frame(frame);row.pack(fill="x")
        ttk.Button(row,text="Join course",command=self.enroll).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Install publication",command=lambda:self.bridge("install")).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Bind current ASK session",command=lambda:self.bridge("join")).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Permitted help",command=lambda:self.bridge("help")).pack(side="left")
        ttk.Button(frame,text="My progress and due reviews",command=lambda:self.school_action("progress")).pack(anchor="w",pady=8)
        ttk.Label(frame,text="Submit after completing the guest checker; explicit typed values stay separate from drawing.").pack(anchor="w",pady=(8,3))
        self.attempt=self.tk.StringVar(value="attempt-1");self.coefficients=self.tk.StringVar(value="[0,1,1,2,1]")
        entries=ttk.Frame(frame);entries.pack(fill="x")
        ttk.Entry(entries,textvariable=self.attempt,width=22).pack(side="left",padx=(0,8))
        ttk.Entry(entries,textvariable=self.coefficients,width=36).pack(side="left",padx=(0,8))
        ttk.Button(entries,text="Record explicit submission",command=self.submit).pack(side="left")
        self.review_id=self.tk.StringVar(value="")
        reviews=ttk.Frame(frame);reviews.pack(fill="x",pady=12)
        ttk.Label(reviews,text="Due review ID").pack(side="left",padx=(0,8));ttk.Entry(reviews,textvariable=self.review_id,width=35).pack(side="left",padx=(0,8))
        ttk.Button(reviews,text="Open original due publication",command=lambda:self.bridge("review",review_id=self.review_id.get())).pack(side="left")
        self.activity=self.tk.StringVar(value="coefficients");self.task_id=self.tk.StringVar(value="4")
        self.teacher_review=self.tk.BooleanVar(value=False);self.work_artifact=self.tk.StringVar(value="")
        work=ttk.Frame(frame);work.pack(fill="x",pady=(4,8))
        ttk.Label(work,text="Activity / guest task").pack(side="left",padx=(0,8))
        ttk.Entry(work,textvariable=self.activity,width=20).pack(side="left",padx=(0,8))
        ttk.Entry(work,textvariable=self.task_id,width=5).pack(side="left",padx=(0,8))
        ttk.Checkbutton(work,text="Explicit work for teacher review",variable=self.teacher_review).pack(side="left")
        artifact=ttk.Frame(frame);artifact.pack(fill="x")
        ttk.Label(artifact,text="Written work artifact").pack(side="left",padx=(0,8))
        ttk.Entry(artifact,textvariable=self.work_artifact,width=60).pack(side="left",padx=(0,8))
        ttk.Button(artifact,text="Choose file",command=self.choose_work).pack(side="left")
        ttk.Label(frame,text="Teacher-review work stays unverified and separate from exact guest checking. The school checks the selected activity and assessment policy.",wraplength=950).pack(anchor="w",pady=8)
        choices=ttk.LabelFrame(frame,text="My goals, challenges and permitted recommendation overrides",padding=10)
        choices.pack(fill="x",pady=(10,4));self.choice_frame=choices
        self.choice_kind=self.tk.StringVar(value="suggestion");self.choice_reference=self.tk.StringVar(value="")
        self.choice_id=self.tk.StringVar(value="choice-1");self.choice_policy=self.tk.StringVar(value="1")
        self.choice_reason=self.tk.StringVar(value="");self.choice_goal=self.tk.StringVar(value="")
        reference=ttk.Frame(choices);reference.pack(fill="x")
        ttk.Label(reference,text="Original kind / key").pack(side="left",padx=(0,8))
        ttk.Combobox(reference,textvariable=self.choice_kind,values=("attempt","suggestion"),state="readonly",width=12).pack(side="left",padx=(0,8))
        ttk.Entry(reference,textvariable=self.choice_reference,width=48).pack(side="left",fill="x",expand=True)
        identity=ttk.Frame(choices);identity.pack(fill="x",pady=6)
        ttk.Label(identity,text="Request ID").pack(side="left",padx=(0,8))
        ttk.Entry(identity,textvariable=self.choice_id,width=32).pack(side="left",padx=(0,12))
        ttk.Label(identity,text="Policy version").pack(side="left",padx=(0,8))
        ttk.Entry(identity,textvariable=self.choice_policy,width=8).pack(side="left")
        for label,variable in (("Reason",self.choice_reason),("New goal",self.choice_goal)):
            row=ttk.Frame(choices);row.pack(fill="x",pady=3)
            ttk.Label(row,text=label,width=12).pack(side="left")
            ttk.Entry(row,textvariable=variable,width=75).pack(side="left",fill="x",expand=True)
        buttons=ttk.Frame(choices);buttons.pack(fill="x",pady=6)
        for label,op in (("Set goal","goal-set"),("Challenge interpretation","interpretation-challenge"),("Override suggestion","suggestion-override")):
            ttk.Button(buttons,text=label,command=lambda action=op:self.learner_choice(action)).pack(side="left",padx=(0,8))
        ttk.Button(buttons,text="Choice history",command=lambda:self.school_action("learner-choices")).pack(side="left")
        ttk.Label(choices,text="Copy the original key from progress or a suggestion. Your declaration retains its evidence; Lean checks ownership, publication, policy and whether an override is permitted.",wraplength=900).pack(anchor="w")
    def learner_choice(self,op):
        connection=self.connection()
        course=self.values["course"].get();revision=self.values["revision"].get();policy=self.choice_policy.get()
        fields={"learner":self.values["actor"].get(),"id":self.choice_id.get(),"reason":self.choice_reason.get(),
                "referenceKind":self.choice_kind.get(),"reference":self.choice_reference.get()}
        if op=="goal-set":fields["newGoal"]=self.choice_goal.get()
        self.run(op,lambda:connection.command(op,course=int(course),revision=int(revision),policy=int(policy),**fields))
    def enroll(self):
        connection=self.connection();actor=self.values["actor"].get()
        course=self.values["course"].get();revision=self.values["revision"].get()
        self.run("Join course",lambda:connection.command("enroll",learner=actor,course=int(course),revision=int(revision)))
    def install_sample(self):
        connection=self.connection()
        self.run("Install local sample",connection.install_sample)
    def bridge(self,action,**fields):
        connection=self.connection();course=self.values["course"].get();revision=self.values["revision"].get()
        fields.setdefault("transaction",uuid.uuid4().int%1000000000+1)
        if self.args.controlled_now is not None:fields["now"]=self.args.controlled_now
        self.run("Actual guest "+action,lambda:connection.bridge(action,int(course),int(revision),**fields))
    def submit(self):
        self.bridge("submit",attempt=self.attempt.get(),activity=self.activity.get(),values=self.coefficients.get(),task_id=self.task_id.get(),
                    teacher_review=self.teacher_review.get(),work_artifact=self.work_artifact.get() if self.teacher_review.get() else None)
    def choose_work(self):
        from tkinter import filedialog
        path=filedialog.askopenfilename(title="Explicit written work for teacher review")
        if path:self.work_artifact.set(path)
    def teacher(self,frame,ScrolledText):
        ttk=self.ttk
        ttk.Label(frame,text="Edit the shared Lean authoring representation",font=("sans",15,"bold")).pack(anchor="w")
        ttk.Label(frame,text="Preview and publish use the same decoder and package compiler as the learner runtime.").pack(anchor="w",pady=8)
        row=ttk.Frame(frame);row.pack(fill="x")
        ttk.Button(row,text="Load sample unit 1/1",command=self.fixture).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Open unit JSON",command=self.open_unit).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Validate / preview",command=lambda:self.unit_action(False)).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Publish immutable revision",command=lambda:self.unit_action(True)).pack(side="left")
        catalogue=ttk.Frame(frame);catalogue.pack(fill="x",pady=(8,0))
        self.catalogue_key=self.tk.StringVar(value="my-topics");self.catalogue_revision=self.tk.StringVar(value="")
        self.catalogue_query=self.tk.StringVar(value="")
        ttk.Label(catalogue,text="Catalogue key").pack(side="left",padx=(0,5))
        ttk.Entry(catalogue,textvariable=self.catalogue_key,width=16).pack(side="left",padx=(0,8))
        ttk.Button(catalogue,text="Import source JSON",command=self.import_catalogue).pack(side="left")
        search=ttk.Frame(frame);search.pack(fill="x",pady=6)
        ttk.Entry(search,textvariable=self.catalogue_revision,width=40).pack(side="left",padx=(0,8))
        ttk.Entry(search,textvariable=self.catalogue_query,width=24).pack(side="left",padx=(0,8))
        ttk.Button(search,text="Search revision digest",command=self.search_catalogue).pack(side="left")
        learner=ttk.Frame(frame);learner.pack(fill="x",pady=(2,0))
        self.learner=self.tk.StringVar(value="")
        ttk.Label(learner,text="Authorized learner identity").pack(side="left",padx=(0,6))
        ttk.Entry(learner,textvariable=self.learner,width=22).pack(side="left",padx=(0,8))
        ttk.Button(learner,text="Inspect permitted progress",command=lambda:self.school_action("progress",learner=self.learner.get())).pack(side="left")
        self.editor=ScrolledText(frame,height=9,wrap="none",font=("monospace",10));self.editor.pack(fill="both",expand=True,pady=10)
        self.editor.insert("1.0","Load the sample or open a unit JSON file. Keep the definition's course/revision aligned with your selected publication.")
    def fixture(self):
        connection=self.connection()
        def display(value):
            self.editor.delete("1.0","end");self.editor.insert("1.0",json.dumps(value,indent=2,ensure_ascii=False))
        self.run("Load sample definition",lambda:json.loads(SAMPLE.read_text(encoding="utf-8")),display)
    def open_unit(self):
        from tkinter import filedialog
        name=filedialog.askopenfilename(title="Authoring unit JSON",filetypes=[("Unit JSON","*.json")])
        if name:self.editor.delete("1.0","end");self.editor.insert("1.0",Path(name).read_text(encoding="utf-8"))
    def unit_action(self,publish):
        connection=self.connection();text=self.editor.get("1.0","end-1c")
        def execute():
            path=connection.edited_unit(text)
            return connection.command("publish",path=str(path),policy=1) if publish else connection.curriculum_command("preview",path)
        self.run("Publish" if publish else "Validate and preview",execute)
    def import_catalogue(self):
        from tkinter import filedialog
        name=filedialog.askopenfilename(title="Catalogue source JSON",filetypes=[("JSON","*.json")])
        if name:
            connection=self.connection();key=self.catalogue_key.get()
            self.run("Import catalogue",lambda:connection.curriculum_command("catalogue","import",connection.school_root/"catalogue",key,name))
    def search_catalogue(self):
        connection=self.connection();key=self.catalogue_key.get();revision=self.catalogue_revision.get();query=self.catalogue_query.get()
        self.run("Search catalogue",lambda:connection.curriculum_command("catalogue","search",connection.school_root/"catalogue",key,revision,query,0,20))
    def operator(self,frame):
        ttk=self.ttk
        ttk.Label(frame,text="Operate your own local school",font=("sans",15,"bold")).pack(anchor="w")
        ttk.Label(frame,text="Choose storage with --school-root. Initialization requires a fresh location; existing work is preserved.",wraplength=950).pack(anchor="w",pady=8)
        self.budgets=self.tk.StringVar(value="{}")
        budget=ttk.Frame(frame);budget.pack(fill="x",pady=(0,8))
        ttk.Label(budget,text="Initial budgets JSON (Lean validates every bound)").pack(side="left",padx=(0,8))
        ttk.Entry(budget,textvariable=self.budgets,width=65).pack(side="left",fill="x",expand=True)
        row=ttk.Frame(frame);row.pack(fill="x")
        ttk.Button(row,text="Initialize local school",command=self.initialize).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Run local endpoint",command=self.start_server).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Status / budgets",command=lambda:self.school_action("status")).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Jobs",command=lambda:self.school_action("jobs")).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Reconcile local jobs",command=lambda:self.school_action("reconcile")).pack(side="left")
        self.export_path=self.tk.StringVar(value=str(ROOT/"build/school/choose-new-export-directory"))
        ttk.Label(frame,text="Export destination (must be new)").pack(anchor="w",pady=(14,3))
        ttk.Entry(frame,textvariable=self.export_path,width=95).pack(anchor="w")
        ttk.Button(frame,text="Create consistent authorized export",command=lambda:self.school_action("export",to=self.export_path.get())).pack(anchor="w",pady=8)
        ttk.Button(frame,text="Stop local authority",command=lambda:self.school_action("stop")).pack(anchor="w")
        self.copy_path=self.tk.StringVar(value=str(ROOT/"build/school/choose-fresh-school-directory"))
        self.copy_identity=self.tk.StringVar(value="my-school-fork")
        copies=ttk.Frame(frame);copies.pack(fill="x",pady=10)
        ttk.Entry(copies,textvariable=self.copy_path,width=52).pack(side="left",padx=(0,8))
        ttk.Entry(copies,textvariable=self.copy_identity,width=20).pack(side="left",padx=(0,8))
        ttk.Button(copies,text="Clone reusable definition",command=self.clone).pack(side="left")
        ttk.Button(frame,text="Restore export offline into that fresh location",command=self.restore).pack(anchor="w")
        ttk.Label(frame,text="Remote providers, replicated availability and protected student credentials remain outside this owner-local binding.",wraplength=950).pack(anchor="w",pady=12)
    def initialize(self):
        connection=self.connection();budgets=self.budgets.get();deployment=self.values["school"].get()+"-local"
        clock="controlled-ms" if self.args.controlled_now is not None else "monotonic-ms"
        self.run("Initialize local school",lambda:connection.command("init",deployment=deployment,provider="local",clockModel=clock,
                                                                     budgets=json.loads(budgets)))
    def start_server(self):
        if self.service and self.service.poll() is None:self.status.set("This panel's local endpoint is already running.");return
        connection=self.connection();out=ROOT/"build/school/panel-services"/uuid.uuid4().hex;out.mkdir(parents=True)
        log=(out/"service.log").open("wb")
        self.service=subprocess.Popen([sys.executable,str(ROOT/"scripts/school_transport.py"),"--binary",str(connection.binary.resolve()),
                    str(connection.school_root.resolve()),"run","--port",str(self.args.port)],cwd=ROOT,stdout=log,stderr=log,start_new_session=True)
        log.close();self.endpoint.set(f"http://127.0.0.1:{self.args.port}/v1/command")
        self.status.set(f"Local endpoint process started; use Status to observe readiness. Log: {out}")
    def clone(self):
        identity=self.copy_identity.get();self.school_action("clone",to=self.copy_path.get(),newSchool=identity,newDeployment=identity+"-local")
    def restore(self):
        connection=self.connection();destination=Path(self.copy_path.get());export=self.export_path.get()
        target=Connection(destination,connection.session_dir,connection.school,connection.actor,connection.binary,connection.curriculum)
        self.run("Offline restore",lambda:target.command("restore",**{"from":export},offline=True))
    def developer(self,frame):
        ttk=self.ttk
        ttk.Label(frame,text="Inspect, extend and check the maintained system",font=("sans",15,"bold")).pack(anchor="w")
        ttk.Label(frame,text="The unit/checker examples execute in Lean. Tablet controls use the actual guest and canonical device contract.",wraplength=950).pack(anchor="w",pady=8)
        for label,path in [("School contract",ROOT/"docs/contracts/008-school-cloud-v0.1.0.html"),
                           ("Authoring and source guide",ROOT/"docs/school-curriculum.html"),
                           ("Client transport and qualification",ROOT/"docs/school-client.html"),
                           ("Physical / simulator machine contract",ROOT/"LEMMA_MACHINE_CONTRACT.html")]:
            ttk.Button(frame,text=label,command=lambda p=path:webbrowser.open(p.as_uri())).pack(anchor="w",pady=3)
        connection=self.connection()
        ttk.Button(frame,text="Run maintained reference checker examples",command=lambda:self.run("Lean checker examples",lambda:connection.curriculum_command("fixture-checks"))).pack(anchor="w",pady=10)
        ttk.Label(frame,text="Source: Lemma/School/FixtureUnit.lean · Lemma/School/Authoring.lean · Lemma/School/Client.lean",wraplength=950).pack(anchor="w")


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir",type=Path,required=True);parser.add_argument("--school-root",type=Path,required=True)
    parser.add_argument("--school",required=True);parser.add_argument("--actor",required=True)
    parser.add_argument("--school-executable",type=Path,default=ROOT/".lake/build/bin/school")
    parser.add_argument("--curriculum-executable",type=Path,default=ROOT/".lake/build/bin/school-curriculum")
    parser.add_argument("--controlled-now",type=int,help="explicit controlled-ms fixture only")
    parser.add_argument("--school-endpoint",help="existing loopback HTTP /v1/command authority")
    parser.add_argument("--port",type=int,default=8790)
    parser.add_argument("--smoke-exit-ms",type=int,help=argparse.SUPPRESS)
    parser.add_argument("--headless-command",help="execute one actual Lean JSON command through the same panel transport")
    args=parser.parse_args(argv)
    if args.headless_command:
        request=json.loads(args.headless_command);op=request.pop("op")
        connection=Connection(args.school_root,args.session_dir,args.school,args.actor,args.school_executable,args.curriculum_executable,args.school_endpoint)
        print(json.dumps(connection.command(op,**request),indent=2));return 0
    import tkinter as tk
    window=tk.Tk();Panel(window,args)
    if args.smoke_exit_ms:window.after(args.smoke_exit_ms,window.destroy)
    window.mainloop();return 0

if __name__=="__main__":raise SystemExit(main())
