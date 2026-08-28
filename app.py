import customtkinter as ctk
from tkinter import filedialog, messagebox
import os, sys, ctypes, time
import engine
import config as cfg

def is_admin():
    try: return ctypes.windll.shell32.IsUserAnAdmin()
    except: return False

def elevate():
    ctypes.windll.shell32.ShellExecuteW(None,"runas",sys.executable," ".join(sys.argv),None,1)
    sys.exit()

if not is_admin():
    elevate()

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

ACCENT=    "#7C3AED"
ACCENT_H=  "#6D28D9"
CYAN=      "#06B6D4"
DANGER=    "#DC2626"
DANGER_H=  "#B91C1C"
SUCCESS=   "#10B981"
WARN=      "#F59E0B"
BG_MAIN=   "#0D1117"
BG_CARD=   "#111827"
BG_CARD2=  "#1F2937"
TEXT_MUTED="#6B7280"
TEXT_DIM=  "#9CA3AF"

def lbl(parent,text,size=13,color=None,bold=False,**kw):
    return ctk.CTkLabel(parent,text=text,
        font=("Segoe UI",size,"bold" if bold else "normal"),
        text_color=color or "white",**kw)

def entr(parent,ph="",secret=False,**kw):
    return ctk.CTkEntry(parent,placeholder_text=ph,
        show="*" if secret else "",
        fg_color=BG_CARD,border_color=ACCENT,border_width=1,
        corner_radius=8,font=("Segoe UI",13),**kw)

def btn(parent,text,cmd,color=None,hover=None,h=40,w=None,**kw):
    k=dict(text=text,command=cmd,fg_color=color or ACCENT,
           hover_color=hover or ACCENT_H,corner_radius=10,
           font=("Segoe UI",13,"bold"),height=h)
    if w: k["width"]=w
    k.update(kw)
    return ctk.CTkButton(parent,**k)

def sec_lbl(parent,text):
    ctk.CTkFrame(parent,height=1,fg_color=BG_CARD2).pack(fill="x",padx=12,pady=(10,3))
    lbl(parent,text,color=CYAN,size=10,bold=True).pack(anchor="w",padx=14,pady=(0,4))

def path_row(parent,var,ph,kind,browse_fn):
    row=ctk.CTkFrame(parent,fg_color="transparent")
    row.pack(fill="x",padx=12,pady=(0,4))
    entr(row,ph,textvariable=var).pack(side="left",fill="x",expand=True,padx=(0,8))
    btn(row,"Browse",lambda:browse_fn(var,kind),h=36,w=84).pack(side="right")


class PatternWidget(ctk.CTkFrame):
    DOT=20; GAP=60
    def __init__(self,master,on_complete=None,**kwargs):
        kwargs.setdefault("fg_color","transparent")
        super().__init__(master,**kwargs)
        self.on_complete=on_complete
        self._seq=[]; self._active=set(); self._centers={}
        sz=self.GAP*2+self.DOT*3+24
        self.cv=ctk.CTkCanvas(self,width=sz,height=sz,
            bg=BG_MAIN,highlightthickness=1,highlightbackground=ACCENT)
        self.cv.pack(padx=8,pady=8)
        self._render_dots()
        self.cv.bind("<ButtonPress-1>",self._start)
        self.cv.bind("<B1-Motion>",self._drag)
        self.cv.bind("<ButtonRelease-1>",self._release)

    def _pos(self,i):
        r,c=divmod(i,3)
        return 28+c*self.GAP,28+r*self.GAP

    def _render_dots(self):
        self.cv.delete("all")
        self._seq=[]; self._active=set()
        for i in range(9):
            x,y=self._pos(i); self._centers[i]=(x,y)
            R=self.DOT//2
            self.cv.create_oval(x-R,y-R,x+R,y+R,fill=BG_CARD2,outline=ACCENT,width=1.5,tags=f"d{i}")
            self.cv.create_text(x,y,text=str(i+1),fill=TEXT_MUTED,font=("Consolas",8))

    def _hit(self,x,y):
        for i,(cx,cy) in self._centers.items():
            if abs(x-cx)<self.DOT+4 and abs(y-cy)<self.DOT+4: return i
        return None

    def _activate(self,i):
        if i in self._active: return
        self._active.add(i); self._seq.append(i)
        x,y=self._centers[i]; R=self.DOT//2
        self.cv.create_oval(x-R,y-R,x+R,y+R,fill=ACCENT,outline=CYAN,width=2,tags=f"d{i}")
        self.cv.create_text(x,y,text=str(i+1),fill="white",font=("Consolas",8,"bold"))
        if len(self._seq)>1:
            px,py=self._centers[self._seq[-2]]
            self.cv.create_line(px,py,x,y,fill=CYAN,width=2,dash=(4,2))

    def _start(self,e):
        self._render_dots()
        d=self._hit(e.x,e.y)
        if d is not None: self._activate(d)

    def _drag(self,e):
        d=self._hit(e.x,e.y)
        if d is not None: self._activate(d)

    def _release(self,e):
        if len(self._seq)>=4 and self.on_complete:
            self.on_complete("".join(str(x) for x in self._seq))
        elif 0<len(self._seq)<4:
            self._render_dots()

    def reset(self): self._render_dots()
    def get_pattern(self): return "".join(str(x) for x in self._seq)


