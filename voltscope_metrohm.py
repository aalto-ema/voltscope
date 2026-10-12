"""Metrohm GPES text and NOVA NRBF data import. Never executes .NET objects."""
from pathlib import Path
import re
import struct
from voltscope_data import Curve, number


def text_file(path):
    data = Path(path).read_bytes()
    try: return data.decode('utf-8-sig')
    except UnicodeDecodeError: return data.decode('cp1252')


def read_gpes(path):
    requested = Path(path)
    path = requested.with_suffix('.ocw') if requested.suffix.lower() in ('.ici','.icw') else requested
    if not path.exists():
        candidates = [p for p in requested.parent.iterdir() if p.stem.casefold() == requested.stem.casefold() and p.suffix.lower() == '.ocw']
        if not candidates: raise ValueError('GPES settings file requires its matching .ocw measurement file in the same folder.')
        path = candidates[0]
    lines = [line.strip() for line in text_file(path).splitlines() if line.strip()]
    start = next((i for i,line in enumerate(lines) if ',' in line and len(line.split(',')) > 1),None)
    if start is None: raise ValueError('GPES OCW column header was not found.')
    labels = [label.strip() for label in lines[start].split(',')]
    metadata = {'FORMAT':'Metrohm GPES','TITLE':path.stem,'REQUESTED_FILE':str(requested)}
    siblings = {p.suffix.lower(): p for p in path.parent.iterdir() if p.stem.casefold() == path.stem.casefold()}
    metadata['COMPANION_FILES'] = [str(p) for ext,p in siblings.items() if ext in ('.ici','.icw','.ocw')]
    settings = siblings.get('.ici', requested.with_suffix('.ici'))
    if settings.exists():
        for line in text_file(settings).splitlines():
            if '=' in line:
                key,value=line.split('=',1)
                metadata[key.strip()]=value.strip()
        if not any(labels):
            labels = [metadata.get('xaxis.axtext',''),metadata.get('yaxis.axtext','')]
            metadata['COLUMN_SOURCE'] = 'Matching ICI axis labels'
        if '[CV]' in text_file(settings): metadata['TAG']='CV'
    config = siblings.get('.icw')
    if config:
        for line in text_file(config).splitlines():
            line=line.strip()
            if re.fullmatch(r'\d{1,2}/\d{1,2}/\d{4}',line): metadata['DATE']=line
            if re.fullmatch(r'\d{1,2}:\d{2}:\d{2}.*',line): metadata['TIME']=line
    columns,units=[],[]
    for i,label in enumerate(labels):
        name,sep,unit=label.partition('/')
        name,unit=name.strip(),unit.strip()
        mapped = {('E','V'):'Vf',('I','A'):'Im',('i','A'):'Im',('t','s'):'T',('Time','s'):'T'}.get((name,unit))
        columns.append(mapped or name or f'Column{i+1}')
        units.append(unit if sep and unit else 'unknown')
    if len(set(columns)) != len(columns): raise ValueError('Duplicate GPES column names.')
    metadata['SOURCE_COLUMNS']=' | '.join(labels)
    metadata.setdefault('TAG','CV' if columns == ['Vf','Im'] else 'GPES')
    rows=[]
    for index,line in enumerate(lines[start+1:],start+2):
        row=[number(value) for value in line.split()]
        if len(row)!=len(columns) or any(v is None for v in row): raise ValueError(f'Malformed GPES data row {index}')
        rows.append(row)
    if not rows: raise ValueError('GPES file has no measurement rows.')
    return [Curve(str(path),'GPES data',columns,units,rows,metadata)]


