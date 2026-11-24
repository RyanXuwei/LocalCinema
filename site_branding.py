"""Custom website title and logo shown on the browser pages (config site_title / site_logo / site_title_in_header)."""
import html,secrets,unicodedata
from pathlib import Path

DEFAULT_TITLE='LocalCinema · by BitingBox Studio'
PLAIN_TITLE='LocalCinema'
DEFAULT_LOGO='/assets/camellia-emblem.png'
DEFAULT_ICON='/assets/localcinema.ico'
MAX_TITLE=60
LOGO_SIZE=512

def clean_title(text):
    text=''.join(' ' if unicodedata.category(ch)[0] in 'CZ' else ch for ch in str(text or ''))
    text=' '.join(text.split())
    if len(text)>MAX_TITLE: raise ValueError(f'網站標題最多 {MAX_TITLE} 字。')
    return text

class SiteBranding:
    def __init__(self,config,data_dir,save):
        self.config=config; self.folder=Path(data_dir)/'site-logo'; self.save=save
    def title(self): return str(self.config.get('site_title','') or '')
    def title_in_header(self): return bool(self.config.get('site_title_in_header',False)) and bool(self.title())
    def logo_path(self):
        name=str(self.config.get('site_logo','') or '')
        if name and Path(name).name==name and name.endswith('.png'):
            path=self.folder/name
            if path.is_file(): return path
        return None
    def effective_title(self,hide_branding):
        return self.title() or (PLAIN_TITLE if hide_branding else DEFAULT_TITLE)
    def state(self):
        logo=self.logo_path()
        return {'siteTitle':self.title(),'siteTitleInHeader':self.title_in_header(),
                'siteLogo':('/site-logo/'+logo.stem) if logo else ''}
    def _bump(self): self.config['privacy_revision']=int(self.config.get('privacy_revision',0))+1
    def set_title(self,text,in_header=None):
        self.config['site_title']=clean_title(text)
        if in_header is not None: self.config['site_title_in_header']=bool(in_header)
        self._bump(); self.save(self.config)
    def set_logo(self,path):
        from PIL import Image,ImageOps
        self.folder.mkdir(parents=True,exist_ok=True)
        filename=secrets.token_hex(16)+'.png'
        with Image.open(path) as image:
            if image.width*image.height>40000000: raise ValueError('圖片過大，請選擇較小圖片。')
            logo=ImageOps.exif_transpose(image).convert('RGBA')
            logo.thumbnail((LOGO_SIZE,LOGO_SIZE),Image.Resampling.LANCZOS)
            logo.save(self.folder/filename,'PNG',optimize=True)
        old=self.logo_path(); self.config['site_logo']=filename; self._bump(); self.save(self.config)
        if old: old.unlink(missing_ok=True)
    def clear_logo(self):
        old=self.logo_path(); self.config.pop('site_logo',None); self._bump(); self.save(self.config)
        if old: old.unlink(missing_ok=True)
    def logo_file(self,key):
        logo=self.logo_path()
        return logo if logo and logo.stem==key else None
    def apply(self,page,hide_branding):
        """Server-side substitution so the first paint already shows the custom title and logo."""
        page=page.replace('<title>'+DEFAULT_TITLE+'</title>','<title>'+html.escape(self.effective_title(hide_branding))+'</title>',1)
        logo=self.state()['siteLogo']
        if logo:
            page=page.replace('href="'+DEFAULT_ICON+'" type="image/x-icon"','href="'+logo+'" type="image/png"',1)
            page=page.replace('<img id="brandLogo" src="'+DEFAULT_LOGO+'"','<img id="brandLogo" class="custom" src="'+logo+'"',1)
        if self.title_in_header():
            page=page.replace('<em id="brandText" class="brandText">映室 <span>LOCAL CINEMA</span></em>','<em id="brandText" class="brandText custom">'+html.escape(self.title())+'</em>',1)
        return page

