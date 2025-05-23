import ctypes
import ctypes.wintypes as wintypes
import socket
import time

# --- Configuration ---
UDP_IP = "127.0.0.1"
UDP_PORT = 5005
CIRCLE_RADIUS = 30
CIRCLE_COLOR_RGB = (255, 0, 0)  # Red
CIRCLE_STROKE_WIDTH = 3
TRANSPARENT_COLOR_RGB = (1, 2, 3) # A specific, unlikely color to be transparent
                                  # Using pure black (0,0,0) can sometimes conflict if other UI elements use it.

# --- WinAPI Constants ---
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020 # Click-through
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080 # Don't show in taskbar or Alt+Tab
WS_POPUP = 0x80000000
WS_VISIBLE = 0x10000000
GWL_EXSTYLE = -20
LWA_COLORKEY = 0x00000001
SM_CXSCREEN = 0
SM_CYSCREEN = 1
WM_DESTROY = 0x0002
WM_QUIT = 0x0012
PS_SOLID = 0
NULL_BRUSH = 5 # Stock GDI object
PM_REMOVE = 0x0001

# Window Procedure forward declaration for WNDCLASSEXW field type hint
WndProcType = ctypes.WINFUNCTYPE(wintypes.LPARAM, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

# --- WinAPI Structures ---
class WNDCLASSEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.UINT),
        ("style", wintypes.UINT),
        ("lpfnWndProc", WndProcType),
        ("cbClsExtra", ctypes.c_int),
        ("cbWndExtra", ctypes.c_int),
        ("hInstance", wintypes.HINSTANCE),
        ("hIcon", wintypes.HANDLE),  # Changed from HICON to HANDLE
        ("hCursor", wintypes.HANDLE), # Changed from HCURSOR to HANDLE
        ("hbrBackground", wintypes.HANDLE), # Changed from HBRUSH to HANDLE
        ("lpszMenuName", wintypes.LPCWSTR),
        ("lpszClassName", wintypes.LPCWSTR),
        ("hIconSm", wintypes.HANDLE) # Changed from HICON to HANDLE
    ]

# --- WinAPI Functions ---
user32 = ctypes.windll.user32
gdi32 = ctypes.windll.gdi32
kernel32 = ctypes.windll.kernel32

# --- Global variables ---
hwnd = None
hdc = None
screen_width = user32.GetSystemMetrics(SM_CXSCREEN)
screen_height = user32.GetSystemMetrics(SM_CYSCREEN)
last_gaze_px = screen_width // 2
last_gaze_py = screen_height // 2
running = True
h_instance_global = None
class_name_global = "GazeOverlayWindowClass"

def RGB(r,g,b):
    return r | (g << 8) | (b << 16)

transparent_colorref = RGB(*TRANSPARENT_COLOR_RGB)
circle_colorref = RGB(*CIRCLE_COLOR_RGB)

# Window Procedure
def wnd_proc_py(hWnd_param, msg, wParam, lParam):
    
    global running
    if msg == WM_DESTROY:
        user32.PostQuitMessage(0)
        running = False # Signal main loop to stop
        return 0
    # Explicitly cast wParam and lParam before passing to DefWindowProcW
    return user32.DefWindowProcW(hWnd_param, msg, wintypes.WPARAM(wParam), wintypes.LPARAM(lParam))
wnd_proc_c = WndProcType(wnd_proc_py)


def create_overlay_window():
    global hwnd, hdc, h_instance_global, class_name_global
    
    h_instance_global = kernel32.GetModuleHandleW(None)
    if not h_instance_global:
        print(f"Failed to get module handle: {kernel32.GetLastError()}")
        return False

    wc = WNDCLASSEXW() # Use the custom defined structure
    wc.cbSize = ctypes.sizeof(WNDCLASSEXW)
    wc.lpfnWndProc = wnd_proc_c
    wc.lpszClassName = class_name_global
    wc.hInstance = h_instance_global
    wc.hbrBackground = gdi32.CreateSolidBrush(transparent_colorref)
    if not wc.hbrBackground:
        print(f"Failed to create background brush: {kernel32.GetLastError()}")
        return False
    wc.hIcon = None # No icon
    wc.hCursor = None # No cursor
    
    if not user32.RegisterClassExW(ctypes.byref(wc)):
        err = kernel32.GetLastError()
        # ERROR_CLASS_ALREADY_EXISTS = 1410
        if err != 1410 : # Don't fail if class already exists (e.g. script re-run)
            print(f"Failed to register window class (Error: {err})")
            gdi32.DeleteObject(wc.hbrBackground)
            return False
        print("Window class already registered, proceeding.")


    hwnd = user32.CreateWindowExW(
        WS_EX_TOPMOST | WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW,
        wc.lpszClassName,
        "Gaze Overlay", # Not visible
        WS_POPUP | WS_VISIBLE,
        0, 0, screen_width, screen_height,
        None, None, wc.hInstance, None
    )

    if not hwnd:
        print(f"Failed to create window: {kernel32.GetLastError()}")
        if wc.hbrBackground : gdi32.DeleteObject(wc.hbrBackground) # wc.hbrBackground might be None if RegisterClassExW failed earlier
        user32.UnregisterClassW(wc.lpszClassName, wc.hInstance)
        return False

    user32.SetLayeredWindowAttributes(hwnd, transparent_colorref, 0, LWA_COLORKEY)
    
    hdc = user32.GetDC(hwnd)
    if not hdc:
        print(f"Failed to get device context: {kernel32.GetLastError()}")
        user32.DestroyWindow(hwnd)
        if wc.hbrBackground : gdi32.DeleteObject(wc.hbrBackground)
        user32.UnregisterClassW(wc.lpszClassName, wc.hInstance)
        return False
        
    print("Overlay window created successfully.")
    return True

