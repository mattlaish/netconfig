"""Data-driven, read-only SNMP vendor collection profiles."""
from __future__ import annotations
from dataclasses import dataclass
import json, os, re, tempfile
from pathlib import Path
_SCHEMA_VERSION = 1
_PROFILE_ID_RE = re.compile('^[a-z0-9][a-z0-9._-]{0,127}$')
_NUMERIC_OID_RE = re.compile('^\\.?\\d+(?:\\.\\d+)*$')
_FORBIDDEN_KEYS = {'python', 'shell', 'command', 'commands', 'script', 'scripts', 'url', 'urls', 'expression', 'expressions', 'eval', 'exec', 'subprocess', 'action', 'actions', 'module', 'callable', 'import', 'imports'}
_MAX_COLLECTIONS = 32
_MAX_VALUES_PER_ROOT = 2048
_MAX_TOTAL_VALUES = 8192
_MAX_METRICS = 256
_MAX_TABLES = 64
_MAX_TABLE_COLUMNS = 64
_MAX_TABLE_SENSORS = 64

def _oid(value, *, field):
    text = str(value or '').strip().lstrip('.')
    if not text or not _NUMERIC_OID_RE.fullmatch(text):
        raise ValueError(f'{field} must be a numeric OID')
    return text

def _under(root, prefix):
    return root == prefix or root.startswith(prefix + '.')

def _safe_walk_keys(value, path='profile'):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).strip().lower() in _FORBIDDEN_KEYS:
                raise ValueError(f'{path}.{key} is not permitted in a declarative SNMP profile')
            _safe_walk_keys(item, f'{path}.{key}')
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _safe_walk_keys(item, f'{path}[{i}]')

def _bounded_text(value, field, max_len=512, required=False):
    text = str(value or '').strip()
    if required and (not text):
        raise ValueError(f'{field} is required')
    if len(text) > max_len:
        raise ValueError(f'{field} is too long')
    return text

def _validate_template(text, field):
    text = _bounded_text(text, field, 1024)
    for token in re.findall('\\{([^{}]+)\\}', text):
        if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', token):
            raise ValueError(f'{field} contains unsupported template placeholder {token!r}')
    return text

@dataclass(frozen=True)
class VendorProfile:
    id: str
    version: str
    vendor: str
    product: str
    sysobject_prefixes: tuple[str, ...]
    collections: tuple[dict, ...]
    excludes: tuple[str, ...]
    metrics: tuple[dict, ...]
    tables: tuple[dict, ...]
    source_path: str

    def matches(self, sysobjectid):
        oid = str(sysobjectid or '').strip().lstrip('.')
        return any((_under(oid, p) for p in self.sysobject_prefixes))

    @property
    def total_limit(self):
        return min(_MAX_TOTAL_VALUES, sum((int(x['max_values']) for x in self.collections)))

