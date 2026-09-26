"""Visible, non-activating Windows controls for the genuine GTA/FrogPilot bridge."""
import ctypes
from ctypes import wintypes
import faulthandler
import json
import logging
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk

ROOT = Path(__file__).resolve().parents[1]
fault_log = (ROOT/'reports/control-panel-faults.log').open('a', buffering=1, encoding='utf-8')
sys.stderr = fault_log
faulthandler.enable(fault_log, all_threads=True)
logging.basicConfig(filename=ROOT/'reports/control-panel.log', level=logging.INFO)
u, k = ctypes.windll.user32, ctypes.windll.kernel32
u.SetProcessDPIAware()
for name in ['FindWindowW', 'GetForegroundWindow', 'GetAncestor', 'SetWindowLongPtrW', 'GetWindowLongPtrW']:
    getattr(u, name).restype = ctypes.c_void_p
u.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
u.GetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int]
u.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
u.BringWindowToTop.argtypes = [ctypes.c_void_p]
u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
u.CallWindowProcW.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
u.CallWindowProcW.restype = ctypes.c_ssize_t
k.CreateMutexW.restype = ctypes.c_void_p
mutex = k.CreateMutexW(None, False, 'Local\\OpenPilotGTA.ControlPanel')
if k.GetLastError() == 183:
    if '--restart' not in sys.argv:
        raise SystemExit(0)
    existing = u.FindWindowW(None, 'NMK AI Driving Controls')
    if existing:
        u.PostMessageW(ctypes.c_void_p(existing), 0x10, 0, 0)
        deadline = time.monotonic()+4
        while u.FindWindowW(None, 'NMK AI Driving Controls') and time.monotonic() < deadline:
            time.sleep(.1)
        if u.FindWindowW(None, 'NMK AI Driving Controls'):
            raise SystemExit('Existing control panel did not close')

BG, CARD, MUTED, TEXT, GREEN, RED = '#101820', '#1c2934', '#a8b9c6', '#f1f6fa', '#236c52', '#913f47'
app = tk.Tk()
app.title('NMK AI Driving Controls')
app.configure(bg=BG)
app.geometry(f'750x845+{min(2050, max(0, app.winfo_screenwidth()-780))}+65')
app.attributes('-topmost', True)
app.resizable(False, False)
app.option_add('*Font', ('Segoe UI', 12))
actions = queue.PriorityQueue()
results = queue.Queue()
interrupt = threading.Event()
closing = threading.Event()
restore_requested = threading.Event()
serial = 0
buttons = {}
layout = []
VK = {**{f'F{i}':0x6f+i for i in range(1,13)}, 'B':0x42, 'L':0x4c,
      '[':0xdb, ']':0xdd, '+':0xbb, '-':0xbd, 'INSERT':0x2d, 'NUDGE_LEFT':0x64, 'NUDGE_RIGHT':0x66}

def enqueue(key, hold=.16, shift=False):
    global serial
    if key == 'F10':
        interrupt.set()
        while not actions.empty():
            try:
                actions.get_nowait()
            except queue.Empty:
                break
    serial += 1
    actions.put((0 if key == 'F10' else 1, serial, key, hold, shift))
    feedback.set('جارٍ إرسال '+key+'…')

def worker():
    while not closing.is_set():
        try:
            _, _, key, hold, shift = actions.get(timeout=.2)
        except queue.Empty:
            continue
        interrupt.clear()
        hwnd = u.FindWindowW(None, 'Grand Theft Auto V')
        if not hwnd:
            results.put('افتح وضع القصة في GTA أولًا.')
            continue
        current = k.GetCurrentThreadId()
        foreground = u.GetWindowThreadProcessId(u.GetForegroundWindow(), None)
        attached = current != foreground and u.AttachThreadInput(current, foreground, True)
        try:
            u.BringWindowToTop(hwnd)
            u.SetForegroundWindow(hwnd)
        finally:
            if attached:
                u.AttachThreadInput(current, foreground, False)
        time.sleep(.08)
        if u.GetForegroundWindow() != hwnd:
            results.put('انقر داخل GTA مرة واحدة ثم استخدم اللوحة.')
            continue
        code = VK[key]
        try:
            if shift:
                u.keybd_event(0x10, u.MapVirtualKeyW(0x10, 0), 0, 0)
            u.keybd_event(code, u.MapVirtualKeyW(code, 0), 0, 0)
            deadline = time.monotonic()+hold
            while time.monotonic() < deadline and not closing.is_set() and not interrupt.is_set():
                time.sleep(.01)
        finally:
            u.keybd_event(code, u.MapVirtualKeyW(code, 0), 2, 0)
            if shift:
                u.keybd_event(0x10, u.MapVirtualKeyW(0x10, 0), 2, 0)
        results.put('أُرسل الأمر — الحالة المباشرة أعلاه.')
        # Give the game's edge detector at least two frames to see release.
        time.sleep(.1)

