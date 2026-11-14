import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
if '--self-test' in sys.argv:
    import os,tempfile,json,subprocess,traceback
    report=Path(sys.argv[sys.argv.index('--self-test')+1]).resolve()
    result={}
    try:
        with tempfile.TemporaryDirectory(prefix='LocalCinema-test-') as isolated:
            os.environ['LOCALAPPDATA']=isolated
            import cinema
            import pystray,send2trash,win32com.shell.shell
            import imageio_ffmpeg, qrcode
            from PIL import Image
            import tkinter
            for name in ['index.html','assets/localcinema.ico','assets/bitingbox-studio.png','assets/group-icons/catalog.json']:
                assert (cinema.BASE/name).is_file(),name
            assert 'id="rescan"' not in (cinema.BASE/'index.html').read_text('utf-8')
            lib=cinema.Library(lambda message:None,config={'roots':[],'tags':{},'categories':[]})
            assert lib.public()['items']==[]
            lib.shutdown()
            run=subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(),'-version'],capture_output=True,creationflags=0x08000000)
            assert run.returncode==0
            assert qrcode.make('http://127.0.0.1:8765/?access=synthetic-test').size[0]>0
            result={'ok':True,'frozen':bool(getattr(sys,'frozen',False)),'ffmpeg':run.stdout.decode().splitlines()[0],'assets':True,'isolated_database':True,'dependencies':True}
    except Exception:
        result={'ok':False,'error':traceback.format_exc()}
    report.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    sys.exit(0 if result.get('ok') else 1)
def repair_guide(error):
    import ctypes
    text=('程式元件缺失或無法載入，請重新執行 LocalCinema 安裝程式 修復安裝。\n'
          '安裝包已內建所需元件，不必另外安裝 Python 或插件；既有個人設定與觀看記錄會保留。\n\n'
          '缺少或異常項目：'+str(error)+'\n\n是否開啟安裝修復說明？')
    if ctypes.windll.user32.MessageBoxW(None,text,'LocalCinema｜安裝修復',0x24)==6:
        import os
        guide=Path(sys.executable).parent/'安裝修復說明.txt' if getattr(sys,'frozen',False) else Path(__file__).parent/'安裝修復說明.txt'
        if guide.is_file():os.startfile(str(guide))
try:
    import pystray,send2trash,win32com.shell.shell
    from PIL import Image
    import imageio_ffmpeg, qrcode
    assets=Path(__file__).resolve().parent
    for required in ['index.html','assets/localcinema.ico','assets/bitingbox-studio.png','assets/group-icons/catalog.json','assets/playback-modes.js','assets/short-queue.js','assets/interaction-controls.js','assets/catalog-pagination.js','assets/studio-layout.css','assets/studio-navigation.js']:
        if not (assets/required).is_file():raise FileNotFoundError(required)
    if not Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file():raise FileNotFoundError('FFmpeg')
    from cinema import main
except (ImportError,OSError,RuntimeError) as error:
    repair_guide(error)
    sys.exit(1)
main()