def validate_profile(raw, *, source_path=''):
    if not isinstance(raw, dict):
        raise ValueError('profile must be a JSON object')
    _safe_walk_keys(raw)
    unknown = set(raw) - {'schema_version', 'id', 'version', 'vendor', 'product', 'match', 'collections', 'exclude', 'metrics', 'tables'}
    if unknown:
        raise ValueError('unsupported profile field(s): ' + ', '.join(sorted(unknown)))
    if int(raw.get('schema_version', 0)) != _SCHEMA_VERSION:
        raise ValueError(f'schema_version must be {_SCHEMA_VERSION}')
    pid = _bounded_text(raw.get('id'), 'id', 128, True).lower()
    if not _PROFILE_ID_RE.fullmatch(pid):
        raise ValueError("id must contain only lowercase letters, digits, '.', '_' or '-'")
    version = _bounded_text(raw.get('version'), 'version', 64, True)
    vendor = _bounded_text(raw.get('vendor'), 'vendor', 128, True)
    product = _bounded_text(raw.get('product'), 'product', 128, True)
    match = raw.get('match') or {}
    if not isinstance(match, dict) or set(match) - {'sysobject_prefixes'}:
        raise ValueError('match supports only sysobject_prefixes')
    prefixes = match.get('sysobject_prefixes') or []
    if not isinstance(prefixes, list) or not prefixes or len(prefixes) > 32:
        raise ValueError('match.sysobject_prefixes must contain 1..32 numeric OIDs')
    prefixes = tuple((_oid(x, field='match.sysobject_prefixes') for x in prefixes))
    cr = raw.get('collections') or []
    if not isinstance(cr, list) or not cr or len(cr) > _MAX_COLLECTIONS:
        raise ValueError(f'collections must contain 1..{_MAX_COLLECTIONS} entries')
    collections = []
    seen = set()
    for i, item in enumerate(cr):
        if not isinstance(item, dict) or set(item) - {'id', 'root', 'max_values', 'label'}:
            raise ValueError(f'collections[{i}] has unsupported fields')
        cid = _bounded_text(item.get('id'), f'collections[{i}].id', 64, True)
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,63}', cid) or cid in seen:
            raise ValueError(f'collections[{i}].id is invalid or duplicated')
        seen.add(cid)
        root = _oid(item.get('root'), field=f'collections[{i}].root')
        if not any((_under(root, p) for p in prefixes)):
            raise ValueError(f'collections[{i}].root must stay under a declared sysObjectID prefix')
        mv = int(item.get('max_values', 0))
        if mv < 1 or mv > _MAX_VALUES_PER_ROOT:
            raise ValueError(f'collections[{i}].max_values must be 1..{_MAX_VALUES_PER_ROOT}')
        collections.append({'id': cid, 'root': root, 'max_values': mv, 'label': _bounded_text(item.get('label') or cid, f'collections[{i}].label', 128)})
    if sum((x['max_values'] for x in collections)) > _MAX_TOTAL_VALUES:
        raise ValueError(f'sum of collection max_values must not exceed {_MAX_TOTAL_VALUES}')
    er = raw.get('exclude') or []
    if not isinstance(er, list) or len(er) > 64:
        raise ValueError('exclude must be a bounded array')
    excludes = tuple((_oid(x, field='exclude') for x in er))
    if any((not any((_under(x, p) for p in prefixes)) for x in excludes)):
        raise ValueError('exclude roots must stay under a declared sysObjectID prefix')
    mr = raw.get('metrics') or []
    if not isinstance(mr, list) or len(mr) > _MAX_METRICS:
        raise ValueError('metrics must be a bounded array')
    metrics = []
    for i, item in enumerate(mr):
        allowed = {'id', 'oid', 'sensor_type', 'resource', 'unit', 'status', 'value_map', 'message'}
        if not isinstance(item, dict) or set(item) - allowed:
            raise ValueError(f'metrics[{i}] has unsupported fields')
        oid = _oid(item.get('oid'), field=f'metrics[{i}].oid')
        if not any((_under(oid, p) for p in prefixes)):
            raise ValueError(f'metrics[{i}].oid is outside match prefixes')
        vm = item.get('value_map') or {}
        if not isinstance(vm, dict) or len(vm) > 128:
            raise ValueError(f'metrics[{i}].value_map must be an object')
        status = str(item.get('status') or 'OK').upper()
        if status not in {'OK', 'WARNING', 'CRITICAL', 'UNKNOWN'}:
            raise ValueError(f'metrics[{i}].status is invalid')
        metrics.append({'id': _bounded_text(item.get('id') or f'metric-{i}', f'metrics[{i}].id', 64), 'oid': oid, 'sensor_type': _bounded_text(item.get('sensor_type'), f'metrics[{i}].sensor_type', 128, True), 'resource': _validate_template(item.get('resource') or '', f'metrics[{i}].resource'), 'unit': _bounded_text(item.get('unit') or '', f'metrics[{i}].unit', 32), 'status': status, 'value_map': {str(k): str(v) for k, v in vm.items()}, 'message': _validate_template(item.get('message') or '', f'metrics[{i}].message')})
    tr = raw.get('tables') or []
    if not isinstance(tr, list) or len(tr) > _MAX_TABLES:
        raise ValueError('tables must be a bounded array')
    tables = []
    for ti, t in enumerate(tr):
        if not isinstance(t, dict) or set(t) - {'id', 'columns', 'sensors'}:
            raise ValueError(f'tables[{ti}] has unsupported fields')
        tid = _bounded_text(t.get('id'), f'tables[{ti}].id', 64, True)
        cols = t.get('columns') or {}
        sensors = t.get('sensors') or []
        if not isinstance(cols, dict) or not cols or len(cols) > _MAX_TABLE_COLUMNS:
            raise ValueError(f'tables[{ti}].columns must be a non-empty bounded object')
        ncols = {}
        for name, prefix in cols.items():
            if not re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', str(name)):
                raise ValueError(f'tables[{ti}] column name {name!r} is invalid')
            prefix = _oid(prefix, field=f'tables[{ti}].columns.{name}')
            if not any((_under(prefix, p) for p in prefixes)):
                raise ValueError(f'tables[{ti}] column prefix is outside match prefixes')
            ncols[str(name)] = prefix
        if not isinstance(sensors, list) or not sensors or len(sensors) > _MAX_TABLE_SENSORS:
            raise ValueError(f'tables[{ti}].sensors must be a non-empty bounded array')
        ns = []
        for si, s in enumerate(sensors):
            allowed = {'sensor_type', 'resource', 'value_from', 'value_map', 'unit', 'status', 'status_from', 'status_map', 'message', 'required_fields'}
            if not isinstance(s, dict) or set(s) - allowed:
                raise ValueError(f'tables[{ti}].sensors[{si}] has unsupported fields')
            vf = str(s.get('value_from') or '').strip()
            sf = str(s.get('status_from') or '').strip()
            req = s.get('required_fields') or []
            for fld in [vf, sf, *req]:
                if fld and fld not in ncols and (fld != 'index'):
                    raise ValueError(f'tables[{ti}] references unknown column {fld!r}')
            status = str(s.get('status') or 'OK').upper()
            if status not in {'OK', 'WARNING', 'CRITICAL', 'UNKNOWN'}:
                raise ValueError(f'tables[{ti}].sensors[{si}].status is invalid')
            vm = s.get('value_map') or {}
            sm = s.get('status_map') or {}
            if not isinstance(vm, dict) or not isinstance(sm, dict):
                raise ValueError('table value_map/status_map must be objects')
            if any((str(x).upper() not in {'OK', 'WARNING', 'CRITICAL', 'UNKNOWN'} for x in sm.values())):
                raise ValueError('table status_map contains invalid status')
            ns.append({'sensor_type': _bounded_text(s.get('sensor_type'), 'sensor_type', 128, True), 'resource': _validate_template(s.get('resource') or '{index}', 'resource'), 'value_from': vf, 'value_map': {str(k): str(v) for k, v in vm.items()}, 'unit': _bounded_text(s.get('unit') or '', 'unit', 32), 'status': status, 'status_from': sf, 'status_map': {str(k): str(v).upper() for k, v in sm.items()}, 'message': _validate_template(s.get('message') or '', 'message'), 'required_fields': tuple((str(x) for x in req))})
        tables.append({'id': tid, 'columns': ncols, 'sensors': ns})
    return VendorProfile(pid, version, vendor, product, prefixes, tuple(collections), excludes, tuple(metrics), tuple(tables), str(source_path or ''))

