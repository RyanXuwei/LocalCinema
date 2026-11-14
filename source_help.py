"""Source-mode explanations illustrated with fictional examples."""
def open_source_help(root,base):
    import tkinter as tk
    from tkinter import ttk
    from PIL import Image,ImageTk
    old=getattr(root,'source_help_window',None)
    if old and old.winfo_exists():old.deiconify();old.lift();return
    window=tk.Toplevel(root);root.source_help_window=window;window.title('影片清單收集方式｜圖解說明')
    window.configure(bg='#171817');window.geometry(f'{min(980,root.winfo_screenwidth()-80)}x{min(740,root.winfo_screenheight()-100)}')
    tabs=ttk.Notebook(window,style='Source.TNotebook');tabs.pack(fill='both',expand=True,padx=12,pady=8)
    window.guide_images=[]
    for mode,title,details in [
        ('directory','目錄影片清單','封面：使用作品資料夾內的圖片；沒有圖片則自動擷取影片畫面。'),
        ('flat','平鋪影片清單','封面：根目錄影片依檔名比對圖片（可部分涵蓋）；資料夾片單使用夾內圖片。沒有圖片則自動擷取。')]:
        page=ttk.Frame(tabs);tabs.add(page,text=title)
        canvas=tk.Canvas(page,bg='#171c18',highlightthickness=0)
        scroll=ttk.Scrollbar(page,orient='vertical',command=canvas.yview);scroll.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
        canvas.configure(yscrollcommand=scroll.set)
        panel=ttk.Frame(canvas);canvas.create_window((0,0),window=panel,anchor='nw')
        with Image.open(base/'assets'/('source-guide-'+mode+'.png')) as picture:
            picture.thumbnail((min(920,root.winfo_screenwidth()-140),560),Image.Resampling.LANCZOS)
            photo=ImageTk.PhotoImage(picture)
        window.guide_images.append(photo);ttk.Label(panel,image=photo).pack(anchor='w')
        ttk.Label(panel,text=details,wraplength=min(880,root.winfo_screenwidth()-160),padding=(12,10)).pack(anchor='w')
        ttk.Label(panel,text='例外：某個子資料夾若已另設為平鋪片源，會由該片源接管，避免被父層重複收集。',wraplength=min(880,root.winfo_screenwidth()-160),padding=(12,10)).pack(anchor='w')
        panel.bind('<Configure>',lambda event,c=canvas:c.configure(scrollregion=c.bbox('all')))
    ttk.Button(window,text='關閉',command=window.destroy).pack(pady=(0,10))
