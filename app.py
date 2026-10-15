#!/usr/bin/env python3
"""Local MuseScore → YouTube workbench. Python standard library only."""
import base64, calendar, copy, hashlib, html, json, mimetypes, os, pathlib, queue, re, secrets, shutil, subprocess, threading, time, urllib.error, urllib.parse, urllib.request, webbrowser, zipfile
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from discovery import DIRECT, discover, xml_data, title_matches

ROOT = pathlib.Path(__file__).resolve().parent
DATA = ROOT / '.data'
DATA.mkdir(exist_ok=True, mode=0o700)
VIDEOS = ROOT / 'Videos'
VIDEOS.mkdir(exist_ok=True)
DEFAULT = str(pathlib.Path.home() / 'Music/Scores')
MUSE = '/Applications/MuseScore 4.app/Contents/MacOS/mscore'
LOCK = threading.RLock()
CSRF = secrets.token_urlsafe(32)
JOBS = queue.Queue()
BUSY = set()
OAUTH = {}
STOP = threading.Event()

def load(path, default):
    try: return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError): return default

STATE = load(DATA / 'state.json', {'folder': DEFAULT, 'pieces': {}})
CHANNEL = load(DATA / 'channel.json', {})
CHANNEL_STATUS = {'busy':False,'error':''}
SUGGESTIONS = load(DATA / 'suggestions.json', {'folder':str(pathlib.Path(DEFAULT).parents[1]),'files':[]})

def atomic(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False))
    tmp.chmod(0o600)
    tmp.replace(path)

def save():
    with LOCK: atomic(DATA / 'state.json', STATE)

def month(value):
    if not re.fullmatch(r'\d{4}-(0[1-9]|1[0-2])', value or ''): raise ValueError('Choose the composition month and year first.')
    year, mo = map(int, value.split('-'))
    if year < 1: raise ValueError('Choose a valid year.')
    return f'Written in {calendar.month_name[mo]} {year}'

def metadata(path):
    return xml_data(path)

def scan(folder):
    folder = pathlib.Path(folder).expanduser().resolve()
    if not folder.is_dir(): raise ValueError('That folder does not exist.')
    rows = []
    for path in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        if path.suffix.lower() not in DIRECT or path.name.startswith('.'): continue
        ident = hashlib.sha256(str(path).encode()).hexdigest()[:24]
        try:
            tags, digest = metadata(path)
            date = (tags.get('creationDate') or '')[:7]
            try: month(date)
            except ValueError: date = ''
            base = {'id': ident, 'path': str(path), 'filename': path.name, 'title': path.stem, 'composer': tags.get('composer') or 'Unknown composer', 'month': date, 'dateSource': 'Score creation date' if date else 'Date needed', 'hash': digest, 'selected': False, 'status': 'Not prepared', 'error': ''}
            with LOCK:
                old = STATE['pieces'].get(ident, {})
                if old.get('hash') == digest:
                    base.update({k: old[k] for k in ('title','month','selected','order','checkedMatches','status','error','video','youtube','session','uploadMeta') if k in old})
                    if (base['status'] in ('Rendering', 'Encoding video', 'Queued') or base['status'].startswith('Uploading')) and ident not in BUSY: base['status'] = 'Interrupted — retry'
                elif old.get('youtube'):
                    base['youtube'] = old['youtube']
                    base['status'] = 'Score changed after upload'
                STATE['pieces'][ident] = base
                rows.append(copy.deepcopy(base))
        except Exception as e:
            rows.append({'id': ident, 'filename': path.name, 'title': path.stem, 'composer': '', 'month': '', 'selected': False, 'status': 'Cannot read score', 'error': str(e)})
    counts = {}
    for r in rows:
        if r.get('hash'): counts[r['hash']] = counts.get(r['hash'], 0) + 1
    for r in rows: r['duplicate'] = counts.get(r.get('hash'), 0) > 1
    with LOCK:
        STATE['folder'] = str(folder)
        save()
    return rows

def update(ident, **values):
    with LOCK:
        STATE['pieces'][ident].update(values)
        save()

def video_path(row):
    return VIDEOS / (row['id'] + '-' + row['hash'][:12] + '.mp4')

