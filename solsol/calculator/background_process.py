"""Windows child policy for the calculator, including host file-write helpers.

No global Python configuration is changed. A hidden parent does not imply hidden
children. Install at app entry before imports or writes that may spawn helpers.
"""
import inspect
import os
import subprocess
from pathlib import Path

def acquire_startup_lock(path, timeout=110):
    """Serialize repeated desktop clicks; OS releases the lock on process exit."""
    if os.name!='nt':
        return None
    import ctypes,hashlib
    from ctypes import wintypes
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.CreateMutexW.argtypes=[ctypes.c_void_p,wintypes.BOOL,wintypes.LPCWSTR]
    kernel.CreateMutexW.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.WaitForSingleObject.restype=wintypes.DWORD
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    kernel.ReleaseMutex.argtypes=[wintypes.HANDLE]
    identity=hashlib.sha256(str(Path(path).resolve()).casefold().encode()).hexdigest()
    handle=kernel.CreateMutexW(None,False,'Local\\SOLSOL_START_'+identity)
    if not handle:raise ctypes.WinError(ctypes.get_last_error())
    outcome=kernel.WaitForSingleObject(handle,int(timeout*1000))
    if outcome not in (0,128):
        kernel.CloseHandle(handle)
        if outcome==258:raise TimeoutError('Another calculator startup is still running; no additional server was started.')
        raise ctypes.WinError(ctypes.get_last_error())
    class Lease:
        def close(self):
            nonlocal handle
            if handle:
                kernel.ReleaseMutex(handle);kernel.CloseHandle(handle);handle=None
        def __del__(self):self.close()
    return Lease()

def install_hidden_children(script_bootstraps=None):
    if os.name != 'nt':
        return
    if getattr(subprocess.Popen, '_solsol_background', False):
        subprocess.Popen._script_bootstraps.update(script_bootstraps or {})
        return
    original = subprocess.Popen
    signature = inspect.signature(original)

    class BackgroundPopen(original):
        _solsol_background = True
        _script_bootstraps = dict(script_bootstraps or {})

        def __init__(self, *args, **kwargs):
            bound = signature.bind(*args, **kwargs)
            flags = bound.arguments.get('creationflags', 0)
            flags &= ~(subprocess.CREATE_NEW_CONSOLE | subprocess.DETACHED_PROCESS)
            bound.arguments['creationflags'] = flags | subprocess.CREATE_NO_WINDOW
            info = bound.arguments.get('startupinfo')
            info = info.copy() if info is not None else subprocess.STARTUPINFO()
            info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            info.wShowWindow = subprocess.SW_HIDE
            bound.arguments['startupinfo'] = info
            command = bound.arguments.get('args')
            # Only explicitly registered Python script children are wrapped.
            # Preserve shell strings, interpreter options, stdin and all outputs.
            if isinstance(command, (list, tuple)) and not bound.arguments.get('shell', False):
                command = list(command)
                if command and Path(command[0]).name.lower() in ('python.exe', 'pythonw.exe'):
                    for index in (1, 2):
                        if index < len(command):
                            bootstrap = self._script_bootstraps.get(str(Path(command[index]).resolve()))
                            if bootstrap:
                                command.insert(index, str(bootstrap))
                                bound.arguments['args'] = command
                                break
            super().__init__(*bound.args, **bound.kwargs)

    subprocess.Popen = BackgroundPopen
    def background_system(command):
        # alive_progress calls os.system('') at import to enable terminal ANSI.
        # A windowless server has no console to initialize. Nonempty commands
        # retain Windows exit-code semantics through the guarded shell path.
        if not isinstance(command,(str,bytes)):
            raise TypeError('system() argument must be str or bytes')
        if not command:return 0
        return subprocess.call(os.fsdecode(command),shell=True)
    os.system = background_system
