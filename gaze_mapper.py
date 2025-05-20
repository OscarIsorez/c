import socket
import json
import threading
from pupil_labs.real_time_screen_gaze import marker_generator
from pupil_labs.real_time_screen_gaze.gaze_mapper import GazeMapper
from pupil_labs.realtime_api.simple import discover_one_device
from PIL import Image, ImageTk
import tkinter as tk

# --- UDP Setup ---
unity_ip = "127.0.0.1"
unity_port = 5005
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# --- Screen and Marker Setup ---
screen_width = 1920
screen_height = 1080
N_MARKERS = 4
MARKER_SIZE = 256

marker_verts = {
    0: [(0, 0), (MARKER_SIZE, 0), (MARKER_SIZE, MARKER_SIZE), (0, MARKER_SIZE)],  # Top-left
    1: [(screen_width-MARKER_SIZE, 0), (screen_width, 0), (screen_width, MARKER_SIZE), (screen_width-MARKER_SIZE, MARKER_SIZE)],  # Top-right
    2: [(0, screen_height-MARKER_SIZE), (MARKER_SIZE, screen_height-MARKER_SIZE), (MARKER_SIZE, screen_height), (0, screen_height)],  # Bottom-left
    3: [(screen_width-MARKER_SIZE, screen_height-MARKER_SIZE), (screen_width, screen_height-MARKER_SIZE), (screen_width, screen_height), (screen_width-MARKER_SIZE, screen_height)],  # Bottom-right
}
screen_size = (screen_width, screen_height)

def show_markers_thread(marker_imgs):
    root = tk.Tk()
    root.withdraw()

    def show_marker(img, x, y):
        win = tk.Toplevel()
        win.overrideredirect(True)
        win.geometry(f"{MARKER_SIZE}x{MARKER_SIZE}+{x}+{y}")
        photo = tk.PhotoImage(img)
        label = tk.Label(win, image=photo)
        label.image = photo
        label.pack()
        win.lift()
        win.attributes("-topmost", True)

    # Corners
    for i, (x, y) in enumerate([
        (0, 0),
        (screen_width - MARKER_SIZE, 0),
        (0, screen_height - MARKER_SIZE),
        (screen_width - MARKER_SIZE, screen_height - MARKER_SIZE)
    ]):
        img = marker_imgs[i]
        img = img.convert("RGB").resize((MARKER_SIZE, MARKER_SIZE))
        img = ImageTk.PhotoImage(img)
        show_marker(img, x, y)

    root.mainloop()

def main():
    # --- Discover Neon Device ---
    try:
        device = discover_one_device(max_search_duration_seconds=10)
        if device is None:
            print("No device found.")
            return
        calibration = device.get_calibration()
        print("Calibration:", calibration)
    except Exception as e:
        print("Error discovering device:", e)
        return

    gaze_mapper = GazeMapper(calibration)
    screen_surface = gaze_mapper.add_surface(marker_verts, screen_size)
    print("Ready to stream gaze data...")

    # --- Marker Generation ---
    marker_ids = list(range(N_MARKERS))
    markers = [marker_generator.generate_marker(marker_id=i) for i in marker_ids]
    marker_imgs = [Image.fromarray(m) for m in markers]

    # --- Start marker display in a separate thread ---
    marker_thread = threading.Thread(target=show_markers_thread, args=(marker_imgs,), daemon=True)
    marker_thread.start()

    # --- Main Loop ---
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

if __name__ == "__main__":
    main()