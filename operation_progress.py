"""Thread-safe latest-only progress; never stores filenames or library paths."""
import threading

class OperationProgress:
    def __init__(self):
        self.lock=threading.Lock();self.value={'phase':'待命','index':0,'total':0,'done':0,'size':0}
    def update(self,phase,index=0,total=0,done=0,size=0):
        with self.lock:self.value=dict(phase=phase,index=index,total=total,done=done,size=size)
    def snapshot(self):
        with self.lock:return dict(self.value)

def report(callback,phase,index=0,total=0,done=0,size=0):
    if callback:callback(phase,index,total,done,size)

def tracked_hash(hash_function,path,callback,phase,index=0,total=0):
    if not callback:return hash_function(path)
    return hash_function(path,lambda done,size:report(callback,phase,index,total,done,size))

def parse_duration(text):
    import re
    match=re.search(r'Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)',text)
    if not match:return None
    hours,minutes,seconds=map(float,match.groups());value=hours*3600+minutes*60+seconds
    return value if value>0 else None

def parse_encode_progress(line,duration):
    name,separator,value=line.strip().partition('=')
    if name!='out_time_us' or not separator:return None
    try:seconds=max(0,float(value)/1000000)
    except ValueError:return None
    return {'seconds':seconds,'duration':duration,'percent':min(99.9,seconds/duration*100) if duration else None}