def load_profile_file(path):
    path = Path(path)
    if path.suffix.lower() != '.json':
        raise ValueError('SNMP vendor profiles must be JSON files')
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('profile file exceeds 1 MiB')
    with path.open('r', encoding='utf-8') as h:
        return validate_profile(json.load(h), source_path=str(path))

def _source_profile_dir():
    root = Path(__file__).resolve().parents[3]
    candidate = root / 'usr/share/netconfig/snmp-profiles'
    return candidate if candidate.is_dir() else None

class VendorProfileRegistry:

    def __init__(self, home, extra_path=None):
        self.home = Path(home)
        self.extra_path = extra_path
        self.profiles = {}
        self.errors = []
        self.reload()

    def directories(self):
        dirs = []
        sd = _source_profile_dir()
        if sd:
            dirs.append(sd)
        dirs += [Path('/usr/share/netconfig/snmp-profiles'), Path('/etc/netconfig/snmp-profiles'), self.home / 'snmp-profiles']
        extra = self.extra_path if self.extra_path is not None else os.environ.get('NETCONFIG_SNMP_PROFILE_PATH', '')
        dirs += [Path(p) for p in str(extra or '').split(os.pathsep) if p.strip()]
        out = []
        seen = set()
        for p in dirs:
            if str(p) not in seen:
                seen.add(str(p))
                out.append(p)
        return out

    def reload(self):
        profiles = {}
        errors = []
        for d in self.directories():
            if not d.is_dir():
                continue
            for path in sorted(d.glob('*.json')):
                try:
                    profile = load_profile_file(path)
                    profiles[profile.id] = profile
                except Exception as exc:
                    errors.append({'path': str(path), 'error': str(exc)})
        self.profiles = profiles
        self.errors = errors
        return len(profiles)

    def match(self, sysobjectid):
        matches = [p for p in self.profiles.values() if p.matches(sysobjectid)]
        return sorted(matches, key=lambda p: (-max((len(x.split('.')) for x in p.sysobject_prefixes)), p.id))[0] if matches else None

    def list(self):
        return sorted(self.profiles.values(), key=lambda p: p.id)

    @property
    def runtime_dir(self):
        return self.home / 'snmp-profiles'

    def install(self, source_file):
        profile = load_profile_file(source_file)
        self.runtime_dir.mkdir(parents=True, exist_ok=True, mode=448)
        target = self.runtime_dir / f'{profile.id}.json'
        raw = Path(source_file).read_bytes()
        fd, tmp = tempfile.mkstemp(prefix=f'.{profile.id}.', suffix='.tmp', dir=str(self.runtime_dir))
        try:
            with os.fdopen(fd, 'wb') as h:
                h.write(raw)
                h.flush()
                os.fsync(h.fileno())
            os.chmod(tmp, 416)
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        self.reload()
        active = self.profiles.get(profile.id)
        if not active:
            raise RuntimeError('profile installed but not active after reload')
        return (active, str(target))

    def remove_runtime(self, profile_id):
        profile_id = str(profile_id or '').strip().lower()
        if not _PROFILE_ID_RE.fullmatch(profile_id):
            raise ValueError('invalid profile id')
        target = self.runtime_dir / f'{profile_id}.json'
        removed = False
        if target.is_file():
            target.unlink()
            removed = True
        self.reload()
        return (removed, str(target))