class MasterKeyOverlay(ctk.CTkToplevel):
    def __init__(self,master,on_success):
        super().__init__(master)
        self.title("PSVault — Session Expired")
        self.geometry("420x300")
        self.configure(fg_color=BG_MAIN)
        self.resizable(False,False)
        self.grab_set()
        self.on_success=on_success
        self._attempts=0
        lbl(self,"🔒 Session Expired",size=20,bold=True).pack(pady=(30,6))
        lbl(self,"6-hour session ended. Enter master key to continue.",color=TEXT_MUTED,size=12).pack(pady=(0,20))
        self.mk=entr(self,"PSV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX",secret=True)
        self.mk.pack(fill="x",padx=30)
        self.mk.bind("<Return>",lambda e:self._try())
        btn(self,"Unlock Session",self._try,h=42).pack(fill="x",padx=30,pady=14)
        self.st=lbl(self,"",size=12)
        self.st.pack()
        self.protocol("WM_DELETE_WINDOW",lambda:sys.exit(0))

    def _try(self):
        val=self.mk.get().strip()
        self._attempts+=1
        if cfg.verify_master_key(val):
            cfg.save_session()
            self.destroy()
            self.on_success()
        else:
            if self._attempts>=5:
                messagebox.showerror("Locked","Too many failed attempts.")
                sys.exit(0)
            self.st.configure(text=f"❌ Wrong master key ({self._attempts}/5)",text_color=DANGER)
            self.mk.delete(0,"end")


class FirstRunWindow(ctk.CTkToplevel):
    def __init__(self,master,on_done):
        super().__init__(master)
        self.title("PSVault — First Setup")
        self.geometry("460x520")
        self.configure(fg_color=BG_MAIN)
        self.resizable(False,False)
        self.grab_set()
        self.on_done=on_done
        self._mk=cfg.generate_master_key()
        cfg.save_master_key(self._mk)
        s=ctk.CTkScrollableFrame(self,fg_color="transparent")
        s.pack(fill="both",expand=True,padx=4,pady=4)
        lbl(s,"🔒 Welcome to PSVault",size=22,bold=True).pack(pady=(20,4))
        lbl(s,"A master key has been generated.\nWrite it down — required every 6 hours.",
            color=TEXT_MUTED,size=12,justify="center").pack(pady=(0,16))
        mk_card=ctk.CTkFrame(s,fg_color=BG_CARD2,corner_radius=10)
        mk_card.pack(fill="x",padx=16,pady=(0,6))
        lbl(mk_card,"YOUR MASTER KEY",color=CYAN,size=10,bold=True).pack(pady=(10,4))
        lbl(mk_card,self._mk,color=WARN,size=14,bold=True).pack(pady=(0,4))
        lbl(mk_card,"⚠  Write this down. It will not be shown again.",color=DANGER,size=11).pack(pady=(0,10))
        btn(s,"📋  Copy Master Key",self._copy,color=BG_CARD2,hover=BG_CARD,h=36).pack(fill="x",padx=16,pady=(0,12))
        ctk.CTkFrame(s,height=1,fg_color=BG_CARD2).pack(fill="x",padx=16,pady=6)
        lbl(s,"Type your master key below to confirm:",color=TEXT_MUTED,size=12).pack(pady=(6,2))
        self.conf=entr(s,"Type master key to confirm")
        self.conf.pack(fill="x",padx=16)
        self.st=lbl(s,"",size=12)
        self.st.pack(pady=4)
        btn(s,"✅  I've Saved It — Continue",self._confirm,h=44).pack(fill="x",padx=16,pady=12)

    def _copy(self):
        self.clipboard_clear(); self.clipboard_append(self._mk)
        self.st.configure(text="✅ Copied!",text_color=SUCCESS)

    def _confirm(self):
        if self.conf.get().strip()!=self._mk:
            self.st.configure(text="❌ Doesn't match. Check again.",text_color=DANGER)
            return
        cfg.save_session()
        self.destroy()
        self.on_done()


