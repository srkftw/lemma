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


def review_photo_image(tk, preview):
    """Present the exact bounded Lean gray4 image through Tk's binary PGM reader."""
    packed = bytes.fromhex(preview['gray4Hex'])
    width, height, stride = preview['width'], preview['height'], preview['stride']
    if (width, height, stride) != (1650, 2200, 825) or len(packed) != stride * height:
        raise RuntimeError('Lean review image geometry differs')
    # Area reduction is presentation only. Nearest-neighbor subsampling can
    # erase an entire one-pixel horizontal/vertical stroke on the skipped row.
    pixels = bytearray()
    for y in range(0, height, 2):
        upper, lower = y * stride, (y + 1) * stride
        for x in range(stride):
            a, b = packed[upper + x], packed[lower + x]
            pixels.append(((a >> 4) + (a & 15) + (b >> 4) + (b & 15)) * 17 // 4)
    pgm = f'P5\n{width // 2} {height // 2}\n255\n'.encode() + pixels
    # Tk's PPM/PGM reader takes binary bytes. Base64 autodetection selects a
    # different decoder in supported Tk builds and fails before displaying ink.
    return tk.PhotoImage(data=pgm, format='PPM')

@dataclass
class Connection:
    school_root: Path
    session_dir: Path
    school: str
    actor: str
    binary: Path
    curriculum: Path
    endpoint: str | None = None
    credential: Path | None = None

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
        if self.credential and not self.endpoint:
            raise RuntimeError("A learner credential requires an explicit /v1/client endpoint")
        if self.endpoint:
            endpoint=urllib.parse.urlparse(self.endpoint)
            if endpoint.scheme!="http" or endpoint.hostname not in ("127.0.0.1","localhost","::1") or endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or endpoint.path!=("/v1/client" if self.credential else "/v1/command"):
                raise RuntimeError("The current school transport supports loopback HTTP /v1/command only.")
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args,**kwargs):return None
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
            payload=json.dumps(request).encode()
            if len(payload)>1048576:raise RuntimeError("School request exceeds the development transport bound")
            headers={"Content-Type":"application/json"}
            if self.credential:
                credential=json.loads(self.credential.read_text())
                if credential.get("schema")!="lemma-school-credential/1":raise RuntimeError("Unsupported learner credential")
                headers["Authorization"]="Bearer "+credential["token"]
            with opener.open(urllib.request.Request(self.endpoint,data=payload,headers=headers),timeout=180) as response:
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

    def service(self,operation,**fields):
        from lemmasim_session import request
        started=request(self.session_dir.resolve(),{'action':'school-service','operation':operation,**fields},timeout=10)
        if started.get('status')!='pending':return started
        import time
        deadline=time.monotonic()+40
        while time.monotonic()<deadline:
            time.sleep(.05)
            result=request(self.session_dir.resolve(),{'action':'school-service','operation':'poll','id':started['id']},timeout=10)
            if result['status']!='pending':
                if result['status']=='failed':raise RuntimeError(result['error'])
                return result['result']
        raise RuntimeError('Original school service40s poll deadline; inspect pending request '+started['id'])

    def bridge(self,action,course,revision,**fields):
        if self.credential:
            operation={'install':'install','join':'join','help':'help','submit':'submit','review':'review'}.get(action)
            if operation is None:raise RuntimeError('Unsupported ordinary school operation')
            payload={'course':course,'revision':revision} if operation=='install' else {'id':fields['review_id']} if operation=='review' else {}
            return self.service(operation,**payload)
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
        out=ROOT/"build/school/panel-samples"/uuid.uuid4().hex;out.mkdir(parents=True,exist_ok=False)
        package=out/"sample.lcp"
        compilation=self.curriculum_command("compile",SAMPLE,package)
        delivered=self.service('sample',hex=package.read_bytes().hex())
        (out/"delivery.json").write_text(json.dumps(delivered,indent=2)+"\n")
        return {"compiled":compilation,"transport":delivered,"retained":str(out),
                "next":"Wait for the guest installation receipt, then tap COURSE. The school guest opens the selected publication."}


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
                          self.args.school_executable,self.args.curriculum_executable,self.endpoint.get().strip() or None,getattr(self.args,"credential",None))
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
        ordinary=bool(getattr(self.args,'credential',None))
        text="Keep writing while the school connects. After installation, tap COURSE. Tap ASK on the paper, bind it here, then tap JOIN on the paper." if ordinary else "Owner-local diagnostics require Pause before install/help, then Resume. The account-free sample uses the ordinary live service."
        ttk.Label(frame,text=text,wraplength=950).pack(anchor="w",pady=8)
        ttk.Button(frame,text="Install local sample · no account",command=self.install_sample).pack(anchor="w",pady=(0,8))
        row=ttk.Frame(frame);row.pack(fill="x")
        ttk.Button(row,text="Join course",command=self.enroll).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Install publication",command=lambda:self.bridge("install")).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Bind current ASK session",command=lambda:self.bridge("join")).pack(side="left",padx=(0,8))
        ttk.Button(row,text="Permitted help",command=lambda:self.bridge("help")).pack(side="left")
        ttk.Button(frame,text="My progress and due reviews",command=lambda:self.school_action("progress")).pack(anchor="w",pady=8)
        courses=ttk.LabelFrame(frame,text="My enrolled publications",padding=8);courses.pack(fill="x",pady=6)
        self.course_cursor=0;self.course_rows=[]
        self.course_list=ttk.Treeview(courses,columns=("title","identity","edition"),show="headings",height=3)
        for key,label,width in (("title","Course title",520),("identity","Stable ID",100),("edition","Edition",80)):
            self.course_list.heading(key,text=label);self.course_list.column(key,width=width)
        self.course_list.pack(fill="x")
        controls=ttk.Frame(courses);controls.pack(fill="x")
        ttk.Button(controls,text="Refresh courses",command=lambda:self.browse_courses(True)).pack(side="left")
        ttk.Button(controls,text="Next page",command=lambda:self.browse_courses(False)).pack(side="left")
        ttk.Button(controls,text="Select publication",command=self.select_course).pack(side="left")
        ttk.Button(controls,text="Teacher feedback",command=self.feedback).pack(side="left")
        if getattr(self.args,"credential",None):
            ttk.Button(controls,text="Connect ordinary tablet school",command=self.connect_school).pack(side="left")
        ttk.Label(frame,text="Save your work, tap SEND on the paper, then send the committed guest queue. X cancels the local queue." if ordinary else "Diagnostic submission: explicit typed values stay separate from drawing.").pack(anchor="w",pady=(8,3))
        self.attempt=self.tk.StringVar(value="attempt-1");self.coefficients=self.tk.StringVar(value="[0,1,1,2,1]")
        entries=ttk.Frame(frame)
        if not ordinary:entries.pack(fill="x")
        ttk.Entry(entries,textvariable=self.attempt,width=22).pack(side="left",padx=(0,8))
        ttk.Entry(entries,textvariable=self.coefficients,width=36).pack(side="left",padx=(0,8))
        ttk.Button(entries,text="Record explicit submission",command=self.submit).pack(side="left")
        if ordinary:ttk.Button(frame,text="Send committed guest work",command=lambda:self.bridge('submit')).pack(anchor='w',pady=6)
        self.review_id=self.tk.StringVar(value="")
        reviews=ttk.Frame(frame)
        if not ordinary:reviews.pack(fill="x",pady=12)
        ttk.Label(reviews,text="Due review ID").pack(side="left",padx=(0,8));ttk.Entry(reviews,textvariable=self.review_id,width=35).pack(side="left",padx=(0,8))
        ttk.Button(reviews,text="Open original due publication",command=lambda:self.bridge("review",review_id=self.review_id.get())).pack(side="left")
        if ordinary:ttk.Button(frame,text="Choose a due review",command=self.due_reviews).pack(anchor='w',pady=6)
        self.activity=self.tk.StringVar(value="coefficients");self.task_id=self.tk.StringVar(value="4")
        self.teacher_review=self.tk.BooleanVar(value=False);self.work_artifact=self.tk.StringVar(value="")
        work=ttk.Frame(frame)
        if not ordinary:work.pack(fill="x",pady=(4,8))
        ttk.Label(work,text="Activity / guest task").pack(side="left",padx=(0,8))
        ttk.Entry(work,textvariable=self.activity,width=20).pack(side="left",padx=(0,8))
        ttk.Entry(work,textvariable=self.task_id,width=5).pack(side="left",padx=(0,8))
        ttk.Checkbutton(work,text="Explicit work for teacher review",variable=self.teacher_review).pack(side="left")
        artifact=ttk.Frame(frame)
        if not ordinary:artifact.pack(fill="x")
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
                    teacher_review=self.teacher_review.get(),work_artifact=self.work_artifact.get() if self.teacher_review.get() else None,
                    review_id=self.review_id.get() or None)
    def connect_school(self):
        connection=self.connection()
        self.run('Connect ordinary tablet school',lambda:connection.service('connect',credential=str(connection.credential.resolve())))

    def browse_courses(self,reset):
        connection=self.connection();cursor=0 if reset else self.course_cursor
        def display(result):
            self.course_cursor=result["next"];self.course_rows=result["courses"]
            self.course_list.delete(*self.course_list.get_children())
            for i,row in enumerate(self.course_rows):
                self.course_list.insert("","end",iid=str(i),values=(row["title"],row["course"],row["revision"]))
        self.run("Browse enrolled publications",lambda:connection.command("course-catalogue",after=cursor,limit=20),display)
    def select_course(self):
        selection=self.course_list.selection()
        if selection:
            row=self.course_rows[int(selection[0])]
            self.values["course"].set(str(row["course"]));self.values["revision"].set(str(row["revision"]))
            self.status.set("Selected "+row["title"]+" · use Install publication to transfer its exact bytes")
    def feedback(self):
        connection=self.connection()
        def display(result):
            from tkinter.scrolledtext import ScrolledText
            window=self.tk.Toplevel(self.window);window.title("Teacher feedback · original work retained")
            text=ScrolledText(window,width=100,height=26,wrap="word");text.pack(fill="both",expand=True)
            text.insert("end",json.dumps(result,indent=2,ensure_ascii=False));text.configure(state="disabled")
        self.run("Teacher feedback",lambda:connection.command("feedback",limit=50),display)
    def due_reviews(self):
        connection=self.connection()
        def display(result):
            window=self.tk.Toplevel(self.window);window.title('Due reviews · original task and edition')
            rows=result['reviews'];listing=self.ttk.Treeview(window,columns=('course','task','edition'),show='headings',height=10)
            for key,label in (('course','Course'),('task','Original task'),('edition','Edition')):listing.heading(key,text=label)
            listing.pack(fill='both',expand=True)
            for i,row in enumerate(rows):listing.insert('','end',iid=str(i),values=(row['courseTitle'],row['title'],str(row['course'])+'/'+str(row['edition'])))
            def open_selected():
                chosen=listing.selection()
                if not chosen:return
                row=rows[int(chosen[0])];self.review_id.set(row['id'])
                self.run('Open original review task',lambda:connection.service('review',id=row['id']))
            self.ttk.Button(window,text='Open selected original task',command=open_selected).pack(pady=6)
            if result.get('more'):self.ttk.Button(window,text='Next page',command=lambda:self.run('Due reviews',lambda:connection.service('reviews',after=result['next']),display)).pack(pady=6)
        self.run('Due reviews',lambda:connection.service('reviews',after=0),display)
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
        ttk.Button(row,text="Edit activity visually",command=self.activity_editor).pack(side="left",padx=8)
        publication=ttk.Frame(frame);publication.pack(fill="x",pady=(6,0))
        self.publication_policy=self.tk.StringVar(value="1")
        ttk.Label(publication,text="Publication policy version").pack(side="left",padx=(0,8))
        ttk.Entry(publication,textvariable=self.publication_policy,width=12).pack(side="left")
        ttk.Label(publication,text="Lean validates the version; older publications keep their original policy.").pack(side="left",padx=8)
        ttk.Button(frame,text='Preview published edition as learner on tablet',command=self.preview_learner).pack(anchor='w',pady=6)
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
        ttk.Button(learner,text="Review learner work",command=self.review_queue).pack(side="left")
        admission=ttk.Frame(frame);admission.pack(fill='x',pady=6)
        ttk.Button(admission,text='Create private learner invitation',command=self.invite_learner).pack(side='left',padx=(0,6))
        ttk.Button(admission,text='Enroll in selected edition',command=lambda:self.manage_enrollment(False)).pack(side='left',padx=(0,6))
        ttk.Button(admission,text='Revoke selected enrollment',command=lambda:self.manage_enrollment(True)).pack(side='left')
        self.token_hash=self.tk.StringVar(value='')
        revoke=ttk.Frame(frame);revoke.pack(fill='x',pady=6)
        ttk.Label(revoke,text='Pairing public SHA256').pack(side='left')
        ttk.Entry(revoke,textvariable=self.token_hash,width=65).pack(side='left',padx=6)
        ttk.Button(revoke,text='Revoke pairing',command=self.revoke_pairing).pack(side='left')
        self.editor=ScrolledText(frame,height=9,wrap="none",font=("monospace",10));self.editor.pack(fill="both",expand=True,pady=10)
        self.editor.insert("1.0","Load the sample or open a unit JSON file. Keep the definition's course/revision aligned with your selected publication.")
    def invite_learner(self):
        from tkinter import filedialog
        connection=self.connection();learner=self.learner.get()
        if not connection.credential:self.status.set('Choose the explicitly admitted teacher pairing for invitation administration.');return
        destination=filedialog.asksaveasfilename(parent=self.window,title='New private learner invitation',defaultextension='.json')
        if not destination:return
        self.run('Create private learner invitation',lambda:connection._run([sys.executable,str(ROOT/'scripts/school_transport.py'),'--binary',str(connection.binary.resolve()),str(connection.school_root.resolve()),'pair','--credential',str(connection.credential.resolve()),'--learner',learner,'--to',destination],label='Admitted teacher invitation'),
                 lambda result:self.token_hash.set(result.get('result',result).get('tokenHash','')))
    def revoke_pairing(self):
        connection=self.connection();digest=self.token_hash.get()
        self.run('Revoke pairing',lambda:connection.command('admission-revoke',tokenHash=digest))
    def manage_enrollment(self,revoke):
        connection=self.connection();learner=self.learner.get()
        course=int(self.values['course'].get());edition=int(self.values['revision'].get())
        self.run('Revoke enrollment' if revoke else 'Enroll learner',lambda:connection.command('enrollment-revoke' if revoke else 'enroll',learner=learner,course=course,revision=edition))
    def activity_editor(self):
        from tkinter.scrolledtext import ScrolledText
        try:unit=json.loads(self.editor.get("1.0","end-1c"))
        except ValueError as error:self.status.set("Open a unit first: "+str(error));return
        window=self.tk.Toplevel(self.window);window.title("Edit shared unit activities");window.geometry("1000x880")
        selected=self.tk.StringVar(value=unit["activities"][0]["id"])
        selector=self.ttk.Combobox(window,textvariable=selected,values=[a["id"] for a in unit["activities"]],state="readonly")
        selector.pack(fill="x",padx=12,pady=8)
        variables={};texts={}
        for key,label,options in (("title","Title",None),("sourceAnchor","Source anchor",[a["id"] for a in unit["anchors"]]),
                ("kind","Activity",["preparation","definition","routine","invalidArgument","independentReasoning","transfer","review"]),
                ("goal","Supported goal",["unsupported","binomialSquare","fractionAddition"]),
                ("assistance","Assistance",["none","hint","worked"]),
                ("checker","Checker",["teacher-review/1","lemma-exact/1:binomialSquare","lemma-exact/1:fractionAddition"]),
                ("prerequisites","Prerequisite activity IDs (comma separated)",None)):
            row=self.ttk.Frame(window);row.pack(fill="x",padx=12,pady=2)
            self.ttk.Label(row,text=label,width=42).pack(side="left")
            value=self.tk.StringVar();variables[key]=value
            widget=self.ttk.Combobox(row,textvariable=value,values=options,state="readonly") if options else self.ttk.Entry(row,textvariable=value)
            widget.pack(side="left",fill="x",expand=True)
        independent=self.tk.BooleanVar()
        self.ttk.Checkbutton(window,text="Independent assessment (Lean rejects public hints or worked answers)",variable=independent).pack(anchor="w",padx=12)
        for key,label in (("body","Content / prompt"),("exercise","Requested work"),("hint","Authored hint"),("worked","Worked content"),("criteria","Rubric criteria (one per line)")):
            row=self.ttk.Frame(window);row.pack(fill="x",padx=12,pady=2)
            self.ttk.Label(row,text=label,width=23).pack(side="left",anchor="n")
            text=ScrolledText(row,height=3,wrap="word");text.pack(side="left",fill="x",expand=True);texts[key]=text
        review=self.tk.StringVar(value=str(unit["review"]["delaySeconds"]))
        row=self.ttk.Frame(window);row.pack(fill="x",padx=12,pady=4)
        self.ttk.Label(row,text="Later review delay (seconds)").pack(side="left")
        self.ttk.Entry(row,textvariable=review,width=12).pack(side="left",padx=12)
        def load(_event=None):
            activity=next(a for a in unit["activities"] if a["id"]==selected.get());node=unit["course"]["nodes"][activity["node"]]
            for key,value in variables.items():
                if key in ("title","sourceAnchor"):value.set(node[key])
                elif key=="checker":value.set(activity["assessment"][key])
                elif key=="prerequisites":value.set(", ".join(a["id"] for a in unit["activities"] if a["node"] in node["logicalPrerequisites"]))
                else:value.set(activity[key])
            independent.set(activity["assessment"]["independent"])
            for key,text in texts.items():
                text.delete("1.0","end");text.insert("1.0","\n".join(activity["assessment"]["criteria"]) if key=="criteria" else node[key])
        def apply():
            try:
                activity=next(a for a in unit["activities"] if a["id"]==selected.get());node=unit["course"]["nodes"][activity["node"]]
                prerequisites=[s.strip() for s in variables["prerequisites"].get().split(",") if s.strip()]
                by_id={a["id"]:a for a in unit["activities"]}
                node["logicalPrerequisites"]=[by_id[key]["node"] for key in prerequisites]
                unit["relations"]=[r for r in unit["relations"] if r["kind"]!="prerequisite" or r["toActivity"]!=activity["id"]]
                for key in prerequisites:unit["relations"].append(dict(fromActivity=key,toActivity=activity["id"],kind="prerequisite",origin="Teacher visual edit; validated with shared Lean authoring",reviewed=True,confidencePermille=None,reviewHistory=["Explicit prerequisite selected in teacher editor"]))
                for key in ("title","sourceAnchor"):node[key]=variables[key].get()
                for key in ("kind","goal","assistance"):activity[key]=variables[key].get()
                activity["assessment"]["checker"]=variables["checker"].get();activity["assessment"]["independent"]=independent.get()
                activity["assessment"]["criteria"]=texts["criteria"].get("1.0","end-1c").splitlines()
                for key in ("body","exercise","hint","worked"):node[key]=texts[key].get("1.0","end-1c")
                if isinstance(node["kind"],dict):node["kind"]={"exercise":{"goal":activity["goal"]}}
                unit["review"]["delaySeconds"]=int(review.get())
                self.editor.delete("1.0","end");self.editor.insert("1.0",json.dumps(unit,indent=2,ensure_ascii=False))
                self.status.set("Activity copied to shared definition · Validate / preview before publication")
            except (KeyError,ValueError) as error:self.status.set("Activity edit rejected: "+str(error))
        selector.bind("<<ComboboxSelected>>",load);load()
        self.ttk.Button(window,text="Apply activity to shared definition",command=apply).pack(pady=5)
        self.ttk.Label(window,text="Other supported fields remain in the JSON editor. Lean diagnoses unsupported constructs, cycles and incompatible checking or assistance.",wraplength=950).pack(padx=12)
    def preview_learner(self):
        connection=self.connection();text=self.editor.get('1.0','end-1c')
        if not connection.credential:self.status.set('Use the paired teacher client to preview a published edition through ordinary Study.');return
        def execute():
            unit=json.loads(text);path=connection.edited_unit(text)
            credential=json.loads(connection.credential.read_text())
            course=int(unit['course']['identity']);edition=int(unit['course']['edition'])
            out=ROOT/'build/school/panel-previews'/uuid.uuid4().hex;out.mkdir(parents=True)
            package=out/'preview.lcp';connection.curriculum_command('compile',path,package)
            connection.command('enroll',learner=credential['learner'],course=course,revision=edition)
            published=connection.command('client-course',course=course,revision=edition)
            import hashlib
            if hashlib.sha256(package.read_bytes()).hexdigest()!=published['artifact']:
                raise ValueError('The editor differs from this immutable publication. Publish a new edition before learner preview.')
            connection.service('connect',credential=str(connection.credential.resolve()))
            return connection.service('install',course=course,revision=edition)
        self.run('Enroll current teacher in published edition and preview on tablet',execute)
    def review_queue(self):
        connection=self.connection();learner=self.learner.get()
        def display(result):
            window=self.tk.Toplevel(self.window);window.title("Teacher review queue · "+learner)
            listing=self.ttk.Treeview(window,columns=("attempt","activity","checker"),show="headings",height=12)
            for key in ("attempt","activity","checker"):listing.heading(key,text=key.title())
            listing.pack(fill="both",expand=True,padx=12,pady=12)
            for row in result["attempts"]:
                listing.insert("","end",iid=row["key"],values=(row["key"],row["data"]["activity"],row["data"]["checker"]))
            def open_work():
                selected=listing.selection()
                if selected:self.open_review(connection,selected[0])
            self.ttk.Button(window,text="Open exact work, prompt and rubric",command=open_work).pack(pady=8)
        self.run("Pending learner work",lambda:connection.command("review-queue",learner=learner,limit=50),display)
    def open_review(self,connection,attempt):
        def load():
            result=connection.command("review-work",attempt=attempt)
            if result['attempt']['data'].get('guestEnvelope') is not None:
                result['inkPreview']=connection.command('review-render',attempt=attempt)
            elif result["workArtifact"] is not None:
                result["artifactBytes"]=connection.command("review-artifact",attempt=attempt)
            return result
        self.run("Open original learner work",load,lambda result:self.review_window(connection,attempt,result))
    def review_window(self,connection,attempt,result):
        from tkinter.scrolledtext import ScrolledText
        window=self.tk.Toplevel(self.window);window.title("Human review · "+attempt);window.geometry("1050x850")
        prompt=ScrolledText(window,height=15,wrap="word");prompt.pack(fill="both",expand=True,padx=10,pady=8)
        context={key:result[key] for key in ("attempt","prompt","rubric","sources","anchors","publication","assistance","assessments")}
        prompt.insert("end",json.dumps(context,indent=2,ensure_ascii=False));prompt.configure(state="disabled")
        preview=result.get('inkPreview')
        if preview:
            image=review_photo_image(self.tk,preview)
            paper=self.tk.Toplevel(window);paper.title('Original guest ink · hosted Lean raster preview')
            canvas=self.tk.Canvas(paper,width=840,height=680);scroll=self.ttk.Scrollbar(paper,orient='vertical',command=canvas.yview)
            canvas.configure(yscrollcommand=scroll.set);scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
            canvas.create_image(0,0,image=image,anchor='nw');canvas.image=image;canvas.configure(scrollregion=canvas.bbox('all'))
            self.ttk.Label(window,text='Exact artifact '+preview['digest']+' · document revision '+str(preview['documentRevision'])+' · hosted Lean raster preview').pack(padx=10)
        artifact=result.get("artifactBytes")
        if artifact:
            raw=bytes.fromhex(artifact["hex"])
            if raw.startswith(b"\x89PNG"):
                import base64
                picture=self.tk.PhotoImage(data=base64.b64encode(raw).decode())
                view=self.ttk.Label(window,image=picture);view.image=picture;view.pack()
            else:
                work=ScrolledText(window,height=6,wrap="word");work.pack(fill="x",padx=10)
                work.insert("end",raw[:262144].decode("utf-8",errors="replace"));work.configure(state="disabled")
                self.ttk.Label(window,text="Artifact SHA256: "+artifact["digest"]+" · "+str(len(raw))+" bytes").pack(anchor="w",padx=10)
        judgments=[]
        for criterion in result["rubric"]["criteria"]:
            row=self.ttk.Frame(window);row.pack(fill="x",padx=10,pady=2)
            self.ttk.Label(row,text=criterion,wraplength=780).pack(side="left",fill="x",expand=True)
            value=self.tk.StringVar(value="unclear");judgments.append(value)
            self.ttk.Combobox(row,textvariable=value,values=("met","not-met","unclear"),state="readonly",width=12).pack(side="right")
        comment=ScrolledText(window,height=4,wrap="word");comment.pack(fill="x",padx=10,pady=8)
        disposition=self.tk.StringVar(value="clarification")
        self.ttk.Combobox(window,textvariable=disposition,values=("accepted","needs-revision","clarification"),state="readonly").pack()
        previous=result["assessments"][-1] if result["assessments"] else None
        def commit():
            fields=dict(attempt=attempt,version=previous["data"]["version"]+1 if previous else 1,
                previousSequence=previous["sequence"] if previous else 0,disposition=disposition.get(),
                comment=comment.get("1.0","end-1c"),criteria=[value.get() for value in judgments])
            self.run("Append human assessment",lambda:connection.command("human-assess",**fields),lambda _:window.destroy())
        self.ttk.Button(window,text="Commit versioned human feedback",command=commit).pack(pady=8)
        self.ttk.Label(window,text="Human review preserves the original checker outcome. It does not certify a proof-kernel result.").pack(pady=4)
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
        connection=self.connection();text=self.editor.get("1.0","end-1c");policy=self.publication_policy.get()
        def execute():
            path=connection.edited_unit(text)
            return (connection.command("publish",definition=json.loads(text),policy=int(policy)) if connection.credential else connection.command("publish",path=str(path),policy=int(policy))) if publish else connection.curriculum_command("preview",path)
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
        if getattr(self.args,'credential',None):
            ttk.Label(frame,text='This paired client retains its scoped identity in every activity. Local authority filesystem operations require the operator launch with its owned storage directory. Changing tabs does not grant that authority.',wraplength=950).pack(anchor='w',pady=8)
            return
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