def collection_specs(profile):
    return [dict(x) for x in profile.collections]

def is_excluded(profile, oid):
    oid = str(oid or '').strip().lstrip('.')
    return any((_under(oid, r) for r in profile.excludes))

def _fmt(template, ctx):
    if not template:
        return ''

    class Safe(dict):

        def __missing__(self, key):
            return ''
    return template.format_map(Safe({k: str(v or '') for k, v in ctx.items()}))

def normalize(profile, rows):
    by_oid = {str(r.get('oid') or '').lstrip('.'): str(r.get('value') or '') for r in rows or []}
    out = []
    base = f'vendor-profile:{profile.id}'
    for m in profile.metrics:
        if m['oid'] not in by_oid:
            continue
        raw = by_oid[m['oid']]
        value = m['value_map'].get(raw, raw)
        ctx = {'value': value, 'raw': raw}
        out.append({'sensor_type': m['sensor_type'], 'resource': _fmt(m['resource'], ctx), 'value': value, 'unit': m['unit'], 'status': m['status'], 'message': _fmt(m['message'], ctx), 'source': f"{base}/{m['id']}"})
    for t in profile.tables:
        entries = {}
        for cname, prefix in t['columns'].items():
            pfx = prefix + '.'
            for oid, value in by_oid.items():
                if oid.startswith(pfx) and (idx := oid[len(pfx):]):
                    entries.setdefault(idx, {'index': idx})[cname] = value
        for idx in sorted(entries, key=lambda x: tuple((int(y) if y.isdigit() else y for y in x.split('.')))):
            ctx = entries[idx]
            for s in t['sensors']:
                if any((not ctx.get(f, '') for f in s['required_fields'])):
                    continue
                raw = ctx.get(s['value_from'], '') if s['value_from'] else ''
                value = s['value_map'].get(str(raw), str(raw))
                status = s['status']
                if s['status_from']:
                    status = s['status_map'].get(str(ctx.get(s['status_from'], '')), 'UNKNOWN')
                mc = dict(ctx)
                mc.update({'value': value, 'raw': raw})
                out.append({'sensor_type': s['sensor_type'], 'resource': _fmt(s['resource'], mc), 'value': value, 'unit': s['unit'], 'status': status, 'message': _fmt(s['message'], mc), 'source': f"{base}/{t['id']}"})
    return out