def build_branding_page(parent,root,lib,base,ttk,tk,filedialog,messagebox):
    """Backend tab: site title, logo and the BitingBox credit toggle in one place."""
    branding=lib.branding
    ttk.Label(parent,text='網站外觀與署名',font=('Microsoft JhengHei UI',14)).pack(anchor='w',padx=20,pady=(14,2))
    ttk.Label(parent,text='自訂瀏覽器分頁標題與網頁商標；留白或恢復預設即使用映室原本的標題與圖示。變更約 1 秒內同步到已開啟的頁面。',style='Sub.TLabel',wraplength=820).pack(anchor='w',padx=20)
    title_box=ttk.LabelFrame(parent,text='網站標題（Title）',padding=12);title_box.pack(fill='x',padx=20,pady=(10,6))
    title_var=tk.StringVar(value=branding.title())
    ttk.Entry(title_box,textvariable=title_var,width=48).grid(row=0,column=0,sticky='we',padx=(0,10))
    header_var=tk.BooleanVar(value=bool(lib.config.get('site_title_in_header',False)))
    hint=tk.StringVar()
    def refresh_hint():
        hint.set('目前分頁標題：'+branding.effective_title(bool(lib.config.get('hide_branding',False))))
    def save_title():
        try: lib.set_site_title(title_var.get(),header_var.get()); title_var.set(branding.title()); refresh_hint()
        except ValueError as error: messagebox.showerror('無法儲存',str(error),parent=root)
    def reset_title(): title_var.set(''); header_var.set(False); save_title()
    ttk.Button(title_box,text='套用標題',command=save_title).grid(row=0,column=1,padx=3)
    ttk.Button(title_box,text='恢復預設',command=reset_title).grid(row=0,column=2,padx=3)
    ttk.Checkbutton(title_box,text='首頁左上角也顯示此標題（取代「映室 LOCAL CINEMA」字樣）',variable=header_var,command=save_title).grid(row=1,column=0,columnspan=3,sticky='w',pady=(8,0))
    ttk.Label(title_box,textvariable=hint,style='Sub.TLabel').grid(row=2,column=0,columnspan=3,sticky='w',pady=(6,0))
    title_box.columnconfigure(0,weight=1)
    logo_box=ttk.LabelFrame(parent,text='網站商標（Logo）',padding=12);logo_box.pack(fill='x',padx=20,pady=6)
    preview=ttk.Label(logo_box);preview.grid(row=0,column=0,rowspan=2,padx=(0,16))
    logo_hint=tk.StringVar()
    def draw_logo():
        path=branding.logo_path() or Path(base)/'assets'/'camellia-emblem.png'
        try:
            from PIL import Image,ImageTk
            with Image.open(path) as image:
                image=image.convert('RGBA');image.thumbnail((72,72),Image.Resampling.LANCZOS)
                preview.photo=ImageTk.PhotoImage(image);preview.configure(image=preview.photo)
        except (OSError,ImportError): preview.configure(image='')
        logo_hint.set('使用自訂商標（顯示於首頁左上角，並作為分頁圖示）' if branding.logo_path() else '未設定：首頁左上角只顯示文字，分頁圖示使用映室圖示')
    def choose_logo():
        filename=filedialog.askopenfilename(parent=root,title='選擇網站商標',filetypes=[('圖片','*.png *.jpg *.jpeg *.webp *.bmp *.gif')])
        if not filename: return
        try: lib.set_site_logo(filename)
        except (OSError,ValueError) as error: return messagebox.showerror('無法使用此圖片',str(error) or '圖片格式無法讀取。',parent=root)
        draw_logo()
    def reset_logo(): lib.clear_site_logo(); draw_logo()
    actions=ttk.Frame(logo_box);actions.grid(row=0,column=1,sticky='w')
    ttk.Button(actions,text='選擇圖片…',command=choose_logo).pack(side='left',padx=(0,6))
    ttk.Button(actions,text='恢復預設',command=reset_logo).pack(side='left')
    ttk.Label(logo_box,text='建議使用透明背景的方形 PNG；會等比例縮至 512 像素內保存（不裁切、不重繪），顯示在首頁左上角標題前與瀏覽器分頁圖示。',style='Sub.TLabel',wraplength=620).grid(row=1,column=1,sticky='w',pady=(8,0))
    ttk.Label(logo_box,textvariable=logo_hint).grid(row=2,column=1,sticky='w',pady=(4,0))
    credit_box=ttk.LabelFrame(parent,text='版權署名',padding=12);credit_box.pack(fill='x',padx=20,pady=6)
    branding_var=tk.BooleanVar(value=bool(lib.config.get('hide_branding',False)))
    def toggle_credit(): lib.set_hide_branding(branding_var.get()); refresh_hint()
    ttk.Checkbutton(credit_box,text='隱藏首頁的 BitingBox Studio 與 Ryan Hsu 版權署名',variable=branding_var,command=toggle_credit).pack(anchor='w')
    ttk.Label(credit_box,text='開啟後網頁隱藏頂部副標、頁尾工作室標誌與署名；未自訂標題時分頁標題改為 LocalCinema。',style='Sub.TLabel',wraplength=800).pack(anchor='w',pady=(4,0))
    refresh_hint(); draw_logo()