threading.Thread(target=worker, daemon=True).start()
outer = tk.Frame(app, bg=BG)
outer.pack(fill='both', expand=True, padx=22, pady=18)
tk.Label(outer, text='تحكم القيادة — NMK AI', font=('Segoe UI', 22, 'bold'), bg=BG, fg=TEXT, anchor='w').pack(fill='x')
connection = tk.StringVar(value='في انتظار الاتصال المباشر باللعبة…')
tk.Label(outer, textvariable=connection, bg=BG, fg=MUTED, anchor='w').pack(fill='x', pady=(3,12))
status = tk.Frame(outer, bg=CARD, padx=14, pady=10)
status.pack(fill='x')
speed = tk.StringVar(value='0 كم/س     الأقصى —')
state = tk.StringVar(value='التوجيه مطفأ  •  التحكم بالسرعة مطفأ')
tk.Label(status, textvariable=speed, font=('Segoe UI', 20, 'bold'), bg=CARD, fg=TEXT, anchor='w').pack(fill='x')
tk.Label(status, textvariable=state, bg=CARD, fg=MUTED, anchor='w').pack(fill='x', pady=(4,0))
last_stop = tk.StringVar(value='')
radar_status = tk.StringVar(value='الرادار: بانتظار السيارة والكاميرا')
tk.Label(status, textvariable=radar_status, bg=CARD, fg=MUTED, anchor='w',
         font=('Segoe UI',10)).pack(fill='x', pady=(3,0))
tk.Label(status, textvariable=last_stop, bg=CARD, fg=MUTED, anchor='w',
         font=('Segoe UI',10), wraplength=670).pack(fill='x', pady=(3,0))

def section(label):
    tk.Label(outer, text=label.upper(), font=('Segoe UI', 10, 'bold'), fg=MUTED, bg=BG, anchor='w').pack(fill='x', pady=(12,5))
    frame = tk.Frame(outer, bg=BG)
    frame.pack(fill='x')
    return frame

def button(frame, label, key, column, row=0, hold=.16, shift=False, status_key=None, danger=False):
    frame.columnconfigure(column, weight=1, uniform='buttons')
    b = tk.Button(frame, text=label, command=lambda:enqueue(key,hold,shift), bg=RED if danger else CARD,
                  activebackground='#3c5365', activeforeground=TEXT, fg=TEXT, relief='flat', bd=0,
                  font=('Segoe UI', 11, 'bold'), padx=6, pady=11, takefocus=0, cursor='hand2')
    b.grid(row=row, column=column, sticky='nsew', padx=3, pady=3)
    if status_key:
        buttons[status_key] = (b, label)
    layout.append((b,label,key,hold,shift))
    return b