class SettingsWindow(ctk.CTkToplevel):
    def __init__(self,master):
        super().__init__(master)
        self.title("PSVault — Settings")
        self.geometry("480x680")
        self.configure(fg_color=BG_MAIN)
        self.resizable(False,False)
        self.grab_set()
        lbl(self,"⚙  Settings",size=20,bold=True).pack(pady=(20,2))
        lbl(self,"Manage credentials & master key",color=TEXT_MUTED).pack(pady=(0,10))
        self.tab=ctk.CTkTabview(self,width=450,fg_color=BG_CARD,
            segmented_button_fg_color=BG_CARD,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_H)
        self.tab.pack(padx=16,fill="both",expand=True)
        for t in ["🗝 Master Key","ℹ About"]:
            self.tab.add(t)
        self._mk_tab(); self._ab_tab()
        self.st=lbl(self,"",size=12)
        self.st.pack(pady=6)

   

    def _mk_tab(self):
        s=ctk.CTkScrollableFrame(self.tab.tab("🗝 Master Key"),fg_color="transparent")
        s.pack(fill="both",expand=True)
        lbl(s,"Change Master Key",size=14,bold=True).pack(pady=(16,4))
        lbl(s,"Enter current master key to set a new one.\nNew key unlocks the 6-hour session and all vaults.",
            color=TEXT_MUTED,size=12,justify="center").pack(pady=(0,14))
        lbl(s,"Current master key:",color=TEXT_MUTED,size=12).pack(anchor="w",padx=12,pady=(0,2))
        self.cur_mk=entr(s,"PSV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX",secret=True); self.cur_mk.pack(fill="x",padx=12)
        lbl(s,"New master key (blank = auto-generate):",color=TEXT_MUTED,size=12).pack(anchor="w",padx=12,pady=(10,2))
        self.new_mk=entr(s,"PSV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX"); self.new_mk.pack(fill="x",padx=12)
        btn(s,"🗝  Update Master Key",self._chg_mk).pack(padx=12,pady=16,fill="x")
        lbl(s,"⚠  Write down the new key immediately.",color=WARN,size=11,justify="center").pack(pady=8)

    def _ab_tab(self):
        s=ctk.CTkScrollableFrame(self.tab.tab("ℹ About"),fg_color="transparent")
        s.pack(fill="both",expand=True)
        for lb,val in [("App","PSVault Final"),("Encryption","AES-256-GCM"),
                       ("KDF","PBKDF2 · 480,000 iterations"),
                       ("Auth","Password · Pattern · Master Key"),
                       ("Session","6-hour master key unlock"),
                       ("Config",cfg.CONFIG_DIR),("Platform","Windows / Linux")]:
            row=ctk.CTkFrame(s,fg_color="transparent"); row.pack(fill="x",padx=12,pady=5)
            lbl(row,lb+":",color=TEXT_MUTED,size=12,width=100,anchor="w").pack(side="left")
            lbl(row,val,size=12,anchor="w",wraplength=280).pack(side="left")
        lbl(s,"⚠  Config is admin-protected & hidden.\nMaster key stored encrypted — never in code.",
            color=WARN,size=11,justify="center").pack(pady=14)

    def _set_st(self,msg,color="white"): self.st.configure(text=msg,text_color=color); self.update()

    

   

    def _chg_mk(self):
        cur=self.cur_mk.get().strip()
        if not cur: self._set_st("⚠ Enter current master key",WARN); return
        if not cfg.verify_master_key(cur): self._set_st("❌ Wrong master key",DANGER); return
        new=self.new_mk.get().strip() or cfg.generate_master_key()
        cfg.save_master_key(new); cfg.save_session()
        self.cur_mk.delete(0,"end"); self.new_mk.delete(0,"end")
        messagebox.showinfo("New Master Key — Save This!",
            f"Your new master key:\n\n{new}\n\nWrite this down now.")
        self._set_st("✅ Master key updated!",SUCCESS)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("PSVault")
        self.geometry("600x740")
        self.configure(fg_color=BG_MAIN)
        self.resizable(False,False)
        self._lock_pattern=""; self._lock_both_pattern=""; self._unlock_pattern=""
        self._session_check_id=None
        if not cfg.master_key_exists():
            self.withdraw()
            w=FirstRunWindow(self,self._after_setup)
            self.wait_window(w)
        else:
            if not cfg.session_valid():
                self.withdraw()
                self._ask_master_key()
            else:
                self._build_ui()
                self._start_session_timer()

    def _after_setup(self):
        self.deiconify(); self._build_ui(); self._start_session_timer()

    def _ask_master_key(self):
        w=MasterKeyOverlay(self,self._on_mk_success)
        self.wait_window(w)

    def _on_mk_success(self):
        self.deiconify(); self._build_ui(); self._start_session_timer()

    def _start_session_timer(self):
        if self._session_check_id: self.after_cancel(self._session_check_id)
        self._session_check_id=self.after(60000,self._check_session)

    def _check_session(self):
        if not cfg.session_valid():
            self.withdraw(); self._ask_master_key()
        else:
            if hasattr(self,"session_lbl"):
                self.session_lbl.configure(text=f"🕐 {cfg.session_remaining_str()}")
            self._start_session_timer()

    def _build_ui(self):
        for w in self.winfo_children(): w.destroy()
        hdr=ctk.CTkFrame(self,fg_color="transparent")
        hdr.pack(fill="x",padx=20,pady=(18,0))
        
        left=ctk.CTkFrame(hdr,fg_color="transparent"); left.pack(side="left")
        lbl(left,"🔒 PSVault",size=26,bold=True).pack(anchor="w")
        lbl(left,"AES-256 · Pattern · Master Key",color=TEXT_MUTED,size=11).pack(anchor="w")
        
        right=ctk.CTkFrame(hdr,fg_color="transparent"); right.pack(side="right")
        
        # --- ADDED LOCK BUTTON ---
        btn(right, "🔒 Lock App", self._lock_app_now, color=DANGER, hover=DANGER_H, h=32, w=110).pack(pady=(0,4))
        # -------------------------
        
        btn(right,"⚙ Settings",lambda:SettingsWindow(self),color=BG_CARD2,hover=BG_CARD,h=32,w=110).pack(pady=(0,4))
        self.session_lbl=lbl(right,f"🕐 {cfg.session_remaining_str()}",color=CYAN,size=10)
        self.session_lbl.pack()
        ctk.CTkFrame(self,height=2,fg_color=ACCENT).pack(fill="x",padx=20,pady=(10,4))
        self.tab=ctk.CTkTabview(self,fg_color=BG_CARD,
            segmented_button_fg_color=BG_CARD,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_H,
            corner_radius=12)
        self.tab.pack(padx=16,fill="both",expand=True,pady=(0,4))
        for t in ["🏠  Home","🔒  Lock","🔓  Unlock","🛡  Win Lock"]:
            self.tab.add(t)
        self._home_tab(); self._lock_tab(); self._unlock_tab(); self._winlock_tab()
        sb=ctk.CTkFrame(self,fg_color=BG_CARD,corner_radius=8)
        sb.pack(fill="x",padx=16,pady=(0,10))
        self.st_var=ctk.StringVar(value="Ready")
        self.st_lbl=ctk.CTkLabel(sb,textvariable=self.st_var,
            font=("Consolas",12),text_color=TEXT_DIM)
        self.st_lbl.pack(pady=5,padx=12,anchor="w")

    def _home_tab(self):
        outer=self.tab.tab("🏠  Home")
        s=ctk.CTkScrollableFrame(outer,fg_color="transparent")
        s.pack(fill="both",expand=True)
        history=cfg.load_history()
        vaults=sum(1 for h in history if h.get("type")=="vault_lock")
        winlocks=sum(1 for h in history if h.get("type")=="win_lock")
        unlocks=sum(1 for h in history if h.get("type")=="vault_unlock")
        stats=ctk.CTkFrame(s,fg_color="transparent")
        stats.pack(fill="x",padx=10,pady=(12,6))
        for icon,count,label,color in [
            ("🔒",vaults,"Vaults Created",ACCENT),
            ("🛡",winlocks,"Win Locks",CYAN),
            ("🔓",unlocks,"Unlocked",SUCCESS)]:
            card=ctk.CTkFrame(stats,fg_color=BG_CARD2,corner_radius=10)
            card.pack(side="left",expand=True,fill="x",padx=5)
            lbl(card,icon,size=22).pack(pady=(10,0))
            lbl(card,str(count),size=22,bold=True,color=color).pack()
            lbl(card,label,color=TEXT_MUTED,size=11).pack(pady=(0,10))
        sk=ctk.CTkFrame(s,fg_color=BG_CARD2,corner_radius=10)
        sk.pack(fill="x",padx=10,pady=6)
        sr=ctk.CTkFrame(sk,fg_color="transparent"); sr.pack(fill="x",padx=14,pady=10)
        lbl(sr,"🕐 Session",bold=True).pack(side="left")
        lbl(sr,f"{cfg.session_remaining_str()} remaining",color=CYAN,size=12).pack(side="right")
        lbl(sk,"Every 6 hours, master key required to continue.",color=TEXT_MUTED,size=11).pack(pady=(0,10))
        sec_lbl(s,"RECENT ACTIVITY")
        if not history:
            lbl(s,"No activity yet. Lock a folder to get started.",color=TEXT_MUTED,size=12).pack(pady=20)
        else:
            for h in history[:15]: self._history_card(s,h)
        btn(s,"🔄  Refresh",self._refresh_home,color=BG_CARD2,hover=BG_CARD,h=34).pack(padx=10,pady=10,fill="x")

    def _history_card(self,parent,h):
        t=h.get("type","")
        if t=="vault_lock": icon,color,title,sub="🔒",ACCENT,f"Locked: {h.get('folder_name','?')}",f"{h.get('locked_at','?')}  ·  {h.get('auth','?')}"
        elif t=="vault_unlock": icon,color,title,sub="🔓",SUCCESS,f"Unlocked: {h.get('folder_name','?')}",h.get("unlocked_at","?")
        elif t=="win_lock": icon,color,title,sub="🛡",CYAN,f"Win Lock: {h.get('folder_name','?')}",h.get("locked_at","?")
        else: return
        card=ctk.CTkFrame(parent,fg_color=BG_CARD2,corner_radius=8)
        card.pack(fill="x",padx=10,pady=3)
        row=ctk.CTkFrame(card,fg_color="transparent"); row.pack(fill="x",padx=12,pady=8)
        lbl(row,icon,size=18).pack(side="left",padx=(0,10))
        info=ctk.CTkFrame(row,fg_color="transparent"); info.pack(side="left",fill="x",expand=True)
        lbl(info,title,size=12,bold=True,color=color).pack(anchor="w")
        lbl(info,sub,size=11,color=TEXT_MUTED).pack(anchor="w")

    def _refresh_home(self):
        tab=self.tab.tab("🏠  Home")
        for w in tab.winfo_children(): w.destroy()
        self._home_tab()

    def _lock_tab(self):
        outer=self.tab.tab("🔒  Lock")
        s=ctk.CTkScrollableFrame(outer,fg_color="transparent")
        s.pack(fill="both",expand=True)
        self.lock_path=ctk.StringVar(); self.vault_dir=ctk.StringVar()
        sec_lbl(s,"FOLDER"); path_row(s,self.lock_path,"Select folder to protect...","folder",self._browse)
        sec_lbl(s,"VAULT DESTINATION  (optional)"); path_row(s,self.vault_dir,"Default = same as folder","folder",self._browse)
        sec_lbl(s,"AUTHENTICATION")
        self.lock_auth=ctk.CTkTabview(s,height=220,fg_color=BG_MAIN,
            segmented_button_fg_color=BG_MAIN,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_H)
        self.lock_auth.pack(fill="x",padx=8,pady=4)
        for t in ["Password","Pattern","Both"]: self.lock_auth.add(t)
        pt=self.lock_auth.tab("Password")
        self.lp1=entr(pt,"Password (min 6 chars)",secret=True); self.lp1.pack(fill="x",padx=8,pady=(16,6))
        self.lp2=entr(pt,"Confirm password",secret=True); self.lp2.pack(fill="x",padx=8)
        pp=self.lock_auth.tab("Pattern")
        self.lpw=PatternWidget(pp,on_complete=self._on_lp); self.lpw.pack()
        self.lpl=lbl(pp,"Draw pattern (min 4 dots)",color=TEXT_MUTED,size=11); self.lpl.pack()
        pb=self.lock_auth.tab("Both")
        pb_s=ctk.CTkScrollableFrame(pb,fg_color="transparent"); pb_s.pack(fill="both",expand=True)
        self.lb1=entr(pb_s,"Password",secret=True); self.lb1.pack(fill="x",padx=8,pady=(10,4))
        self.lb2=entr(pb_s,"Confirm password",secret=True); self.lb2.pack(fill="x",padx=8,pady=(0,6))
        self.lbw=PatternWidget(pb_s,on_complete=self._on_lbp); self.lbw.pack()
        self.lbl2=lbl(pb_s,"Also draw pattern",color=TEXT_MUTED,size=11); self.lbl2.pack()
        sec_lbl(s,"OPTIONS")
        self.del_var=ctk.BooleanVar(value=False)
        self.mk_reminder_var=ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(s,text="Delete original folder after locking",variable=self.del_var,
            fg_color=ACCENT,hover_color=ACCENT_H,font=("Segoe UI",12)).pack(anchor="w",padx=12,pady=2)
        ctk.CTkCheckBox(s,text="Show master key reminder after lock",variable=self.mk_reminder_var,
            fg_color=ACCENT,hover_color=ACCENT_H,font=("Segoe UI",12)).pack(anchor="w",padx=12,pady=2)
        btn(s,"🔒   Lock Folder",self._do_lock,h=44).pack(padx=12,pady=14,fill="x")

    def _on_lp(self,p): self._lock_pattern=p; self.lpl.configure(text=f"✅ Pattern set ({len(p)} dots)",text_color=CYAN)
    def _on_lbp(self,p): self._lock_both_pattern=p; self.lbl2.configure(text=f"✅ Pattern set ({len(p)} dots)",text_color=CYAN)

    def _unlock_tab(self):
        outer=self.tab.tab("🔓  Unlock")
        s=ctk.CTkScrollableFrame(outer,fg_color="transparent")
        s.pack(fill="both",expand=True)
        self.vault_path=ctk.StringVar(); self.out_path=ctk.StringVar()
        sec_lbl(s,"VAULT FILE"); path_row(s,self.vault_path,"Select .vault file...","vault",self._browse)
        sec_lbl(s,"RESTORE DESTINATION  (optional)"); path_row(s,self.out_path,"Default = same as vault","folder",self._browse)
        sec_lbl(s,"AUTHENTICATION")
        self.ul_auth=ctk.CTkTabview(s,height=200,fg_color=BG_MAIN,
            segmented_button_fg_color=BG_MAIN,
            segmented_button_selected_color=ACCENT,
            segmented_button_selected_hover_color=ACCENT_H)
        self.ul_auth.pack(fill="x",padx=8,pady=4)
        for t in ["Password","Pattern","Master Key"]: self.ul_auth.add(t)
        pt=self.ul_auth.tab("Password")
        self.up=entr(pt,"Enter vault password",secret=True); self.up.pack(fill="x",padx=8,pady=24)
        pp=self.ul_auth.tab("Pattern")
        self.upw=PatternWidget(pp,on_complete=self._on_up); self.upw.pack(pady=8)
        pm=self.ul_auth.tab("Master Key")
        lbl(pm,"Unlocks any vault regardless of password",color=TEXT_MUTED,size=11).pack(pady=(16,6))
        self.umk=entr(pm,"PSV-XXXX-XXXX-XXXX-XXXX-XXXX-XXXX",secret=True); self.umk.pack(fill="x",padx=8,pady=(0,8))
        btn(s,"🔓   Unlock Folder",self._do_unlock,h=44).pack(padx=12,pady=14,fill="x")

    def _on_up(self,p):
        self._unlock_pattern=p
        if not self.vault_path.get().strip():
            self._st("⚠  Select a vault file first", WARN); self._auto_clear_st()
            return
        self._run_unlock(pattern=p)

    def _winlock_tab(self):
        outer=self.tab.tab("🛡  Win Lock")
        s=ctk.CTkScrollableFrame(outer,fg_color="transparent")
        s.pack(fill="both",expand=True)
        self.wl_path=ctk.StringVar()
        lbl(s,"Makes folder show 'Access Denied' to everyone.\nNo vault file. Windows permission trick only.",
            color=TEXT_MUTED,size=12,justify="center").pack(pady=(18,10))
        sec_lbl(s,"FOLDER"); path_row(s,self.wl_path,"Select folder...","folder",self._browse)
        wcard=ctk.CTkFrame(s,fg_color="#1C1000",corner_radius=8)
        wcard.pack(fill="x",padx=12,pady=10)
        lbl(wcard,"⚠  Does NOT encrypt files.\nUse Vault Lock for real encryption.",
            color=WARN,size=12,justify="center").pack(pady=10)
        btn(s,"🛡   Apply Windows Lock",self._do_wl,color=DANGER,hover=DANGER_H,h=44).pack(padx=12,pady=(4,6),fill="x")
        btn(s,"🔓   Remove Windows Lock",self._do_wul,color=BG_CARD2,hover=BG_CARD,h=40).pack(padx=12,pady=(0,12),fill="x")

    def _browse(self,var,kind):
        p=(filedialog.askopenfilename(filetypes=[("Vault","*.vault")])
           if kind=="vault" else filedialog.askdirectory())
        if p: var.set(p)

    def _st(self,msg,color="white"):
        self.st_var.set(msg); self.st_lbl.configure(text_color=color); self.update()

    def _auto_clear_st(self,delay_ms=3500):
        try: self.after_cancel(self._st_clear_id)
        except: pass
        def _clear(): self._st("Ready",TEXT_DIM)
        self._st_clear_id=self.after(delay_ms,_clear)

    def _folder_info(self,folder):
        n=0; size=0
        for r,d,fs in os.walk(folder):
            for f in fs:
                fp=os.path.join(r,f)
                try: size+=os.path.getsize(fp); n+=1
                except: pass
        def hz(b):
            for u in ["B","KB","MB","GB","TB"]:
                if b<1024: return f"{b:.1f} {u}"
                b/=1024
            return f"{b:.1f} PB"
        return n,hz(size)

    def _do_lock(self):
        folder = self.lock_path.get().strip()
        vault_dir = self.vault_dir.get().strip() or None
        if not folder: self._st("⚠  Select a folder", WARN); self._auto_clear_st(); return
        active = self.lock_auth.get()
        pwd = pat = None

        if active == "Password":
            pwd, cf = self.lp1.get(), self.lp2.get()
            if not pwd: self._st("⚠  Enter a password", WARN); self._auto_clear_st(); return
            if pwd != cf: self._st("⚠  Passwords don't match", WARN); self._auto_clear_st(); return
            if len(pwd) < 6: self._st("⚠  Min 6 characters", WARN); self._auto_clear_st(); return
        elif active == "Pattern":
            pat = self._lock_pattern
            if len(pat) < 4: self._st("⚠  Draw pattern (min 4 dots)", WARN); self._auto_clear_st(); return
        elif active == "Both":
            pwd, cf = self.lb1.get(), self.lb2.get()
            pat = self._lock_both_pattern
            if not pwd: self._st("⚠  Enter a password", WARN); self._auto_clear_st(); return
            if pwd != cf: self._st("⚠  Passwords don't match", WARN); self._auto_clear_st(); return
            if len(pat) < 4: self._st("⚠  Draw pattern too", WARN); self._auto_clear_st(); return

        n,sz=self._folder_info(folder)
        self._st(f"⏳  Encrypting {n} file(s) ({sz}) — please wait...", TEXT_DIM)
        result = engine.lock_folder(folder, password=pwd, pattern=pat,
                                    vault_dir=vault_dir, delete_original=self.del_var.get())
        if result["success"]:
            if self.mk_reminder_var.get():
                mk = cfg.load_master_key()
                if mk: messagebox.showinfo("Master Key Reminder", f"Your master key:\n\n{mk}")
                self.mk_reminder_var.set(False)
            self.lock_path.set(""); self.vault_dir.set("")
            self.lp1.delete(0,"end"); self.lp2.delete(0,"end")
            self.lb1.delete(0,"end"); self.lb2.delete(0,"end")
            try:
                self.lpw.reset()
            except Exception:
                pass
            try:
                self.lbw.reset()
            except Exception:
                pass
            self._lock_pattern=""; self._lock_both_pattern=""
            try:
                self.lpl.configure(text="Draw pattern (min 4 dots)",text_color=TEXT_MUTED)
            except Exception:
                pass
            try:
                self.lbl2.configure(text="Also draw pattern",text_color=TEXT_MUTED)
            except Exception:
                pass
            self._st("✅  Folder locked successfully!", SUCCESS)
            self._refresh_home(); self._auto_clear_st(5000)
        else:
            self._st(f"❌  {result['error']}", DANGER); self._auto_clear_st(6000)

 
    def _lock_app_now(self):
        if messagebox.askyesno("Lock App", "Invalidate session and lock PSVault now?"):
             cfg.clear_session()
             self._check_session()
            
   

    def _do_unlock(self):
        active=self.ul_auth.get()
        if active=="Password":
            p=self.up.get()
            if not p: self._st("⚠  Enter password",WARN); self._auto_clear_st(); return
            self._run_unlock(password=p)
        elif active=="Pattern":
            if not self._unlock_pattern: self._st("⚠  Draw pattern first",WARN); self._auto_clear_st(); return
            self._run_unlock(pattern=self._unlock_pattern)
        elif active=="Master Key":
            mk=self.umk.get().strip()
            if not mk: self._st("⚠  Enter master key",WARN); self._auto_clear_st(); return
            self._run_unlock(password=mk)

    def _run_unlock(self,password=None,pattern=None):
        vault=self.vault_path.get().strip()
        out=self.out_path.get().strip() or None
        if not vault: self._st("⚠  Select a vault file",WARN); self._auto_clear_st(); return
        self._st("⏳  Decrypting — please wait...",TEXT_DIM)
        if out:
            import shutil
            nv=os.path.join(out,os.path.basename(vault))
            try:
                shutil.copy2(vault,nv)
                result=engine.unlock_folder(nv,password=password,pattern=pattern,output_dir=out)
                if result["success"]: os.remove(vault)
            except Exception as e: self._st(f"❌  {e}",DANGER); self._auto_clear_st(6000); return
        else:
            result=engine.unlock_folder(vault,password=password,pattern=pattern)
        if result["success"]:
            self.vault_path.set(""); self.out_path.set("")
            self.up.delete(0,"end"); self.umk.delete(0,"end")
            self._unlock_pattern=""
            if hasattr(self,"upw"): self.upw.reset()
            self._st(f"✅  Unlocked → {result['folder_path']}",SUCCESS)
            self._refresh_home(); self._auto_clear_st(6000)
        else:
            self._st(f"❌  {result['error']}",DANGER); self._auto_clear_st(6000)
            self._unlock_pattern=""
            if hasattr(self,"upw"): self.upw.reset()

    def _do_wl(self):
        folder=self.wl_path.get().strip()
        if not folder: self._st("⚠  Select a folder",WARN); self._auto_clear_st(); return
        if not messagebox.askyesno("Confirm",f"Apply Windows Lock?\n\n{folder}"): return
        self._st("⏳  Applying...",TEXT_DIM)
        r=engine.win_lock_folder(folder)
        if r["success"]:
            self.wl_path.set("")
            self._st("✅  Windows Lock applied!",SUCCESS); self._refresh_home(); self._auto_clear_st(5000)
        else: self._st(f"❌  {r['error']}",DANGER); self._auto_clear_st(6000)

    def _do_wul(self):
        folder=self.wl_path.get().strip()
        if not folder: self._st("⚠  Select a folder",WARN); self._auto_clear_st(); return
        self._st("⏳  Removing lock...",TEXT_DIM)
        r=engine.win_unlock_folder(folder)
        if r["success"]:
            self.wl_path.set("")
            self._st("✅  Windows Lock removed!",SUCCESS); self._auto_clear_st(5000)
        else: self._st(f"❌  {r['error']}",DANGER); self._auto_clear_st(6000)


if __name__=="__main__":
    app=App()
    app.mainloop()
