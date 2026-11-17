"""Top-level source collections; images stay separate from source media."""
import json
import secrets
import time
from pathlib import Path

DEFAULT_GROUP='default'
DEFAULT_ICON='collection'
WEB_KIND='web'

def kind_of(group):
    return WEB_KIND if group.get('kind')==WEB_KIND else 'media'

class SourceGroups:
    def __init__(self,config,data_dir,asset_dir,save):
        self.config=config; self.data_dir=Path(data_dir); self.asset_dir=Path(asset_dir); self.save=save
        groups=config.setdefault('groups',[])
        if not any(group.get('id')==DEFAULT_GROUP for group in groups):
            groups.insert(0,{'id':DEFAULT_GROUP,'name':'預設片源','icon':DEFAULT_ICON,'updated':0})
        if 'group_categories' not in config:
            config['group_categories']={group['id']:list(config.get('categories',[])) for group in groups}
            config['group_tags']={group['id']:{key:list(tags) for key,tags in config.get('tags',{}).items()} for group in groups}
        config.setdefault('group_tags',{})
        valid={group['id'] for group in groups}
        for root in config.get('roots',[]):
            if root.get('group') not in valid: root['group']=DEFAULT_GROUP
    def catalog(self):
        try: return json.loads((self.asset_dir/'catalog.json').read_text('utf-8'))
        except (OSError,ValueError): return [{'id':DEFAULT_ICON,'name':'綜合片庫'}]
    def get(self,group_id):
        group=next((group for group in self.config['groups'] if group['id']==group_id),None)
        if group is None: raise ValueError('片源群組不存在。')
        return group
    def create(self,name,kind='media'):
        name=self.validate_name(name)
        group={'id':secrets.token_hex(8),'name':name,'icon':DEFAULT_ICON,'updated':time.time_ns()}
        if kind==WEB_KIND:group['kind']=WEB_KIND
        self.config['groups'].append(group); self.save(self.config); return group
    def validate_name(self,name,ignore=None):
        name=str(name).strip()[:60]
        if not name: raise ValueError('請輸入群組名稱。')
        if any(group['id']!=ignore and group['name'].casefold()==name.casefold() for group in self.config['groups']):
            raise ValueError('已有同名群組。')
        return name
    def rename(self,group_id,name):
        group=self.get(group_id); group['name']=self.validate_name(name,group_id)
        group['updated']=time.time_ns(); self.save(self.config)
    def set_icon(self,group_id,icon):
        if icon not in {entry['id'] for entry in self.catalog()}: raise ValueError('預設頭像不存在。')
        group=self.get(group_id); group['icon']=icon; group.pop('custom_image',None)
        group['updated']=time.time_ns(); self.save(self.config)
    def set_custom(self,group_id,path):
        from PIL import Image,ImageOps
        group=self.get(group_id); folder=self.data_dir/'group-images'; folder.mkdir(parents=True,exist_ok=True)
        filename=secrets.token_hex(16)+'.webp'
        with Image.open(path) as image:
            if image.width*image.height>40000000: raise ValueError('圖片過大，請選擇較小圖片。')
            square=ImageOps.fit(ImageOps.exif_transpose(image).convert('RGBA'),(512,512))
            square.save(folder/filename,'WEBP',quality=90)
        group['custom_image']=filename; group['updated']=time.time_ns(); self.save(self.config)
    def image(self,group_id):
        group=self.get(group_id); custom=group.get('custom_image')
        if custom and Path(custom).name==custom and custom.endswith('.webp'):
            path=self.data_dir/'group-images'/custom
            if path.is_file(): return path
        icon=group.get('icon',DEFAULT_ICON)
        if icon not in {entry['id'] for entry in self.catalog()}: icon=DEFAULT_ICON
        path=self.asset_dir/(icon+'.webp')
        return path if path.is_file() else self.asset_dir.parent/'localcinema-icon.png'
    def delete(self,group_id):
        self.get(group_id)
        if group_id==DEFAULT_GROUP: raise ValueError('預設片源可改名，不能刪除。')
        if any(root.get('group',DEFAULT_GROUP)==group_id for root in self.config.get('roots',[])):
            raise ValueError('請先將此群組的根目錄移到其他群組，再刪除群組。')
        self.config['groups']=[group for group in self.config['groups'] if group['id']!=group_id]
        self.save(self.config)
    def assign(self,indices,group_id):
        if kind_of(self.get(group_id))==WEB_KIND:raise ValueError('作品群組只放網址，不能加入影片根目錄。')
        if any(not isinstance(index,int) or index<0 or index>=len(self.config.get('roots',[])) for index in indices): raise ValueError('片源選取已變更，請重新選取。')
        for index in indices: self.config['roots'][index]['group']=group_id
        self.save(self.config)
    def tag_catalog(self,group_id):
        self.get(group_id)
        return list(self.config['group_categories'].get(group_id,[]))
    def item_tags(self,group_id,item_id):
        self.get(group_id)
        return list(self.config['group_tags'].get(group_id,{}).get(item_id,[]))
    def add_tags(self,group_id,tags,item_id=None):
        self.get(group_id)
        if item_id is not None:self.config['group_tags'].setdefault(group_id,{})[item_id]=list(tags)
        self.config['group_categories'][group_id]=sorted(set(self.tag_catalog(group_id)+tags))
        self.save(self.config)
    def tag_usage(self,group_id,item_ids):
        """How many current items in the group carry each tag; stale item ids are ignored."""
        self.get(group_id);counts={}
        for item_id,tags in self.config['group_tags'].get(group_id,{}).items():
            if item_id in item_ids:
                for tag in set(tags):counts[tag]=counts.get(tag,0)+1
        return counts
    def delete_tag(self,group_id,name):
        """Remove a tag from the group's catalog and from every item in that group."""
        self.get(group_id)
        self.config['group_categories'][group_id]=[tag for tag in self.config['group_categories'].get(group_id,[]) if tag!=name]
        changed=0
        for item_id,tags in self.config['group_tags'].get(group_id,{}).items():
            if name in tags:tags[:]=[tag for tag in tags if tag!=name];changed+=1
        self.save(self.config);return changed
    def prune_tags(self,group_id,names,item_ids):
        """Drop the named tags from the catalog when no current item uses them any more."""
        usage=self.tag_usage(group_id,item_ids);removed=[name for name in names if not usage.get(name)]
        if removed:
            self.config['group_categories'][group_id]=[tag for tag in self.config['group_categories'].get(group_id,[]) if tag not in removed]
            self.save(self.config)
        return removed
    def reorder(self,group_ids):
        """Accept the full order, or one kind's order placed back into that kind's slots."""
        groups=self.config['groups']; ids=[group['id'] for group in groups]
        if len(set(group_ids))!=len(group_ids) or not set(group_ids)<=set(ids):
            raise ValueError('群組清單已變更，請重新拖曳排序。')
        by_id={group['id']:group for group in groups}
        if len(group_ids)!=len(ids):
            kinds={kind_of(by_id[group_id]) for group_id in group_ids}
            subset={group['id'] for group in groups if kind_of(group) in kinds}
            if len(kinds)!=1 or subset!=set(group_ids):raise ValueError('群組清單已變更，請重新拖曳排序。')
            queue=iter(group_ids)
            group_ids=[next(queue) if group_id in subset else group_id for group_id in ids]
        self.config['groups']=[by_id[group_id] for group_id in group_ids]
        self.save(self.config)
    def public(self,items):
        return [{'id':group['id'],'name':group['name'],'kind':kind_of(group),
                 'image':'/group-image/'+group['id']+'?v='+str(group.get('updated',0)),
                 'count':sum(group['id'] in item.get('groups',[DEFAULT_GROUP]) for item in items)}
                for group in self.config['groups']]


