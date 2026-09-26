"""Show the genuine WSLg FrogPilot window above GTA without changing its input.

DWM shares the existing UI surface: no second UI, model, or video encoder.
GTA's window-only camera capture excludes this separate compositor window.
"""
import ctypes as c
from ctypes import wintypes as w
import json
import logging
from pathlib import Path
import subprocess
import time
import tkinter as tk

ROOT=Path(__file__).resolve().parents[1]
config=json.loads((ROOT/'config/project.json').read_text(encoding='utf-8-sig'))
local=ROOT/'config/local.json'
if local.exists(): config.update(json.loads(local.read_text(encoding='utf-8-sig')))
UI_TITLE=f"ui ({config['wslDistribution']})"
logging.basicConfig(filename=ROOT/'reports/ui-overlay.log',level=logging.INFO)
u=c.WinDLL('user32',use_last_error=True)
d=c.WinDLL('dwmapi',use_last_error=True)
k=c.WinDLL('kernel32',use_last_error=True)
u.SetProcessDPIAware()
for name in ('FindWindowW','GetForegroundWindow','GetAncestor','GetWindowLongPtrW','SetWindowLongPtrW'):
  getattr(u,name).restype=c.c_void_p
u.GetAncestor.argtypes=[c.c_void_p,c.c_uint]
u.GetWindowLongPtrW.argtypes=[c.c_void_p,c.c_int]
u.SetWindowLongPtrW.argtypes=[c.c_void_p,c.c_int,c.c_void_p]
u.GetWindowRect.argtypes=[c.c_void_p,c.POINTER(w.RECT)]
u.GetClientRect.argtypes=[c.c_void_p,c.POINTER(w.RECT)]
u.ClientToScreen.argtypes=[c.c_void_p,c.POINTER(w.POINT)]
u.IsWindowVisible.argtypes=u.IsIconic.argtypes=[c.c_void_p]
u.ShowWindowAsync.argtypes=[c.c_void_p,c.c_int]
u.SetWindowPos.argtypes=[c.c_void_p,c.c_void_p,c.c_int,c.c_int,c.c_int,c.c_int,c.c_uint]
u.CallWindowProcW.argtypes=[c.c_void_p,c.c_void_p,c.c_uint,c.c_size_t,c.c_ssize_t]
u.CallWindowProcW.restype=c.c_ssize_t
k.CreateMutexW.restype=c.c_void_p
mutex=k.CreateMutexW(None,False,'Local\\OpenPilotGTA.UIOverlay')
if c.get_last_error()==183: raise SystemExit(0)

class Properties(c.Structure):
  _fields_=[('flags',w.DWORD),('destination',w.RECT),('source',w.RECT),
            ('opacity',c.c_ubyte),('visible',w.BOOL),('client_only',w.BOOL)]
d.DwmRegisterThumbnail.argtypes=[c.c_void_p,c.c_void_p,c.POINTER(c.c_void_p)]
d.DwmUpdateThumbnailProperties.argtypes=[c.c_void_p,c.POINTER(Properties)]
d.DwmUnregisterThumbnail.argtypes=[c.c_void_p]

settings=ROOT/'runtime/ui-overlay.json'
try: prefs=json.loads(settings.read_text())
except (OSError,ValueError): prefs={}
width=max(360,min(800,int(prefs.get('width',480))))
collapsed=bool(prefs.get('collapsed',False))
app=tk.Tk()
app.title('NMK AI في GTA')
app.overrideredirect(True)
app.configure(bg='#15202a')
app.attributes('-topmost',True)
header=tk.Frame(app,bg='#15202a',height=30)
header.pack(side='top',fill='x')
header.pack_propagate(False)
label=tk.Label(header,text='NMK AI • الواجهة المباشرة',bg='#15202a',fg='#eef5fa',font=('Segoe UI',10,'bold'))
label.pack(side='left',padx=8)
body=tk.Frame(app,bg='#111820')
body.pack(fill='both',expand=True)
placeholder=tk.Label(body,text='في انتظار NMK AI…',bg='#111820',fg='#dce8ee')
placeholder.pack(expand=True)
thumbnail=c.c_void_p()
source=None
previous_geometry=None
last_report=0.
closed=False
background_restores=0

def save():
  settings.write_text(json.dumps(dict(enabled=not closed,width=width,collapsed=collapsed)))

def launch(name):
  subprocess.Popen(['powershell.exe','-NoProfile','-ExecutionPolicy','Bypass','-File',str(ROOT/'scripts'/name)],
                   creationflags=subprocess.CREATE_NO_WINDOW)

def resize(delta):
  global width,previous_geometry
  width=max(360,min(800,width+delta));previous_geometry=None;save()

def collapse():
  global collapsed,previous_geometry
  collapsed=not collapsed;previous_geometry=None;save()
  fold.configure(text='â–¾' if collapsed else 'â–´')