def open_study(parent,directory):
    """Ordinary live Study window; only bounded byte-service operations."""
    import tkinter as tk
    from tkinter import ttk,filedialog
    from tkinter.scrolledtext import ScrolledText
    directory=Path(directory).resolve()
    window=tk.Toplevel(parent);window.title('LemmaSim · Study');window.geometry('850x650')
    shell=ttk.Frame(window,padding=14);shell.pack(fill='both',expand=True)
    ttk.Label(shell,text='Study',font=('sans',20,'bold')).pack(anchor='w')
    ttk.Label(shell,text='Writing and Save stay on the paper. Sensors may stay off. Pairing grants only admitted school activities.',wraplength=800).pack(anchor='w',pady=8)
    connection=Connection(Path('.'),directory,'','',Path(),Path())
    output=ScrolledText(shell,height=8,wrap='word')
    pending=queue.Queue();busy=[False];generation=[0];cursor=[0];kind=['courses'];rows=[]
    listing=ttk.Treeview(shell,columns=('title','identity','task'),show='headings',height=8)
    for key,label,width in (('title','Course',360),('identity','Edition',100),('task','Task',280)):
        listing.heading(key,text=label);listing.column(key,width=width)
    def show(result):
        output.delete('1.0','end');output.insert('end',json.dumps(result,indent=2,ensure_ascii=False))
        for key in ('courses','reviews'):
            if key in result:
                kind[0]=key;rows[:]=result[key];cursor[0]=result['next'];listing.delete(*listing.get_children())
                for i,row in enumerate(rows):
                    listing.insert('','end',iid=str(i),values=(row.get('courseTitle',row.get('title','')),str(row['course'])+'/'+str(row.get('edition',row.get('revision'))),row.get('title','') if key=='reviews' else ''))
    def run(operation,**fields):
        if busy[0] and operation not in ('cancel','disconnect'):show({'status':'A school request is pending. Local pen and Save remain available.'});return
        generation[0]+=1;intent=generation[0]
        busy[0]=True
        def work():
            try:pending.put((intent,True,connection.service(operation,**fields)))
            except Exception as error:pending.put((intent,False,str(error)))
        threading.Thread(target=work,daemon=True).start()
    def poll():
        try:
            while True:
                intent,ok,result=pending.get_nowait()
                if intent==generation[0]:busy[0]=False;show(result if ok else {'error':result})
        except queue.Empty:pass
        if window.winfo_exists():window.after(50,poll)
    def pair():
        path=filedialog.askopenfilename(parent=window,title='Private school pairing file',filetypes=[('School pairing','*.json')])
        if path:run('connect',credential=path)
    def sample():
        try:
            metadata=json.loads((directory/'session.json').read_text());bundle=Path(metadata['identity']['native_bundle']['path'])
            manifest=json.loads((bundle/'bundle.json').read_text());item=manifest.get('sample_course')
            if not isinstance(item,dict) or not isinstance(item.get('path'),str):raise ValueError('This distribution has no inventoried local sample package')
            path=bundle/item['path']
            if path.resolve().parent!=bundle.resolve() or path.stat().st_size!=4199:raise ValueError('Invalid local sample artifact')
            import hashlib
            payload=path.read_bytes()
            if hashlib.sha256(payload).hexdigest()!=item['sha256']:raise ValueError('Local sample artifact identity differs')
            run('sample',hex=payload.hex())
        except Exception as error:show({'error':str(error)})
    top=ttk.Frame(shell);top.pack(fill='x',pady=8)
    for label,command in (('Local sample · no account',sample),('Choose pairing and connect',pair),('Courses',lambda:run('catalogue',after=0)),('Due reviews',lambda:run('reviews',after=0))):
        ttk.Button(top,text=label,command=command).pack(side='left',padx=(0,6))
    listing.pack(fill='x')
    def select():
        selected=listing.selection()
        if not selected:return
        row=rows[int(selected[0])]
        if kind[0]=='reviews':run('review',id=row['id'])
        else:run('install',course=row['course'],revision=row['revision'])
    controls=ttk.Frame(shell);controls.pack(fill='x',pady=8)
    ttk.Button(controls,text='Install / open selected task',command=select).pack(side='left')
    ttk.Button(controls,text='Next page',command=lambda:run('reviews' if kind[0]=='reviews' else 'catalogue',after=cursor[0])).pack(side='left')
    ttk.Label(shell,text='After installation tap COURSE. Tap ASK, bind it below, then tap JOIN on the paper. Save and tap SEND before sending committed work.',wraplength=800).pack(anchor='w',pady=8)
    actions=ttk.Frame(shell);actions.pack(fill='x')
    for label,operation in (('Bind ASK','join'),('Permitted help','help'),('Send committed work','submit'),('Feedback','feedback'),('Guest receipts','observation'),('Cancel help','cancel'),('Disconnect','disconnect')):
        ttk.Button(actions,text=label,command=lambda op=operation:run(op)).pack(side='left',padx=(0,4))
    output.pack(fill='both',expand=True,pady=8);show({'status':'Local paper is available. Choose the sample or your private school pairing.'});poll()


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-dir",type=Path,required=True);parser.add_argument("--school-root",type=Path,required=True)
    parser.add_argument("--school",required=True);parser.add_argument("--actor",required=True)
    parser.add_argument("--school-executable",type=Path,default=ROOT/".lake/build/bin/school")
    parser.add_argument("--curriculum-executable",type=Path,default=ROOT/".lake/build/bin/school-curriculum")
    parser.add_argument("--controlled-now",type=int,help="explicit controlled-ms fixture only")
    parser.add_argument("--school-endpoint",help="existing loopback HTTP /v1/command authority")
    parser.add_argument("--credential",type=Path,help="Local learner credential; only the bounded /v1/client admission is used")
    parser.add_argument("--port",type=int,default=8790)
    parser.add_argument("--smoke-exit-ms",type=int,help=argparse.SUPPRESS)
    parser.add_argument("--headless-command",help="execute one actual Lean JSON command through the same panel transport")
    args=parser.parse_args(argv)
    if args.headless_command:
        request=json.loads(args.headless_command);op=request.pop("op")
        connection=Connection(args.school_root,args.session_dir,args.school,args.actor,args.school_executable,args.curriculum_executable,args.school_endpoint,args.credential)
        print(json.dumps(connection.command(op,**request),indent=2));return 0
    import tkinter as tk
    window=tk.Tk();Panel(window,args)
    if args.smoke_exit_ms:window.after(args.smoke_exit_ms,window.destroy)
    window.mainloop();return 0

if __name__=="__main__":raise SystemExit(main())