def open_group_manager(root,lib,on_change):
    import tkinter as tk
    from tkinter import ttk,simpledialog,filedialog,messagebox
    from PIL import Image,ImageTk
    previous=getattr(root,'group_window',None)
    if previous and previous.winfo_exists(): previous.deiconify(); previous.lift(); return
    window=tk.Toplevel(root); root.group_window=window; window.title('片源群組設定')
    window.configure(bg='#171817'); window.geometry('820x580'); window.minsize(680,460)
    ttk.Label(window,text='片源群組是最上層片單範圍',font=('Microsoft JhengHei UI',16)).pack(anchor='w',padx=16,pady=12)
    ttk.Label(window,text='「新增網路作品」建立只收網址的作品群組，影片目錄改用一般群組。按住群組列上下拖曳即可排序，放開後自動儲存；順序同步至後台分頁與首頁。',wraplength=770).pack(anchor='w',padx=16)
    tree=ttk.Treeview(window,columns=('name','kind','roots'),show='headings',height=8,selectmode='browse')
    tree.heading('name',text='群組名稱');tree.heading('kind',text='類型');tree.heading('roots',text='內容數')
    tree.column('name',width=440);tree.column('kind',width=110,stretch=False);tree.column('roots',width=110,stretch=False)
    tree.pack(fill='both',expand=True,padx=16,pady=12)
    preview=ttk.Label(window);preview.pack(pady=5)
    actions=ttk.Frame(window); actions.pack(fill='x',padx=16,pady=12)
    def selected():
        choice=tree.selection()
        if not choice: raise ValueError('請先選取群組。')
        return choice[0]
    def draw(event=None):
        try:
            with Image.open(lib.source_groups.image(selected())) as image: window.avatar=ImageTk.PhotoImage(image.convert('RGBA').resize((80,80)))
            preview.configure(image=window.avatar)
        except (ValueError,OSError): preview.configure(image='')
    def refresh(group_id=None):
        old=group_id or (tree.selection()[0] if tree.selection() else DEFAULT_GROUP)
        tree.delete(*tree.get_children())
        with lib.lock:
            for group in lib.config['groups']:
                web=kind_of(group)==WEB_KIND
                count=f"{len(lib.web_works.rows(group['id']))} 個網址" if web else f"{sum(r.get('group',DEFAULT_GROUP)==group['id'] for r in lib.config['roots'])} 個目錄"
                tree.insert('','end',iid=group['id'],values=(group['name']+('（隱藏）' if group.get('hidden') else ''),'網路作品' if web else '影片片源',count))
        if tree.exists(old): tree.selection_set(old)
        draw();on_change()
    def run(action):
        try:
            if action in ('new','new-web'):
                web=action=='new-web'
                name=simpledialog.askstring('新增網路作品' if web else '新增片源群組','網路作品群組名稱：' if web else '群組名稱：',parent=window)
                if name is None:return
                with lib.lock: group=lib.source_groups.create(name,WEB_KIND if web else 'media')
                refresh(group['id']);return
            group_id=selected()
            if action=='rename':
                name=simpledialog.askstring('群組改名','群組名稱：',initialvalue=lib.source_groups.get(group_id)['name'],parent=window)
                if name is None:return
                with lib.lock: lib.source_groups.rename(group_id,name)
            elif action=='custom':
                filename=filedialog.askopenfilename(parent=window,title='選擇群組代表圖',filetypes=[('圖片','*.png *.jpg *.jpeg *.webp *.bmp')])
                if not filename:return
                with lib.lock:lib.source_groups.set_custom(group_id,filename)
            elif action=='delete' and kind_of(lib.source_groups.get(group_id))==WEB_KIND:
                group=lib.source_groups.get(group_id);count=len(lib.web_works.rows(group_id))
                if not messagebox.askyesno('刪除作品群組',f'「{group["name"]}」含 {count} 個作品網址，刪除群組會一併移除這些網址與快照（不影響網站本身）。確定繼續？',parent=window):return
                if count and not messagebox.askyesno('再次確認','此操作無法復原。確定刪除群組與全部作品網址？',icon='warning',parent=window):return
                with lib.lock:
                    lib.web_works.delete_group_works(group_id);lib.source_groups.delete(group_id);lib.refresh_web()
            elif action=='delete':
                if not messagebox.askyesno('刪除群組','只刪除群組設定，不刪除影片。確定繼續？',parent=window):return
                with lib.lock:lib.source_groups.delete(group_id)
            refresh()
        except Exception as error:messagebox.showerror('無法更新群組',str(error),parent=window)
    def channel_settings():
        try:group_id=selected();group=lib.source_groups.get(group_id)
        except ValueError as error:messagebox.showinfo('選擇群組',str(error),parent=window);return
        dialog=tk.Toplevel(window);dialog.title('隱藏頻道設定');dialog.configure(bg='#171817');dialog.transient(window)
        hidden=tk.BooleanVar(value=bool(group.get('hidden')));password=tk.StringVar()
        ttk.Label(dialog,text=group['name'],font=('Microsoft JhengHei UI',14)).pack(anchor='w',padx=18,pady=12)
        ttk.Checkbutton(dialog,text='隱藏頻道（前端輸入密碼後才顯示）',variable=hidden).pack(anchor='w',padx=18,pady=8)
        ttk.Label(dialog,text='顯示頻道密碼（4至128字元）').pack(anchor='w',padx=18)
        entry=ttk.Entry(dialog,textvariable=password,show='•',width=38);entry.pack(fill='x',padx=18,pady=8)
        show=tk.BooleanVar();ttk.Checkbutton(dialog,text='顯示本次輸入的密碼',variable=show,command=lambda:entry.configure(show='' if show.get() else '•')).pack(anchor='w',padx=18)
        ttk.Label(dialog,text='已有密碼時留白可沿用；密碼以雜湊保存，不可回讀。\n變更設定會讓已解鎖的瀏覽器重新鎖定。',wraplength=400).pack(anchor='w',padx=18,pady=10)
        def save():
            try:
                with lib.lock:lib.group_access.configure(group_id,hidden.get(),password.get())
                dialog.destroy();refresh(group_id)
            except ValueError as error:messagebox.showerror('無法儲存',str(error),parent=dialog)
        ttk.Button(dialog,text='儲存',command=save).pack(pady=14);dialog.grab_set();entry.focus_set()
    def choose_icon():
        try:group_id=selected()
        except ValueError as error:messagebox.showinfo('選擇群組',str(error),parent=window);return
        picker=tk.Toplevel(window);picker.title('選擇預設分類頭像');picker.geometry('690x620');picker.configure(bg='#171817')
        canvas=tk.Canvas(picker,bg='#171817',highlightthickness=0);bar=ttk.Scrollbar(picker,orient='vertical',command=canvas.yview)
        canvas.configure(yscrollcommand=bar.set);bar.pack(side='right',fill='y');canvas.pack(fill='both',expand=True)
        panel=ttk.Frame(canvas);canvas.create_window((0,0),window=panel,anchor='nw')
        panel.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all')));picker.images=[]
        def apply(icon):
            with lib.lock:lib.source_groups.set_icon(group_id,icon)
            picker.destroy();refresh(group_id)
        for index,entry in enumerate(lib.source_groups.catalog()):
            path=lib.source_groups.asset_dir/(entry['id']+'.webp')
            with Image.open(path) as image:photo=ImageTk.PhotoImage(image.convert('RGBA').resize((78,78)))
            picker.images.append(photo)
            ttk.Button(panel,text=entry['name'],image=photo,compound='top',command=lambda icon=entry['id']:apply(icon)).grid(row=index//6,column=index%6,padx=5,pady=5)
        picker.transient(window);picker.grab_set()
    for text,action in [('新增群組','new'),('新增網路作品','new-web'),('改名','rename'),('自訂代表圖','custom'),('刪除群組','delete')]:
        ttk.Button(actions,text=text,command=lambda a=action:run(a)).pack(side='left',padx=3)
    ttk.Button(actions,text='隱藏頻道／密碼',command=channel_settings).pack(side='left',padx=3)
    ttk.Button(actions,text='頭像設定',command=choose_icon).pack(side='left',padx=3)
    drag={'id':None,'y':0,'moving':False}
    def drag_start(event):
        row=tree.identify_row(event.y) if tree.identify_region(event.x,event.y) in ('cell','tree') else ''
        drag.update(id=row or None,y=event.y,moving=False)
    def drag_move(event):
        source=drag['id']
        if not source or not tree.exists(source):return
        if not drag['moving'] and abs(event.y-drag['y'])<5:return
        drag['moving']=True;tree.configure(cursor='fleur')
        if event.y<30:tree.yview_scroll(-1,'units')
        elif event.y>tree.winfo_height()-24:tree.yview_scroll(1,'units')
        target=tree.identify_row(event.y)
        if target and target!=source:
            tree.move(source,'',tree.index(target));tree.selection_set(source)
        return 'break'
    def drag_end(event):
        moved=drag['moving'];source=drag['id']
        drag.update(id=None,moving=False);tree.configure(cursor='')
        if not moved:return
        try:
            with lib.lock:lib.source_groups.reorder(list(tree.get_children()))
            refresh(source)
        except Exception as error:
            refresh(source);messagebox.showerror('無法儲存排序',str(error),parent=window)
        return 'break'
    tree.bind('<ButtonPress-1>',drag_start)
    tree.bind('<B1-Motion>',drag_move)
    tree.bind('<ButtonRelease-1>',drag_end)
    tree.bind('<<TreeviewSelect>>',draw);refresh()