f = section('سيارة القائد الآلي • Krieger الافتراضية')
button(f,'إحضار سيارة القائد الآلي', 'F12',0)
car_status = tk.StringVar(value='Krieger الافتراضية • أوقف السيارة قبل الإحضار')
tk.Label(outer,textvariable=car_status,bg=BG,fg=MUTED,anchor='w',font=('Segoe UI',10)).pack(fill='x')
f = section('التشغيل')
button(f,'الكاميرا', 'F6',0,status_key='camera')
button(f,'مفتاح التوجيه الرئيسي','F7',1,status_key='cruise_master')
button(f,'تثبيت السرعة الحالية','F8',2)
button(f,'استئناف','F8',0,1,shift=True)
button(f,'إلغاء التثبيت','F9',1,1)
button(f,'إطفاء الكل','F10',2,1,danger=True)
f = section('السرعة القصوى')
button(f,'− خطوة كبيرة','-',0,shift=True)
button(f,'− سرعة','-',1)
button(f,'+ سرعة','+',2)
button(f,'+ خطوة كبيرة','+',3,shift=True)
f = section('الإشارات والقيادة')
button(f,'◀ إشارة يسار','[',0,status_key='left_blinker')
button(f,'إشارة يمين ▶',']',1,status_key='right_blinker')
button(f,'وضع تجريبي','F5',2,status_key='experimental_mode')
button(f,'شخصية القيادة','F4',0,1,status_key='personality')
button(f,'وضع المرور','F11',1,1,status_key='traffic')
button(f,'اقتصادي / عادي / رياضي','INSERT',2,1,status_key='drive_mode')
f = section('تجاوز مؤقت')
button(f,'انطلاق حر','F1',0,status_key='coast')
button(f,'إيقاف التوجيه مؤقتًا','F2',1,status_key='pause_lateral')
button(f,'إيقاف الوقود/الفرامل مؤقتًا','F3',2,status_key='pause_longitudinal')
f = section('أزرار المقود القابلة للبرمجة')
button(f,'المسافة: نقرة','B',0)
button(f,'المسافة: ضغطة','B',1,hold=.7)
button(f,'المسافة: ضغطة طويلة','B',2,hold=2.8)
button(f,'زر LKAS','L',0,1)
button(f,'تثبيت يسار خفيف','NUDGE_LEFT',1,1,hold=.25)
button(f,'تثبيت يمين خفيف','NUDGE_RIGHT',2,1,hold=.25)
feedback = tk.StringVar(value='Start: Camera â†’ Steering master â†’ SET or RESUME.')
tk.Label(outer,textvariable=feedback,bg=BG,fg=TEXT,anchor='w',wraplength=690,justify='left').pack(fill='x',pady=(12,0))
tk.Label(outer,text='الكاميرا وحدها لا تُفعّل النظام. الأزرار تُبقي التركيز على GTA.\nأفعال المسافة وLKAS تتبع إعدادات أزرار مقود القائد الآلي لديك.',
         bg=BG,fg=MUTED,anchor='w',justify='left',font=('Segoe UI',10)).pack(fill='x',pady=(7,0))

