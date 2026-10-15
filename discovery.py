"""Read-only score discovery and conservative YouTube title matching."""
import difflib, hashlib, os, pathlib, re, unicodedata, xml.etree.ElementTree as ET, zipfile
DIRECT = {'.mscz', '.mscx', '.musicxml', '.mxl', '.xml'}
FOUND = DIRECT | {'.sib', '.mid', '.midi', '.musescore'}
SKIP = {'backup scores', 'backups', 'backup', 'node_modules', 'videos', 'outputs', 'work', 'autosave', 'auto-save'}

def xml_data(path):
    path=pathlib.Path(path)
    if path.suffix.lower() in ('.mscz','.mxl'):
        with zipfile.ZipFile(path) as z:
            if path.suffix.lower()=='.mscz': name=next(n for n in z.namelist() if n.lower().endswith('.mscx'))
            else:
                container=ET.fromstring(z.read('META-INF/container.xml'))
                name=next(x.get('full-path') for x in container.iter() if x.tag.split('}')[-1]=='rootfile' and x.get('full-path'))
            if z.getinfo(name).file_size>50_000_000: raise ValueError('Score XML is too large.')
            raw=z.read(name)
    else:
        if path.stat().st_size>50_000_000: raise ValueError('Score XML is too large.')
        raw=path.read_bytes()
    root=ET.fromstring(raw)
    kind=root.tag.split('}')[-1]
    if kind=='museScore': tags={x.get('name'):''.join(x.itertext()).strip() for x in root.iter('metaTag')}
    elif kind in ('score-partwise','score-timewise'):
        tags={'composer':next((''.join(x.itertext()).strip() for x in root.iter() if x.tag.split('}')[-1]=='creator' and x.get('type')=='composer'),'')}
        # MusicXML encoding-date is an export date, not a composition date.
    else: raise ValueError('This XML file is not a MuseScore or MusicXML score.')
    return tags,hashlib.sha256(raw).hexdigest()

def discover(folder,known=()):
    folder=pathlib.Path(folder).expanduser().resolve()
    if not folder.is_dir(): raise ValueError('Choose an existing folder to search.')
    known=set(known);rows=[];errors=[];visited=0;truncated=False
    def error(e): errors.append(str(e))
    for parent,dirs,files in os.walk(folder,followlinks=False,onerror=error):
        dirs[:]=sorted(d for d in dirs if not d.startswith('.') and d.casefold() not in SKIP and not pathlib.Path(parent,d).is_symlink())
        for name in sorted(files):
            visited+=1
            if visited>50000 or len(rows)>=3000: truncated=True;break
            path=pathlib.Path(parent,name);ext=path.suffix.lower()
            if name.startswith('.') or ext not in FOUND or path.is_symlink(): continue
            if ext=='.xml':
                try:xml_data(path)
                except (ValueError,ET.ParseError,OSError):continue
            direct=ext in DIRECT
            reason='Ready to import' if direct else 'Export MusicXML in Sibelius first' if ext=='.sib' else 'Open in MuseScore and save as MSCZ first' if ext in ('.mid','.midi') else 'Unrecognized extension — export MusicXML or MSCZ first'
            rows.append({'path':str(path),'folder':str(path.parent),'filename':name,'title':path.stem,'format':ext[1:].upper(),'direct':direct,'known':str(path) in known,'reason':reason})
        if truncated:break
    rows.sort(key=lambda r:(r['known'],not r['direct'],r['title'].casefold(),r['path']))
    return {'folder':str(folder),'files':rows,'truncated':truncated,'unreadableFolders':len(errors)}

def normalized(title):
    title=unicodedata.normalize('NFKD',title.casefold())
    title=''.join(c for c in title if not unicodedata.combining(c))
    title=re.sub(r'\bsharp\b','#',title)
    title=re.sub(r'\bflat\b','♭',title)
    return re.sub(r'[^\w#♭]+',' ',title).strip()

def title_matches(row,videos):
    titles={normalized(row['title']),normalized(pathlib.Path(row['filename']).stem)}-{''}
    matches=[]
    for video in videos:
        other=normalized(video['title'])
        exact=other in titles
        near=any(len(t)>=12 and len(other)>=12 and difflib.SequenceMatcher(None,t,other).ratio()>=.9 for t in titles)
        contained=any(len(t)>=12 and (' '+t+' ') in (' '+other+' ') for t in titles)
        if exact or near or contained:matches.append({'id':video['id'],'title':video['title'],'reason':'Same normalized title' if exact else 'Similar title'})
    return sorted(matches,key=lambda m:(m['reason']!='Same normalized title',m['title']))[:20]
