"""Explicit local-file selection for loopback validation import, never raw serving."""
import hashlib,os,re,stat,zipfile,io
from pathlib import Path

MAX_ZIP_BYTES=20*1024*1024
MAX_EXPANDED_BYTES=256*1024*1024

def _native_open_path(handle,allowed):
    """Bind containment to the opened file, including a swapped path/junction."""
    if os.name=='nt':
        import ctypes,msvcrt
        from ctypes import wintypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        final=kernel.GetFinalPathNameByHandleW;final.argtypes=[wintypes.HANDLE,wintypes.LPWSTR,wintypes.DWORD,wintypes.DWORD];final.restype=wintypes.DWORD
        create=kernel.CreateFileW;create.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,wintypes.LPVOID,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE];create.restype=wintypes.HANDLE
        close=kernel.CloseHandle;close.argtypes=[wintypes.HANDLE];close.restype=wintypes.BOOL
        def native(value):
            buffer=ctypes.create_unicode_buffer(32768);length=final(value,buffer,len(buffer),0)
            if not 0<length<len(buffer):raise OSError('Cannot resolve opened file identity')
            name=buffer.value
            if name.startswith('\\\\?\\UNC\\'):return Path('\\\\'+name[8:])
            return Path(name[4:] if name.startswith('\\\\?\\') else name)
        actual=native(msvcrt.get_osfhandle(handle.fileno()));roots=[]
        for root in allowed:
            directory=create(str(root),0,7,None,3,0x02000000,None)
            if directory==wintypes.HANDLE(-1).value:continue
            try:roots.append(native(directory))
            finally:close(directory)
    else:
        link=Path('/proc/self/fd')/str(handle.fileno())
        if not link.exists():raise ValueError('VALIDATION_LOCAL_HANDLE_CHECK_UNSUPPORTED')
        actual=link.resolve(strict=True);roots=allowed
    if not any(actual.is_relative_to(root) for root in roots):raise ValueError('VALIDATION_LOCAL_OPENED_FILE_OUTSIDE_ROOTS')
    return actual

def import_roots():
    home=Path(os.environ.get('USERPROFILE',str(Path.home())))
    return [home/'Desktop',home/'Downloads']

def read_export_bytes(raw,cid):
    from engine_client import EngineClient,EngineError
    if not isinstance(raw,bytes) or not 0<len(raw)<=MAX_ZIP_BYTES:raise ValueError('VALIDATION_EXPORT_SIZE_LIMIT_20MB')
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members=archive.infolist()
            if len(members)>20000 or sum(m.file_size for m in members)>MAX_EXPANDED_BYTES:raise ValueError('VALIDATION_EXPORT_EXPANDED_LIMIT_256MB')
            if any(m.flag_bits&1 for m in members):raise ValueError('VALIDATION_EXPORT_ENCRYPTED_UNSUPPORTED')
        result=EngineClient.read_validation_export(raw)
    except (EngineError,zipfile.BadZipFile,KeyError,TypeError,RuntimeError,NotImplementedError) as exc:raise ValueError('VALIDATION_EXPORT_INVALID: '+str(exc)) from exc
    if result['manifest']['experiment_contract_id']!=cid:raise ValueError('VALIDATION_EXPORT_CONTRACT_MISMATCH')
    return result

def read_local_export(selected_path,cid,roots=None):
    if not isinstance(selected_path,str) or len(selected_path)>4096 or '\x00' in selected_path:raise ValueError('VALIDATION_LOCAL_PATH_REQUIRED')
    path=Path(selected_path)
    if not path.is_absolute() or selected_path.startswith(('\\\\','//')) or path.suffix.lower()!='.zip':raise ValueError('VALIDATION_LOCAL_ABSOLUTE_ZIP_ONLY')
    if os.name=='nt' and (not re.fullmatch(r'[A-Za-z]:',path.drive) or ':' in selected_path[2:]):raise ValueError('VALIDATION_LOCAL_DEVICE_OR_STREAM_UNSUPPORTED')
    allowed=[p.resolve() for p in (import_roots() if roots is None else map(Path,roots))]
    try:
        resolved=path.resolve(strict=True)
        if not any(resolved.is_relative_to(root) for root in allowed):raise ValueError('VALIDATION_LOCAL_PATH_OUTSIDE_DESKTOP_DOWNLOADS')
        if not stat.S_ISREG(resolved.stat().st_mode):raise ValueError('VALIDATION_LOCAL_REGULAR_FILE_ONLY')
        with resolved.open('rb') as handle:
            before=os.fstat(handle.fileno())
            if not stat.S_ISREG(before.st_mode):raise ValueError('VALIDATION_LOCAL_REGULAR_FILE_ONLY')
            if not 0<before.st_size<=MAX_ZIP_BYTES:raise ValueError('VALIDATION_EXPORT_SIZE_LIMIT_20MB')
            opened_path=_native_open_path(handle,allowed)
            raw=handle.read(MAX_ZIP_BYTES+1);after=os.fstat(handle.fileno())
            if _native_open_path(handle,allowed)!=opened_path:raise ValueError('VALIDATION_LOCAL_FILE_CHANGED_DURING_READ')
        current=resolved.stat()
        identity=lambda s:(s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns)
        if identity(before)!=identity(after) or identity(after)!=identity(current) or len(raw)!=before.st_size:raise ValueError('VALIDATION_LOCAL_FILE_CHANGED_DURING_READ')
    except OSError as exc:raise ValueError('VALIDATION_LOCAL_FILE_UNAVAILABLE') from exc
    result=read_export_bytes(raw,cid)
    result['import_source']=dict(method='EXPLICIT_LOCAL_PATH',path=str(resolved),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest(),optimizer_nfe=0)
    return result
