import socket
import json
import threading
from pupil_labs.real_time_screen_gaze import marker_generator
from pupil_labs.real_time_screen_gaze.gaze_mapper import GazeMapper
from pupil_labs.realtime_api.simple import discover_one_device
import matplotlib.pyplot as plt
from PIL import Image, ImageTk
# --- UDP Setup ---
unity_ip = "127.0.0.1"
unity_port = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

screen_height = 1080
screen_width = 1920
N_MARKERS = 4
MARKER_SIZE = 256

# --- Marker Vertices (pixel coordinates in the camera image) ---
marker_verts = {
    0: [(0, 0), (MARKER_SIZE, 0), (MARKER_SIZE, MARKER_SIZE), (0, MARKER_SIZE)],  # Top-left
    1: [(screen_width-MARKER_SIZE, 0), (screen_width, 0), (screen_width, MARKER_SIZE), (screen_width-MARKER_SIZE, MARKER_SIZE)],  # Top-right
    2: [(0, screen_height-MARKER_SIZE), (MARKER_SIZE, screen_height-MARKER_SIZE), (MARKER_SIZE, screen_height), (0, screen_height)],  # Bottom-left
    3: [(screen_width-MARKER_SIZE, screen_height-MARKER_SIZE), (screen_width, screen_height-MARKER_SIZE), (screen_width, screen_height), (screen_width-MARKER_SIZE, screen_height)],  # Bottom-right
}



# marker_verts = {
#     0: [(0, 0), (0, 128), (128, 128), (128, 0)],  # Top-left
#     1: [(1920 - 128, 0), (1920 - 128, 128), (1920, 128), (1920, 0)],  # Top-right
#     2: [(0, 1080 - 128), (0, 1080), (128, 1080), (128, 1080 - 128)],  # Bottom-left
#     3: [(1920 - 128, 1080 - 128), (1920 - 128, 1080), (1920, 1080), (1920, 1080 - 128)],  # Bottom-right
#     4: [(screen_width//2 - 64, 0), (screen_width//2 - 64, 128), (screen_width//2 + 64, 128), (screen_width//2 + 64, 0)],  # Top-center
#     5: [(screen_width//2 - 64, screen_height - 128), (screen_width//2 - 64, screen_height), (screen_width//2 + 64, screen_height), (screen_width//2 + 64, screen_height - 128)],  # Bottom-center
#     6: [(0, screen_height//2 - 64), (0, screen_height//2 + 64), (128, screen_height//2 + 64), (128, screen_height//2 - 64)],  # Left-center
#     7: [(screen_width - 128, screen_height//2 - 64), (screen_width - 128, screen_height//2 + 64), (screen_width, screen_height//2 + 64), (screen_width, screen_height//2 - 64)],  # Right-center
# }
screen_size = (1920, 1080)  # Your display resolution

# --- Discover Neon Device ---
try :
    device = discover_one_device(max_search_duration_seconds=10)
    calibration = device.get_calibration()
    print("Calibration:", calibration)
except Exception as e:
    print("Error discovering device:", e)
    exit(1)
gaze_mapper = GazeMapper(calibration)

# --- Add Surface for Gaze Mapping ---
screen_surface = gaze_mapper.add_surface(marker_verts, screen_size)

print("Ready to stream gaze data...")

screen_width = 1920
screen_height = 1080

# Marker size in pixels


# Generate eight markers with different IDs
marker_ids = list(range(N_MARKERS))
markers = [marker_generator.generate_marker(marker_id=i) for i in marker_ids]
marker_imgs = [Image.fromarray(m).resize((MARKER_SIZE, MARKER_SIZE), Image.NEAREST) for m in markers]