def nova_curves(objects, root, path, stream):
    """Extract explicit data-array parameters grouped by their owner command."""
    def deref(value):
        seen=set()
        while isinstance(value,dict) and '__ref__' in value:
            key=value['__ref__']
            if key in seen or key not in objects: raise ValueError('Invalid or cyclic NOVA reference.')
            seen.add(key)
            value=objects[key]
        return value

    def array(value):
        value=deref(value)
        if isinstance(value,dict) and '_value' in value: value=deref(value['_value'])
        if isinstance(value,dict) and '_items' in value:
            items=deref(value['_items'])
            size=value.get('_size')
            if not isinstance(items,list) or not isinstance(size,int) or not 0<=size<=len(items): raise ValueError('Invalid NOVA array size.')
            return items[:size]
        return value if isinstance(value,list) else None

    groups={}
    for obj in objects.values():
        if not isinstance(obj,dict) or obj.get('__class__')!='EcoChemie.Utils.Sequencer.CommandParameterDataArray': continue
        values=array(obj.get('_parameter'))
        if not values: continue
        if not all(isinstance(v,(float,int)) for v in values): raise ValueError('Non-numeric NOVA signal data.')
        parent=obj.get('CommandParameter+_parent',{})
        if '__ref__' not in parent: raise ValueError('NOVA signal has no owner.')
        owner=parent['__ref__']
        name=deref(obj.get('CommandParameter+_name'))
        unit=deref(obj.get('CommandParameter+_unit')) or 'unknown'
        mapped={'SetpointApplied':'Vset','CalcTime':'T','EI_0.CalcCurrent':'Im','EI_0.CalcPotential':'Vf','ScanNumber':'Scan','Index':'Index'}.get(name,name)
        groups.setdefault(owner,[]).append((mapped,unit,values))
    curves=[]
    for owner,signals in groups.items():
        if not {'Im','Vf'}.issubset({name for name,_,_ in signals}): continue
        lengths={len(values) for _,_,values in signals}
        if len(lengths)!=1: raise ValueError('NOVA signals have incompatible lengths; data was not truncated.')
        if len({name for name,_,_ in signals})!=len(signals): raise ValueError('Duplicate NOVA signals.')
        command=objects.get(owner,{})
        label=deref(command.get('FunctionHandler+_text')) or deref(command.get('FunctionHandler+_localizedText')) or f'Command {owner}'
        tag='CV' if 'CyclicVoltammetry' in command.get('__class__','') else 'NOVA'
        metadata={'FORMAT':'Metrohm NOVA','TAG':tag,'TITLE':root.get('_text',''),'PSTAT':root.get('_instrument',''),'NOVA_STREAM':str(stream),'NOVA_COMMAND':str(owner),'SOURCE_COLUMNS':' | '.join(name for name,_,_ in signals)}
        curves.append(Curve(str(path),f'{stream}: {label}',[v[0] for v in signals],[v[1] for v in signals],[list(row) for row in zip(*(v[2] for v in signals))],metadata))
    return curves


def read_nova(path):
    try: import nrbf
    except ImportError: raise ValueError('NOVA import requires nrbf. Install requirements.txt in your Python environment.') from None
    class RawParser(nrbf.NRBFParser):
        # Keep references as records; automatic graph resolution recurses on
        # NOVA parent/child cycles. Resolve only fields needed for data extraction.
        def _resolve(self,value): return value
    data=Path(path).read_bytes()
    curves,offset,stream=[],0,0
    while offset<len(data):
        parser=RawParser(data[offset:])
        try:
            root=parser.parse()
            used=parser._f.tell()
            if not used or data[offset+used-1]!=11: raise ValueError('Incomplete NOVA stream.')
            stream+=1
            if not isinstance(root,dict): raise ValueError('Unsupported NOVA root object.')
            curves.extend(nova_curves(parser.objects,root,path,stream))
            offset+=used
        except (ValueError,EOFError,KeyError,IndexError,TypeError,OverflowError,struct.error) as exc:
            raise ValueError(f'Cannot read NOVA stream {stream+1}: {exc}') from exc
    if not curves: raise ValueError('NOVA file contains no supported stored measurement signals.')
    return curves
