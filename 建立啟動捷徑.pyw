"""Create this app's icon shortcut without changing Python file associations."""
from pathlib import Path
import subprocess
import sys
import os
import tkinter as tk
from tkinter import messagebox

def create():
    base=Path(__file__).resolve().parent
    executable=Path(sys.executable)
    if executable.name.lower()=='python.exe' and executable.with_name('pythonw.exe').is_file():
        executable=executable.with_name('pythonw.exe')
    target=base/'LocalCinema.pyw'
    icon=base/'assets'/'localcinema.ico'
    shortcut=base/'映室 LocalCinema.lnk'
    subprocess.run([str(Path(os.environ['SystemRoot'])/'System32'/'cscript.exe'),'//NoLogo',str(base/'create_shortcut.vbs'),str(executable),str(target),str(shortcut),str(icon)],check=True,creationflags=0x08000000)
    return shortcut

if __name__=='__main__':
    window=tk.Tk(); window.withdraw()
    try:
        shortcut=create()
        messagebox.showinfo('啟動圖示已建立','已在程式資料夾建立「映室 LocalCinema」捷徑。\n可直接使用，或將捷徑複製到桌面。\n若移動程式資料夾，請重新建立捷徑。')
    except Exception:
        messagebox.showerror('無法建立捷徑','請確認程式資料夾可寫入，且 Windows Script Host 可使用。未更動其他 Python 檔案圖示或個人資料。')
    finally: window.destroy()