def draw_gaze_circle():
    if not hwnd or not hdc: return

    rect_fullscreen = wintypes.RECT(0, 0, screen_width, screen_height) # Full screen rect
    
    # Create a brush with the transparent color to fill the background
    hbr_fill = gdi32.CreateSolidBrush(transparent_colorref)
    if not hbr_fill: return
    user32.FillRect(hdc, ctypes.byref(rect_fullscreen), hbr_fill)
    gdi32.DeleteObject(hbr_fill)

    hPen = gdi32.CreatePen(PS_SOLID, CIRCLE_STROKE_WIDTH, circle_colorref)
    if not hPen: return
    hOldPen = gdi32.SelectObject(hdc, hPen)
    
    hNullBrush = gdi32.GetStockObject(NULL_BRUSH)
    hOldBrush = gdi32.SelectObject(hdc, hNullBrush)

    left, top = last_gaze_px - CIRCLE_RADIUS, last_gaze_py - CIRCLE_RADIUS
    right, bottom = last_gaze_px + CIRCLE_RADIUS, last_gaze_py + CIRCLE_RADIUS
    gdi32.Ellipse(hdc, left, top, right, bottom)

    gdi32.SelectObject(hdc, hOldPen)
    gdi32.SelectObject(hdc, hOldBrush)
    gdi32.DeleteObject(hPen)

def main_loop():
    global last_gaze_px, last_gaze_py, running, hwnd, hdc, h_instance_global, class_name_global

    # --- UDP Socket Setup ---
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((UDP_IP, UDP_PORT))
        sock.setblocking(False)
        print(f"Listening for gaze data on UDP {UDP_IP}:{UDP_PORT}")
    except OSError as e:
        print(f"Error binding UDP socket: {e}. Is another instance running or port in use?")
        return # Exit if socket can't be bound

    if not create_overlay_window():
        print("Could not create overlay window. Exiting.")
        sock.close()
        return

    print("Overlay active. Press Ctrl+C in the console to quit.")
    msg = wintypes.MSG()
    pMsg = ctypes.byref(msg)

    try:
        while running:
            while user32.PeekMessageW(pMsg, None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT:
                    running = False
                    break
                user32.TranslateMessage(pMsg)
                user32.DispatchMessageW(pMsg)
            if not running: break

            try:
                data, addr = sock.recvfrom(1024)
                # Decode data to string and parse "x,y" format
                message = data.decode('utf-8')
                parts = message.split(',')
                if len(parts) == 2:
                    px_str, py_str = parts
                    try:
                        px = int(float(px_str)) # Convert to float first for robustness, then int
                        py = int(float(py_str))

                        new_gaze_px = max(0, min(screen_width - 1, px))
                        new_gaze_py = max(0, min(screen_height - 1, py))

                        if new_gaze_px != last_gaze_px or new_gaze_py != last_gaze_py:
                            last_gaze_px, last_gaze_py = new_gaze_px, new_gaze_py
                            draw_gaze_circle()
                    except ValueError:
                        print(f"Could not parse coordinates: {message}")
                # else: # Optional: handle malformed messages
                    # print(f"Received malformed message: {message}")

            except BlockingIOError: pass
            except socket.error: pass # Other socket errors
            except UnicodeDecodeError:
                print("Error decoding UDP message.")
            
            time.sleep(0.005) # Small delay to yield CPU

    except KeyboardInterrupt:
        print("\nCtrl+C detected. Exiting.")
        running = False
    finally:
        print("Cleaning up...")
        if hdc and hwnd and user32.IsWindow(hwnd): user32.ReleaseDC(hwnd, hdc)
        if hwnd and user32.IsWindow(hwnd): user32.DestroyWindow(hwnd) # Triggers WM_DESTROY -> PostQuitMessage
        
        # Wait for WM_QUIT to be processed if DestroyWindow was called
        # This ensures wnd_proc_py sets running to False
        if msg.message != WM_QUIT and user32.IsWindow(hwnd): # Check if window still exists
             # Pump messages once more to ensure WM_DESTROY/WM_QUIT are handled
            while user32.PeekMessageW(pMsg, None, 0, 0, PM_REMOVE):
                if msg.message == WM_QUIT: break
                user32.TranslateMessage(pMsg)
                user32.DispatchMessageW(pMsg)


        if h_instance_global and class_name_global:
            if not user32.UnregisterClassW(class_name_global, h_instance_global):
                # This might fail if other instances are still running or if it was never properly registered
                # print(f"Failed to unregister window class (Error: {kernel32.GetLastError()}).")
                pass # Suppress error on exit
            else:
                print("Window class unregistered.")
        
        sock.close()
        print("Cleanup complete.")

if __name__ == "__main__":
    main_loop()
