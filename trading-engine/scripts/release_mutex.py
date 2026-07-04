"""Force-release abandoned Blofin mutexes by taking ownership."""
import ctypes
import sys
import time

kernel32 = ctypes.windll.kernel32

MUTEX_NAMES = [r"Global\BlofinAutoHedgeLoop", r"Global\BlofinAutoHedgeLoop_v2"]

for name in MUTEX_NAMES:
    # Try to create with initial ownership
    h = kernel32.CreateMutexW(None, True, name)
    err = kernel32.GetLastError()
    if h:
        kernel32.ReleaseMutex(h)
        kernel32.CloseHandle(h)
        print(f"OK: Released {name} (create err={err})")
    else:
        print(f"FAIL: Could not create {name} (err={err})")
    time.sleep(0.5)

# Verify they're gone
print("\nVerification:")
time.sleep(1)
for name in MUTEX_NAMES:
    h = kernel32.CreateMutexW(None, True, name)
    err = kernel32.GetLastError()
    if err == 0:
        print(f"  {name}: CLEAN (fresh creation)")
        kernel32.ReleaseMutex(h)
        kernel32.CloseHandle(h)
    else:
        print(f"  {name}: STILL HELD (err={err})")