def show_markers_thread():
    import tkinter as tk
    from PIL import ImageTk

    # Tkinter root (hidden)
    root = tk.Tk()
    root.withdraw()

    def show_marker(img, x, y):
        win = tk.Toplevel()
        win.overrideredirect(True)
        win.geometry(f"{MARKER_SIZE}x{MARKER_SIZE}+{x}+{y}")
        photo = ImageTk.PhotoImage(img)
        label = tk.Label(win, image=photo)
        label.image = photo
        label.pack()
        win.lift()
        win.attributes("-topmost", True)

    # Corners
    show_marker(marker_imgs[0], 0, 0)  # Top-left
    show_marker(marker_imgs[1], screen_width - MARKER_SIZE, 0)  # Top-right
    show_marker(marker_imgs[2], 0, screen_height - MARKER_SIZE)  # Bottom-left
    show_marker(marker_imgs[3], screen_width - MARKER_SIZE, screen_height - MARKER_SIZE)  # Bottom-right
    # Edge centers
    # show_marker(marker_imgs[4], screen_width//2 - marker_size//2, 0)  # Top-center
    # show_marker(marker_imgs[5], screen_width//2 - marker_size//2, screen_height - marker_size)  # Bottom-center
    # show_marker(marker_imgs[6], 0, screen_height//2 - marker_size//2)  # Left-center
    # show_marker(marker_imgs[7], screen_width - marker_size, screen_height//2 - marker_size//2)  # Right-center

    root.mainloop()

# Start marker display in a separate thread
marker_thread = threading.Thread(target=show_markers_thread, daemon=True)
marker_thread.start()

# --- Now your main loop can run without being blocked ---
while True:
    frame, gaze = device.receive_matched_scene_video_frame_and_gaze()
    result = gaze_mapper.process_frame(frame, gaze)

    # --- Prepare Data ---
    data = {
        "raw_gaze": {
            "x": gaze.x,
            "y": gaze.y,
            "worn": gaze.worn,
            "pupil_diameter_left": gaze.pupil_diameter_left,
            "eyeball_center_left_x": gaze.eyeball_center_left_x,
            "eyeball_center_left_y": gaze.eyeball_center_left_y,
            "eyeball_center_left_z": gaze.eyeball_center_left_z,
            "optical_axis_left_x": gaze.optical_axis_left_x,
            "optical_axis_left_y": gaze.optical_axis_left_y,
            "optical_axis_left_z": gaze.optical_axis_left_z,
            "pupil_diameter_right": gaze.pupil_diameter_right,
            "eyeball_center_right_x": gaze.eyeball_center_right_x,
            "eyeball_center_right_y": gaze.eyeball_center_right_y,
            "eyeball_center_right_z": gaze.eyeball_center_right_z,
            "optical_axis_right_x": gaze.optical_axis_right_x,
            "optical_axis_right_y": gaze.optical_axis_right_y,
            "optical_axis_right_z": gaze.optical_axis_right_z,
            "eyelid_angle_top_left": gaze.eyelid_angle_top_left,
            "eyelid_angle_bottom_left": gaze.eyelid_angle_bottom_left,
            "eyelid_aperture_left": gaze.eyelid_aperture_left,
            "eyelid_angle_top_right": gaze.eyelid_angle_top_right,
            "eyelid_angle_bottom_right": gaze.eyelid_angle_bottom_right,
            "eyelid_aperture_right": gaze.eyelid_aperture_right,
            "timestamp_unix_seconds": gaze.timestamp_unix_seconds,
        },
        "surface_gaze": []
    }
    if len(result.mapped_gaze[screen_surface.uid]) == 0:
        print("No gaze data available")
        continue

    for surface_gaze in result.mapped_gaze[screen_surface.uid]:
        data["surface_gaze"].append({
            "timestamp_unix_seconds": surface_gaze.timestamp_unix_seconds,
            "x": surface_gaze.x,
            "y": surface_gaze.y,
            "on_surf": surface_gaze.on_surf,
            "confidence": surface_gaze.confidence,
        })
        print(f"Surface Gaze: {surface_gaze.x}, {surface_gaze.y}, {surface_gaze.on_surf}, {surface_gaze.confidence}")

    # --- Send Data via UDP ---
    sock.sendto(json.dumps(data).encode(), (unity_ip, unity_port))