def validate_video(path):
    probe = shutil.which('ffprobe') or '/opt/homebrew/bin/ffprobe'
    result = subprocess.run([probe, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)], capture_output=True, timeout=30)
    info = json.loads(result.stdout or '{}')
    types = {s['codec_type'] for s in info.get('streams', [])}
    if result.returncode or not {'audio','video'} <= types or float(info.get('format', {}).get('duration',0)) <= 0:
        raise ValueError('The exported file must contain both video and audio.')

def render(row):
    """Render timed score systems with measure highlights; no native MP4 dependency."""
    import struct
    target = video_path(row)
    if target.exists():
        validate_video(target)
        update(row['id'], video=str(target), status='Ready', error='')
        return
    work = DATA / ('render-' + row['id'] + '-' + row['hash'][:12])
    work.mkdir(exist_ok=True)
    partial = target.with_name(target.stem + '.partial.mp4')
    log = DATA / (row['id'] + '.log')
    env = dict(os.environ)
    env['PATH'] = '/opt/homebrew/bin:/usr/local/bin:' + env.get('PATH','')
    ffmpeg = shutil.which('ffmpeg', path=env['PATH'])
    ffprobe = shutil.which('ffprobe', path=env['PATH'])
    if not ffmpeg or not ffprobe: raise ValueError('Install FFmpeg to prepare videos.')
    update(row['id'], status='Rendering', error='')
    def run(cmd):
        if STOP.is_set(): raise ValueError('Stopped. Retry to prepare this video.')
        with log.open('a') as out:
            result = subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT, env=env, timeout=7200)
        return result.returncode
    audio, positions = work / 'audio.mp3', work / 'score.mpos'
    # Each export is isolated; certain MuseScore builds crash during batch teardown.
    if not audio.exists():
        run([MUSE, '--sound-profile', 'MuseScore Basic', '-o', str(audio), row['path']])
    if not positions.exists(): run([MUSE, '-r', '150', '-o', str(positions), row['path']])
    if not (work/'page-1.png').exists(): run([MUSE, '-r', '150', '-o', str(work/'page.png'), row['path']])
    if not audio.exists() or not positions.exists() or not (work/'page-1.png').exists():
        raise ValueError('MuseScore could not export audio, score pages, or timing. Export an MP4 in MuseScore and attach it in Preview. See ' + log.name)
    probe = subprocess.run([ffprobe,'-v','error','-show_entries','format=duration','-of','json',str(audio)],capture_output=True,timeout=30)
    duration = float(json.loads(probe.stdout)['format']['duration'])
    root = ET.parse(positions).getroot()
    elements = {el.get('id'):el.attrib for el in root.findall('./elements/element')}
    events = [(float(el.get('position'))/1000, elements[el.get('elid')]) for el in root.findall('./events/event')]
    events.sort(key=lambda e:e[0])
    if not events: raise ValueError('This score has no playback timing data.')
    # Group measures sharing a system; the events include played repeats.
    segments = []
    for start, el in events:
        key = (int(el['page']), round(float(el['y']),1))
        if not segments or segments[-1]['key'] != key:
            segments.append({'key':key,'start':start,'events':[]})
        segments[-1]['events'].append((start,el))
    segments[0]['start'] = 0
    filters = []
    concat = []
    with log.open('w') as out: out.write('Score-system renderer · MuseScore Basic audio\n')
    for i,seg in enumerate(segments):
        page,y = seg['key']
        source = work / f'page-{page+1}.png'
        with source.open('rb') as f:
            header=f.read(24)
        width,height=struct.unpack('>II',header[16:24])
        # Position export uses twelve coordinate units per pixel at the chosen DPI.
        ratio=1/12
        top = 0 if page==0 and y==segments[0]['key'][1] else max(0,int(y*ratio)-85)
        bottom=min(height,int(max(float(el['y'])+float(el['sy']) for _,el in seg['events'])*ratio)+100)
        cropheight=max(2,bottom-top)
        scale=min(1800/width,900/cropheight)
        outw=max(2,int(width*scale)//2*2)
        outh=max(2,int(cropheight*scale)//2*2)
        image=work/f'system-{i}.png'
        vf=f'crop={width}:{cropheight}:0:{top},scale={outw}:{outh},pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=white,setsar=1'
        if run([ffmpeg,'-v','error','-y','-i',str(source),'-vf',vf,'-frames:v','1',str(image)]): raise ValueError('Could not render a score system. See '+log.name)
        end=segments[i+1]['start'] if i+1<len(segments) else duration
        if end <= seg['start']: raise ValueError('Invalid score timing.')
        concat.extend([f"file '{image.name}'",f"duration {end-seg['start']:.6f}"])
        for j,(start,el) in enumerate(seg['events']):
            stop=seg['events'][j+1][0] if j+1<len(seg['events']) else end
            x=(1920-outw)/2+float(el['x'])*ratio*outw/width
            yy=(1080-outh)/2+(float(el['y'])*ratio-top)*outh/cropheight
            w=float(el['sx'])*ratio*outw/width
            h=float(el['sy'])*ratio*outh/cropheight
            filters.append(f"drawbox=x={x:.2f}:y={yy:.2f}:w={w:.2f}:h={h:.2f}:color=0x3d7eaa@0.6:t=3:enable='gte(t,{start:.6f})*lt(t,{stop:.6f})'")
    concat.append(f"file 'system-{len(segments)-1}.png'")
    playlist=work/'timeline.txt';playlist.write_text('\n'.join(concat)+'\n')
    filterfile=work/'filters.txt';filterfile.write_text(','.join(filters))
    update(row['id'],status='Encoding video')
    code=run([ffmpeg,'-v','error','-y','-f','concat','-safe','1','-i',str(playlist),'-i',str(audio),'-/filter:v',str(filterfile),'-r','24','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-c:a','aac','-b:a','192k','-t',str(duration),'-movflags','+faststart',str(partial)])
    if code: raise ValueError('Video encoding failed. See '+log.name)
    validate_video(partial)
    if metadata(pathlib.Path(row['path']))[1] != row['hash']:
        partial.unlink(missing_ok=True)
        raise ValueError('The score changed during rendering. Refresh the folder and prepare it again.')
    partial.replace(target)
    update(row['id'],video=str(target),status='Ready',error='')
    shutil.rmtree(work)

def request(url, data=None, headers=None, method=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as res: return res.status, dict(res.headers), res.read()
    except urllib.error.HTTPError as e:
        if e.code == 308: return 308, dict(e.headers), e.read()
        detail = e.read().decode(errors='replace')
        raise ValueError(f'Google returned {e.code}: {detail[:500]}') from None

def client():
    obj = load(DATA / 'client.json', {})
    if 'installed' not in obj: raise ValueError('Add your Google Desktop app credentials first. See the setup guide.')
    return obj['installed']

def token_form(values):
    return json.loads(request('https://oauth2.googleapis.com/token', urllib.parse.urlencode(values).encode(), {'Content-Type':'application/x-www-form-urlencoded'})[2])

def access():
    t = load(DATA / 'token.json', {})
    if not t: raise ValueError('Connect your YouTube account first.')
    if t.get('expires_at',0) < time.time() + 60:
        c = client()
        fresh = token_form({'client_id':c['client_id'], 'client_secret':c.get('client_secret',''), 'refresh_token':t.get('refresh_token',''), 'grant_type':'refresh_token'})
        t.update(fresh)
        t['expires_at'] = time.time() + t.get('expires_in',3600)
        atomic(DATA / 'token.json', t)
    return t['access_token']

def upload(row, privacy, kids):
    ident = row['id']
    if row.get('youtube'): raise ValueError('This piece already has a YouTube video. Open the saved link.')
    if metadata(pathlib.Path(row['path']))[1] != row['hash']: raise ValueError('The score changed. Refresh and prepare it again.')
    path = video_path(row)
    validate_video(path)
    desc = month(row['month'])
    if not row['title'].strip() or len(row['title']) > 100 or any(c in row['title'] for c in '<>'): raise ValueError('YouTube titles must be 1–100 characters, without < or >.')
    meta = {'snippet': {'title':row['title'], 'description':desc, 'categoryId':'10'}, 'status': {'privacyStatus':privacy, 'selfDeclaredMadeForKids':kids}}
    size = path.stat().st_size
    headers = {'Authorization':'Bearer ' + access()}
    session = row.get('session')
    if session and row.get('uploadMeta') != meta: raise ValueError('An interrupted upload has different title, date, or visibility. Restore its previous settings to resume.')
    if not session:
        _, h, _ = request('https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status', json.dumps(meta).encode(), {**headers,'Content-Type':'application/json; charset=UTF-8','X-Upload-Content-Length':str(size),'X-Upload-Content-Type':'video/mp4'}, 'POST')
        session = h.get('Location') or h.get('location')
        if not session or urllib.parse.urlparse(session).scheme != 'https': raise ValueError('Google did not return an upload session.')
        update(ident, session=session, uploadMeta=meta)
    # Query before sending or resuming: prevents duplicates after a lost final response.
    status, h, body = request(session, b'', {**headers,'Content-Length':'0','Content-Range':f'bytes */{size}'}, 'PUT')
    if status in (200,201):
        result = json.loads(body)
        update(ident, youtube=result['id'], session=None, status='Uploaded', error='')
        return
    offset = int((h.get('Range') or h.get('range') or 'bytes=0--1').split('-')[-1]) + 1 if (h.get('Range') or h.get('range')) else 0
    with path.open('rb') as f:
        f.seek(offset)
        while offset < size:
            if STOP.is_set(): raise ValueError('Stopped. Upload progress was saved; retry to resume.')
            block = f.read(8*1024*1024)
            end = offset + len(block) - 1
            update(ident, status=f'Uploading {int(offset/size*100)}%')
            headers = {'Authorization':'Bearer ' + access()}
            status, h, body = request(session, block, {**headers,'Content-Type':'video/mp4','Content-Length':str(len(block)),'Content-Range':f'bytes {offset}-{end}/{size}'}, 'PUT')
            if status in (200,201):
                result = json.loads(body)
                update(ident, youtube=result['id'], session=None, status='Uploaded', error='')
                return
            if status != 308: raise ValueError('Unexpected upload response. Retry to resume.')
            acknowledged = h.get('Range') or h.get('range')
            offset = int(acknowledged.split('-')[-1]) + 1 if acknowledged else 0
            f.seek(offset)
    raise ValueError('Upload completion is unconfirmed. Retry to check its saved session.')

def sync_channel():
    global CHANNEL
    try:
        def get(resource,**params):
            url='https://www.googleapis.com/youtube/v3/'+resource+'?'+urllib.parse.urlencode(params)
            return json.loads(request(url,headers={'Authorization':'Bearer '+access()})[2])
        channels=get('channels',part='snippet,contentDetails',mine='true').get('items',[])
        if len(channels)!=1: raise ValueError('Sign in to exactly one YouTube channel, then check again.')
        channel=channels[0];playlist=channel['contentDetails']['relatedPlaylists']['uploads']
        videos=[];page=''
        while True:
            result=get('playlistItems',part='snippet,contentDetails',playlistId=playlist,maxResults=50,**({'pageToken':page} if page else {}))
            for item in result.get('items',[]):
                snippet=item['snippet'];vid=item.get('contentDetails',{}).get('videoId')
                if vid and snippet.get('title') not in ('Deleted video','Private video'): videos.append({'id':vid,'title':snippet['title']})
            page=result.get('nextPageToken','')
            if not page:break
        complete={'id':channel['id'],'title':channel['snippet']['title'],'checkedAt':time.time(),'videos':videos}
        with LOCK:
            atomic(DATA/'channel.json',complete);CHANNEL=complete
    except Exception as e:
        CHANNEL_STATUS['error']=str(e)+' If access is denied, reconnect Google to grant read access to your uploads.'
    finally: CHANNEL_STATUS['busy']=False

def channel_info(row):
    matches=title_matches(row,CHANNEL.get('videos',[]))
    ids=sorted(m['id'] for m in matches)
    return {'matches':matches,'checked':bool(CHANNEL.get('checkedAt')),'reviewed':bool(ids) and ids==sorted(row.get('checkedMatches',[]))}

def worker():
    while True:
        kind, row, options = JOBS.get()
        try:
            if STOP.is_set(): update(row['id'], status='Stopped', error='')
            elif kind == 'render': render(row)
            else: upload(row, **options)
        except Exception as e:
            update(row['id'], status='Needs attention', error=str(e))
            if kind == 'upload': STOP.set()
        finally:
            with LOCK: BUSY.discard(row['id'])
            JOBS.task_done()

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args): pass
    def respond(self, value, status=200, typ='application/json'):
        data = json.dumps(value, ensure_ascii=False).encode() if typ == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type',typ)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.end_headers()
        self.wfile.write(data)
    def guard(self, mutation=False):
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}': raise ValueError('Invalid host.')
        if mutation and not secrets.compare_digest(self.headers.get('X-CSRF-Token',''),CSRF): raise ValueError('Refresh the app and try again.')
    def do_GET(self):
        global CHANNEL
        try:
            self.guard()
            url = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(url.query)
            if url.path == '/':
                page = (ROOT / 'index.html').read_text().replace('__CSRF__', CSRF)
                self.respond(page.encode(), typ='text/html; charset=utf-8')
            elif url.path == '/api/state':
                with LOCK:
                    folder = STATE['folder']
                    rows = [copy.deepcopy(v) for v in STATE['pieces'].values() if str(pathlib.Path(v['path']).parent) == folder and pathlib.Path(v['path']).exists()]
                    counts = {}
                    for r in rows: counts[r['hash']] = counts.get(r['hash'],0)+1
                    for r in rows:
                        r['duplicate'] = counts[r['hash']] > 1
                        r['channelCheck']=channel_info(r)
                self.respond({'folder':folder,'pieces':rows,'connected':(DATA/'token.json').exists(),'configured':(DATA/'client.json').exists(),'busy':len(BUSY),'stopping':STOP.is_set(),'channel':{k:v for k,v in CHANNEL.items() if k!='videos'},'channelStatus':CHANNEL_STATUS,'channelCount':len(CHANNEL.get('videos',[]))})
            elif url.path == '/api/suggestions':
                self.respond(SUGGESTIONS)
            elif url.path == '/oauth/callback':
                if not OAUTH or time.time() - OAUTH['time'] > 600 or not secrets.compare_digest(q.get('state',[''])[0],OAUTH['state']): raise ValueError('Google sign-in expired. Connect again.')
                if 'error' in q: raise ValueError('Google sign-in was cancelled.')
                c = client()
                t = token_form({'client_id':c['client_id'],'client_secret':c.get('client_secret',''),'code':q['code'][0],'code_verifier':OAUTH['verifier'],'redirect_uri':OAUTH['redirect'],'grant_type':'authorization_code'})
                t['expires_at'] = time.time() + t.get('expires_in',3600)
                atomic(DATA/'token.json',t)
                OAUTH.clear()
                with LOCK:
                    CHANNEL={};atomic(DATA/'channel.json',{})
                CHANNEL_STATUS.update(busy=True,error='')
                threading.Thread(target=sync_channel,daemon=True).start()
                self.send_response(303)
                self.send_header('Location','/')
                self.end_headers()
            elif url.path in ('/thumbnail','/video'):
                with LOCK: row = copy.deepcopy(STATE['pieces'][q['id'][0]])
                if url.path == '/thumbnail':
                    if pathlib.Path(row['path']).suffix.lower() != '.mscz': self.send_error(404); return
                    with zipfile.ZipFile(row['path']) as z: data = z.read('Thumbnails/thumbnail.png')
                    self.respond(data,typ='image/png')
                else: self.serve_video(video_path(row))
            else: self.send_error(404)
        except (BrokenPipeError, ConnectionResetError): pass
        except Exception as e: self.respond({'error':str(e)},400)
    def serve_video(self,path):
        size = path.stat().st_size
        start,end = 0,size-1
        ran = self.headers.get('Range')
        if ran:
            m = re.fullmatch(r'bytes=(\d*)-(\d*)',ran)
            if not m or not any(m.groups()): self.send_error(416); return
            a,b = m.groups()
            if a: start,end=int(a),min(int(b) if b else end,end)
            else: start=max(0,size-int(b))
            if start > end or start >= size: self.send_error(416); return
        self.send_response(206 if ran else 200)
        self.send_header('Content-Type','video/mp4')
        self.send_header('Accept-Ranges','bytes')
        self.send_header('Content-Length',str(end-start+1))
        if ran: self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        with path.open('rb') as f:
            f.seek(start)
            remaining=end-start+1
            while remaining:
                data=f.read(min(1024*1024,remaining))
                if not data: break
                self.wfile.write(data); remaining-=len(data)
    def do_POST(self):
        try:
            self.guard(True)
            length=int(self.headers.get('Content-Length',0))
            if length > 1_000_000: raise ValueError('Request too large.')
            body=json.loads(self.rfile.read(length) or '{}')
            global SUGGESTIONS
            route=urllib.parse.urlparse(self.path).path
            if route == '/api/discover':
                with LOCK: known=[p['path'] for p in STATE['pieces'].values()]
                result=discover(body['folder'],known)
                with LOCK:
                    atomic(DATA/'suggestions.json',result);SUGGESTIONS=result
                self.respond(result);return
            if route == '/api/sync-channel':
                if CHANNEL_STATUS['busy']: raise ValueError('A channel check is already running.')
                if BUSY: raise ValueError('Wait for your batch before checking the channel.')
                access()
                CHANNEL_STATUS.update(busy=True,error='')
                threading.Thread(target=sync_channel,daemon=True).start()
                self.respond({'ok':True});return
            if route == '/api/open-found':
                item=next((r for r in SUGGESTIONS.get('files',[]) if r['path']==body.get('path')),None)
                if not item: raise ValueError('Run the search again to locate this file.')
                app='Sibelius' if item['format']=='SIB' else 'MuseScore 4'
                subprocess.Popen(['open','-a',app,item['path']])
                self.respond({'ok':True});return
            if route == '/api/scan':
                if BUSY: raise ValueError('Wait for the current batch before changing folders or refreshing.')
                self.respond({'pieces':scan(body.get('folder',STATE['folder']))}); return
            if route == '/api/choose-folder':
                result=subprocess.run(['osascript','-e','POSIX path of (choose folder with prompt "Choose your MuseScore pieces folder")'],capture_output=True,text=True,timeout=120)
                if result.returncode: raise ValueError('Folder selection cancelled.')
                self.respond({'folder':result.stdout.strip()}); return
            if route == '/api/save':
                with LOCK:
                    for patch in body['pieces']:
                        ident=patch['id']
                        if ident in BUSY: raise ValueError('Wait until this piece finishes processing before editing it.')
                        row=STATE['pieces'][ident]
                        for k in ('title','month','selected','checkedMatches'):
                            if k in patch:
                                if k=='selected' and not isinstance(patch[k],bool): raise ValueError('Invalid selection.')
                                if k=='checkedMatches' and (not isinstance(patch[k],list) or not all(isinstance(x,str) for x in patch[k])): raise ValueError('Invalid match review.')
                                if k not in ('selected','checkedMatches') and not isinstance(patch[k],str): raise ValueError('Invalid text.')
                                if k=='selected' and patch[k] and not row.get('selected'):
                                    row['order']=1+max((p.get('order',0) for p in STATE['pieces'].values()),default=0)
                                row[k]=patch[k]
                    save()
            elif route == '/api/order':
                with LOCK:
                    if BUSY: raise ValueError('Wait for the current batch before changing upload order.')
                    ids=body['ids']
                    expected={p['id'] for p in STATE['pieces'].values() if p.get('selected') and str(pathlib.Path(p['path']).parent)==STATE['folder'] and pathlib.Path(p['path']).exists()}
                    if not isinstance(ids,list) or len(ids)!=len(set(ids)) or set(ids)!=expected: raise ValueError('Selection changed. Refresh and reorder the current batch.')
                    for rank,ident in enumerate(ids): STATE['pieces'][ident]['order']=rank+1
                    save()
            elif route in ('/api/render','/api/upload'):
                ids=list(dict.fromkeys(body['ids']))
                if not ids: raise ValueError('Select at least one piece.')
                rows=[]
                with LOCK:
                    for ident in ids:
                        row=copy.deepcopy(STATE['pieces'][ident])
                        if ident in BUSY: raise ValueError('This piece is already in the queue.')
                        if str(pathlib.Path(row['path']).parent)!=STATE['folder']: raise ValueError('This piece is in another folder.')
                        if metadata(pathlib.Path(row['path']))[1]!=row['hash']: raise ValueError('A score changed. Refresh the folder first.')
                        if route.endswith('upload'):
                            month(row['month'])
                            if row.get('youtube'): raise ValueError('A selected piece is already uploaded.')
                            check=channel_info(row)
                            if check['matches'] and not check['reviewed']: raise ValueError('Review the possible YouTube matches in Preview before uploading '+row['title'])
                            if any(p.get('youtube') and p.get('hash') == row['hash'] for p in STATE['pieces'].values()): raise ValueError('An identical copy of a selected piece is already uploaded.')
                            if any(p['hash'] == row['hash'] for p in rows): raise ValueError('Two selected pieces are exact duplicates. Select only one copy.')
                            if not video_path(row).exists(): raise ValueError('Prepare all selected videos first.')
                        rows.append(row)
                    if route.endswith('upload'):
                        if body.get('confirmed') is not True: raise ValueError('Review the batch before uploading.')
                        if body.get('privacy') not in ('private','unlisted','public') or not isinstance(body.get('kids'),bool): raise ValueError('Choose visibility and audience.')
                        access()
                    STOP.clear()
                    for row in rows:
                        BUSY.add(row['id'])
                        update(row['id'],status='Queued',error='')
                        JOBS.put(('upload' if route.endswith('upload') else 'render',row,{'privacy':body['privacy'],'kids':body['kids']} if route.endswith('upload') else {}))
            elif route == '/api/stop': STOP.set()
            elif route == '/api/import':
                row=copy.deepcopy(STATE['pieces'][body['id']])
                if row['id'] in BUSY or row.get('youtube') or row.get('session'): raise ValueError('Cannot replace a video while it is processing or has an upload record.')
                source=pathlib.Path(body['path']).expanduser().resolve()
                if source.suffix.lower()!='.mp4': raise ValueError('Choose an MP4 file.')
                validate_video(source)
                target=video_path(row)
                if source!=target.resolve(): shutil.copyfile(source,target)
                update(row['id'],video=str(target),status='Ready',error='')
            elif route == '/api/open-score':
                row=STATE['pieces'][body['id']]
                subprocess.Popen(['open','-a','MuseScore 4',row['path']])
            elif route == '/api/client':
                obj=body['credentials']
                if 'installed' not in obj or not obj['installed'].get('client_id'): raise ValueError('Choose credentials for a Google Desktop app.')
                atomic(DATA/'client.json',obj)
            elif route == '/api/connect':
                c=client()
                verifier=secrets.token_urlsafe(64)
                OAUTH.update(state=secrets.token_urlsafe(32),verifier=verifier,redirect=f'http://127.0.0.1:{self.server.server_port}/oauth/callback',time=time.time())
                params={'client_id':c['client_id'],'redirect_uri':OAUTH['redirect'],'response_type':'code','scope':'https://www.googleapis.com/auth/youtube.upload https://www.googleapis.com/auth/youtube.readonly','access_type':'offline','prompt':'consent','state':OAUTH['state'],'code_challenge':base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('='),'code_challenge_method':'S256'}
                self.respond({'url':'https://accounts.google.com/o/oauth2/v2/auth?'+urllib.parse.urlencode(params)}); return
            else: self.send_error(404); return
            self.respond({'ok':True})
        except Exception as e: self.respond({'error':str(e)},400)

def main():
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--no-browser',action='store_true')
    args=parser.parse_args()
    try:
        server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    except OSError:
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/state',timeout=3) as response:
                existing=json.load(response)
            if 'pieces' not in existing: raise ValueError('Another app is using this port.')
            webbrowser.open(f'http://127.0.0.1:{args.port}')
            return
        except Exception:
            raise SystemExit('This port is in use. Start with --port 8766 to use a different port.')
    try: scan(STATE['folder'])
    except (ValueError, OSError): pass
    threading.Thread(target=worker,daemon=True).start()
    url=f'http://127.0.0.1:{server.server_port}'
    print(f'Score Publisher is open at {url}\nKeep this window open. Press Control-C to stop.',flush=True)
    if not args.no_browser: webbrowser.open(url)
    try: server.serve_forever()
    except KeyboardInterrupt: server.server_close()

if __name__=='__main__': main()