def refresh():
    # A Win32 WNDPROC callback must not call into Tcl/Tk. Poll its signal
    # here, inside Tk's own event loop, to avoid native reentrant aborts.
    if restore_requested.is_set():
        restore_requested.clear()
        restore_panel()
    try:
        while True:
            feedback.set(results.get_nowait())
    except queue.Empty:
        pass
    try:
        path = ROOT/'reports/bridge-status.json'
        live = json.loads(path.read_text())
        fresh = time.time()-path.stat().st_mtime < 4
        valid = fresh and live['valid']
        spawn_messages = {0:'Stock Krieger â€¢ stop before spawning', 1:'جارٍ تحميل Krieger…',
                          2:'أُحضرت Krieger • الكاميرا تعمل • القيادة غير مفعّلة',
                          3:'طراز Krieger غير متوفر في هذا التثبيت', 4:'لا توجد مساحة طريق خالية قريبًا — تحرك وأعد المحاولة',
                          5:'انتهت مهلة تحميل Krieger — أعد المحاولة', 6:'أوقف السيارة واخرج من قائمة الإيقاف أولًا',
                          7:'لم يتمكن GTA من إنشاء Krieger — أعد المحاولة',
                          8:'تعذّر تهيئة دعم مركبات DLC في وضع القصة'}
        car_status.set(spawn_messages.get(live.get('spawn_status', 0), 'بانتظار حالة السيارة'))
        connection.set('مباشر • متصل بملف GTA' if valid else 'بانتظار سيارة GTA والكاميرا الأمامية')
        speed.set(f"{live['speed_mps']*3.6:.0f} كم/س     الأقصى {live['cruise_speed_mps']*3.6:.0f} كم/س")
        lat = valid and live.get('lateral_applied', False)
        long = valid and live.get('longitudinal_applied', False)
        state.set(f"التوجيه {'مفعّل' if lat else 'مطفأ'}  •  التحكم بالسرعة {'مفعّل' if long else 'مطفأ'}")
        if valid and live.get('radar_valid'):
            radar_text = f"الرادار مفعّل • {live.get('radar_points', 0)} مركبات مرصودة"
            if live.get('radar_lead'):
                radar_text += f" • المركبة الأمامية على {live['radar_lead_distance']:.0f} م • فرق السرعة {live['radar_lead_relative_speed']*3.6:+.0f} كم/س"
            radar_status.set(radar_text)
        else:
            radar_status.set('الرادار: بانتظار بيانات مستشعرات حديثة')
        if lat or long:
            last_stop.set('')
        else:
            diagnostic=ROOT/'reports/native-disengagement.json'
            if diagnostic.exists():
                stopped=json.loads(diagnostic.read_text())
                prefix='آخر إيقاف (مرجّح): ' if 'inferred' in stopped.get('evidence','') else 'آخر إيقاف: '
                last_stop.set(prefix+stopped['reason'])
        for name,(b,label) in buttons.items():
            value = live.get(name, False) if fresh else False
            if name == 'personality':
                b.configure(text='شخصية: '+str(value or '—'))
            elif name == 'drive_mode':
                b.configure(text='نمط القيادة: '+str(value or 'عادي'))
            else:
                b.configure(bg=GREEN if value else CARD, text=label+(' • مفعّل' if value else ''))
    except (OSError,ValueError,KeyError):
        connection.set('بانتظار حالة الجسر المباشرة…')
    app.after(200,refresh)

def close():
    enqueue('F10')
    def finish():
        closing.set()
        app.destroy()
    app.after(500,finish)

app.protocol('WM_DELETE_WINDOW',close)
app.update_idletasks()
app.geometry(f'750x{min(outer.winfo_reqheight()+36, app.winfo_screenheight()-140)}')
panel_height=min(outer.winfo_reqheight()+36,app.winfo_screenheight()-140)
app.minsize(750,panel_height)

def restore_panel():
    # Restore through Tk; resizing an iconified Win32 wrapper loses geometry.
    app.deiconify()
    app.state('normal')
    app.geometry(f'750x{panel_height}+{min(2050,max(0,app.winfo_screenwidth()-780))}+65')
    app.attributes('-topmost',True)
    app.lift()
    logging.info('Control panel restored pid=%s', os.getpid())

hwnd = u.GetAncestor(app.winfo_id(), 2)
style = u.GetWindowLongPtrW(hwnd,-20) or 0
u.SetWindowLongPtrW(hwnd,-20,style | 0x08000000)  # WS_EX_NOACTIVATE
WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t,ctypes.c_void_p,ctypes.c_uint,ctypes.c_size_t,ctypes.c_ssize_t)
previous_proc = None
@WNDPROC
def wndproc(window,message,wparam,lparam):
    if message == 0x805b:
        restore_requested.set()
        return 0
    if message == 0x21:  # WM_MOUSEACTIVATE: let the click through without stealing focus.
        return 3
    return u.CallWindowProcW(previous_proc,window,message,wparam,lparam)
previous_proc = u.SetWindowLongPtrW(hwnd,-4,ctypes.cast(wndproc,ctypes.c_void_p))
def save_layout():
    (ROOT/'reports/control-panel-layout.json').write_text(json.dumps([
        {'label':label, 'key':key, 'hold':hold, 'shift':shift,
         'x':b.winfo_rootx()+b.winfo_width()//2, 'y':b.winfo_rooty()+b.winfo_height()//2}
        for b,label,key,hold,shift in layout], indent=2))
app.bind('<Configure>',lambda _:app.after_idle(save_layout))
refresh()
logging.info('Control panel ready pid=%s', os.getpid())
app.after(100,restore_panel)
app.mainloop()
