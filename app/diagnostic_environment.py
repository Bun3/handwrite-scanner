"""Allowlisted performance snapshot; never enumerates user files or processes."""
import ctypes
import importlib.metadata
import platform
import shutil
import struct
import sys
import time

from app import config, models

def _memory():
    class Memory(ctypes.Structure):
        _fields_ = [('length', ctypes.c_uint32), ('load', ctypes.c_uint32)] + [
            (name, ctypes.c_uint64) for name in ('total', 'available', 'commit_limit',
            'commit_available', 'virtual_total', 'virtual_available', 'extended')]
    memory = Memory()
    memory.length = ctypes.sizeof(memory)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(memory)):
        raise OSError('memory unavailable')
    return dict(ram_available_gb=round(memory.available / 2**30, 2), ram_load_percent=memory.load,
                commit_limit_gb=round(memory.commit_limit / 2**30, 2),
                commit_available_gb=round(memory.commit_available / 2**30, 2))


def _process_memory():
    class Counters(ctypes.Structure):
        _fields_ = [('size', ctypes.c_uint32), ('page_faults', ctypes.c_uint32)] + [
            (name, ctypes.c_size_t) for name in ('peak_working', 'working', 'peak_paged',
            'paged', 'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile', 'private')]
    counters = Counters()
    counters.size = ctypes.sizeof(counters)
    get_current = ctypes.windll.kernel32.GetCurrentProcess
    get_current.restype = ctypes.c_void_p
    get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
    get_memory.argtypes = [ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_uint32]
    if not get_memory(get_current(), ctypes.byref(counters), counters.size):
        raise OSError('process memory unavailable')
    result = dict(process_memory_mb=round(counters.working / 2**20, 1),
                  process_private_mb=round(counters.private / 2**20, 1))
    created, exited, kernel, user = (ctypes.c_uint64() for _ in range(4))
    get_times = ctypes.windll.kernel32.GetProcessTimes
    get_times.argtypes = [ctypes.c_void_p] + [ctypes.POINTER(ctypes.c_uint64)] * 4
    if get_times(get_current(), ctypes.byref(created), ctypes.byref(exited), ctypes.byref(kernel), ctypes.byref(user)):
        result['app_uptime_s'] = round(max(0, time.time() - (created.value / 1e7 - 11644473600)), 1)
    return result


def _cpu_load():
    def sample():
        idle, kernel, user = ctypes.c_uint64(), ctypes.c_uint64(), ctypes.c_uint64()
        if not ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user)):
            raise OSError('CPU sample unavailable')
        return idle.value, kernel.value + user.value
    idle, total = sample()
    time.sleep(.1)
    idle2, total2 = sample()
    return max(0, min(100, round(100 * (1 - (idle2-idle) / max(1, total2-total)), 1)))


def _hardware():
    import winreg
    result = {}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'HARDWARE\DESCRIPTION\System\CentralProcessor\0') as key:
            result['cpu_name'] = str(winreg.QueryValueEx(key, 'ProcessorNameString')[0]).strip()[:120]
            result['cpu_mhz'] = int(winreg.QueryValueEx(key, '~MHz')[0])
    except OSError:
        pass
    graphics = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Video') as root:
            for i in range(min(winreg.QueryInfoKey(root)[0], 32)):
                try:
                    with winreg.OpenKey(root, winreg.EnumKey(root, i) + r'\0000') as key:
                        name = str(winreg.QueryValueEx(key, 'DriverDesc')[0])[:120]
                        try:
                            version = str(winreg.QueryValueEx(key, 'DriverVersion')[0])[:120]
                        except OSError:
                            version = 'unknown'
                        item = {'name': name, 'driver_version': version}
                        if item not in graphics:
                            graphics.append(item)
                except OSError:
                    continue
    except OSError:
        pass
    result['graphics'] = graphics[:8]
    return result


def collect():
    result = dict(python_version=platform.python_version(), process_bits=struct.calcsize('P') * 8,
                  frozen=bool(getattr(sys, 'frozen', False)),
                  process_cpu_s=round(time.process_time(), 1))
    # Each optional probe fails independently; a damaged installation can still be reported.
    if sys.platform == 'win32':
        for probe in (_memory, _process_memory, _hardware):
            try:
                result.update(probe())
            except Exception:
                pass
        try:
            result['cpu_load_percent'] = _cpu_load()
            uptime = ctypes.windll.kernel32.GetTickCount64
            uptime.restype = ctypes.c_uint64
            result['system_uptime_s'] = round(uptime() / 1000, 1)
        except Exception:
            pass
    try:
        disk = shutil.disk_usage(config.DATA_DIR)
        result.update(disk_total_gb=round(disk.total / 2**30, 1), disk_used_gb=round(disk.used / 2**30, 1))
    except OSError:
        pass
    try:
        selected = models.current()
        model, projection = models.paths(selected)
        result.update(model_installed=model.is_file() and projection.is_file(),
                      model_size_mb=round(model.stat().st_size / 2**20, 1) if model.is_file() else 0,
                      projection_size_mb=round(projection.stat().st_size / 2**20, 1) if projection.is_file() else 0)
    except Exception:
        pass
    try:
        from app import llm
        status = llm.status()
        result['engine_state'] = status['state']
        # Only an error code; never the engine's raw output.
        code = status.get('error', {}).get('code', 'none')
        result['engine_error_code'] = code if code in ('memory','engine_missing','model_missing',
            'engine_exited','engine_start_timeout','engine_connection','permission','unexpected') else 'other'
    except Exception:
        result['engine_state'] = 'unknown'
    result['dependencies'] = {}
    for package in ('fastapi', 'httpx', 'pillow', 'pymupdf', 'opencv-python-headless'):
        try:
            result['dependencies'][package] = importlib.metadata.version(package)[:80]
        except Exception:
            result['dependencies'][package] = 'unknown'
    return result