def close():
  global closed
  closed=True;save()
  if thumbnail.value:d.DwmUnregisterThumbnail(thumbnail)
  app.destroy()

def button(text,command):
  b=tk.Button(header,text=text,command=command,relief='flat',bd=0,padx=7,pady=2,
              bg='#223544',fg='#eef5fa',activebackground='#38556a',activeforeground='white',
              font=('Segoe UI',9),takefocus=0)
  b.pack(side='right',padx=1,pady=2)
  return b

button('Ã—',close)
fold=button('â–¾' if collapsed else 'â–´',collapse)
button('+',lambda:resize(80))
button('âˆ’',lambda:resize(-80))
button('Controls',lambda:launch('Start-ControlPanel.ps1'))
button('Full UI',lambda:launch('Show-NMKAi.ps1'))
app.geometry(f'{width}x270+720+45')
app.update_idletasks()
hwnd=u.GetAncestor(app.winfo_id(),2)
style=u.GetWindowLongPtrW(hwnd,-20) or 0
u.SetWindowLongPtrW(hwnd,-20,style|0x08000000|0x80)  # NOACTIVATE, TOOLWINDOW
WNDPROC=c.WINFUNCTYPE(c.c_ssize_t,c.c_void_p,c.c_uint,c.c_size_t,c.c_ssize_t)
old_proc=None
@WNDPROC
def wndproc(window,message,wparam,lparam):
  if message==0x21:return 3  # Mouse interaction does not steal driving focus.
  return u.CallWindowProcW(old_proc,window,message,wparam,lparam)
old_proc=u.SetWindowLongPtrW(hwnd,-4,c.cast(wndproc,c.c_void_p))

def tick():
  global source,thumbnail,previous_geometry,last_report,background_restores
  if closed:return
  try:
    game=u.FindWindowW(None,'Grand Theft Auto V')
    ui=u.FindWindowW(None, UI_TITLE)
    if ui and u.IsIconic(ui):
      # WSLg stops painting an iconified source. Interpret minimize as putting
      # the standalone UI behind other windows, retaining its live surface.
      # Never move/resize WSLg's proxy: that breaks its input coordinates.
      u.ShowWindowAsync(ui,4)  # SW_SHOWNOACTIVATE
      u.SetWindowPos(ui,c.c_void_p(1),0,0,0,0,0x13)  # HWND_BOTTOM, no move/size/focus
      background_restores+=1
    available=game and ui and u.IsWindowVisible(game) and not u.IsIconic(game)
    if not available:
      app.withdraw();previous_geometry=None
    else:
      if app.state()=='withdrawn':app.deiconify()
      client=w.RECT();origin=w.POINT(0,0);source_client=w.RECT()
      u.GetClientRect(game,c.byref(client));u.ClientToScreen(game,c.byref(origin))
      u.GetClientRect(ui,c.byref(source_client))
      view_width=min(width,max(360,client.right-24))
      view_height=0 if collapsed else round(view_width*max(1,source_client.bottom)/max(1,source_client.right))
      geometry=(origin.x+(client.right-view_width)//2,origin.y+10,view_width,view_height+30)
      if geometry!=previous_geometry:
        app.geometry(f'{geometry[2]}x{geometry[3]}{geometry[0]:+d}{geometry[1]:+d}')
        u.SetWindowPos(hwnd,c.c_void_p(-1),*geometry,0x50)
        previous_geometry=geometry
      if ui!=source:
        if thumbnail.value:d.DwmUnregisterThumbnail(thumbnail)
        thumbnail=c.c_void_p()
        hr=d.DwmRegisterThumbnail(hwnd,ui,c.byref(thumbnail))
        if hr:raise RuntimeError(f'DWM registration failed: {hr:#x}')
        source=ui
      props=Properties(0x1|0x4|0x8|0x10,w.RECT(0,30,view_width,view_height+30),w.RECT(),255,not collapsed,True)
      hr=d.DwmUpdateThumbnailProperties(thumbnail,c.byref(props))
      if hr:raise RuntimeError(f'DWM update failed: {hr:#x}')
      label.configure(text='NMK AI • الواجهة المباشرة')
      if time.monotonic()-last_report>1:
        last_report=time.monotonic()
        (ROOT/'reports/ui-overlay-status.json').write_text(json.dumps(dict(monotonic=last_report,
          source_window=source,overlay_window=hwnd,game_window=game,rectangle=list(geometry),
          source_client=[source_client.right,source_client.bottom],collapsed=collapsed,
          backend='DWM live thumbnail',capture_source='GTA window only',
          source_minimized=bool(u.IsIconic(ui)),background_restores=background_restores)))
  except Exception:
    logging.exception('Overlay update failed')
    label.configure(text='NMK AI • إعادة الاتصال')
  app.after(100,tick)

app.protocol('WM_DELETE_WINDOW',close)
save()
tick()
logging.info('Genuine UI overlay started')
app.mainloop()
