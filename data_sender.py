import asyncio
import json  # WARNING: Slow for 200Hz, consider a binary format.
import socket  # Only used for AsyncUDPSender structure, not for direct sending.

from pupil_labs.realtime_api.simple import discover_one_device
from pupil_labs.real_time_screen_gaze.gaze_mapper import GazeMapper

# --- Configuration ---
UNITY_IP = "127.0.0.1"  # IP address
UNITY_PORT = 5005       # UDP port

# pixels
SCREEN_WIDTH_PX = 1920
SCREEN_HEIGHT_PX = 1080
screen_surface_size_px = (SCREEN_WIDTH_PX, SCREEN_HEIGHT_PX)

# AprilTag marker configuration on the screen
#  4 tuples (x, y) representing the marker corners in pixels on the screen.
# Example: a square marker of 80px, with ID 0, placed 50,50px from the top left corner of the screen.
# (top_left, top_right, bottom_right, bottom_left)
MARKER_DISPLAY_SIZE_PX = 80  # Display size of your markers on the screen
PADDING_PX = 50  # Margin from the edges of the screen

marker_verts_screen_px = {
    0: [
        (PADDING_PX, PADDING_PX),
        (PADDING_PX + MARKER_DISPLAY_SIZE_PX, PADDING_PX),
        (PADDING_PX + MARKER_DISPLAY_SIZE_PX, PADDING_PX + MARKER_DISPLAY_SIZE_PX),
        (PADDING_PX, PADDING_PX + MARKER_DISPLAY_SIZE_PX),
    ],
    1: [
        (SCREEN_WIDTH_PX - PADDING_PX - MARKER_DISPLAY_SIZE_PX, PADDING_PX),
        (SCREEN_WIDTH_PX - PADDING_PX, PADDING_PX),
        (SCREEN_WIDTH_PX - PADDING_PX, PADDING_PX + MARKER_DISPLAY_SIZE_PX),
        (SCREEN_WIDTH_PX - PADDING_PX - MARKER_DISPLAY_SIZE_PX, PADDING_PX + MARKER_DISPLAY_SIZE_PX),
    ],
    2: [
        (PADDING_PX, SCREEN_HEIGHT_PX - PADDING_PX - MARKER_DISPLAY_SIZE_PX),
        (PADDING_PX + MARKER_DISPLAY_SIZE_PX, SCREEN_HEIGHT_PX - PADDING_PX - MARKER_DISPLAY_SIZE_PX),
        (PADDING_PX + MARKER_DISPLAY_SIZE_PX, SCREEN_HEIGHT_PX - PADDING_PX),
        (PADDING_PX, SCREEN_HEIGHT_PX - PADDING_PX),
    ],
    3: [
        (SCREEN_WIDTH_PX - PADDING_PX - MARKER_DISPLAY_SIZE_PX, SCREEN_HEIGHT_PX - PADDING_PX - MARKER_DISPLAY_SIZE_PX),
        (SCREEN_WIDTH_PX - PADDING_PX, SCREEN_HEIGHT_PX - PADDING_PX - MARKER_DISPLAY_SIZE_PX),
        (SCREEN_WIDTH_PX - PADDING_PX, SCREEN_HEIGHT_PX - PADDING_PX),
        (SCREEN_WIDTH_PX - PADDING_PX - MARKER_DISPLAY_SIZE_PX, SCREEN_HEIGHT_PX - PADDING_PX),
    ],
}

class AsyncUDPSender:
    """Class to send data via UDP asynchronously."""
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.transport = None

    async def connect(self):
        loop = asyncio.get_running_loop()
        # For sendto only, no need for a complex protocol class.
        # remote_addr specifies the default destination for sendto().
        self.transport, _ = await loop.create_datagram_endpoint(
            lambda: asyncio.DatagramProtocol(),
            remote_addr=(self.host, self.port)
        )
        print(f"UDP Sender ready to send to {self.host}:{self.port}")

    def send_data(self, data_dict: dict):
        if not self.transport:
            print("Error: UDP transport not initialized. Call connect() first.")
            return
        try:
            # WARNING: JSON is slow. For 200Hz, use a binary format.
            message = json.dumps(data_dict).encode('utf-8')
            self.transport.sendto(message)
        except Exception as e:
            print(f"Error sending UDP data: {e}")

    def close(self):
        if self.transport:
            self.transport.close()
            print("UDP Sender connection closed.")


async def stream_data_loop(device, gaze_mapper, surface_definition, udp_sender: AsyncUDPSender):
    """Main loop to retrieve, process, and send data."""
    print("Starting data streaming...")
    async for frame, gaze in device.async_receive_matched_scene_video_frame_and_gaze():
        if frame is None or gaze is None:
            # Can happen if packets are missed or matching fails.
            # print("Missing frame or gaze data.") # Can be verbose
            continue

        # 1. Process with GazeMapper to get surface data
        # `gaze` is a pupil_labs.realtime_api.models.GazeData object
        # `frame` is a pupil_labs.realtime_api.models.VideoFrame object
        surface_gaze_result = gaze_mapper.process_frame(frame, gaze)

        # 2. Prepare raw gaze data
        # The `gaze` object already contains detailed information.
        raw_gaze_data_to_send = {
            "timestamp_unix_seconds": gaze.timestamp_unix_seconds,
            "x_raw_normalized": gaze.x,  # Normalized coordinates in scene camera space
            "y_raw_normalized": gaze.y,
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
            "eyelid_angle_top_left": getattr(gaze, 'eyelid_angle_top_left', None),  # Newer attributes
            "eyelid_angle_bottom_left": getattr(gaze, 'eyelid_angle_bottom_left', None),
            "eyelid_aperture_left": getattr(gaze, 'eyelid_aperture_left', None),
            "eyelid_angle_top_right": getattr(gaze, 'eyelid_angle_top_right', None),
            "eyelid_angle_bottom_right": getattr(gaze, 'eyelid_angle_bottom_right', None),
            "eyelid_aperture_right": getattr(gaze, 'eyelid_aperture_right', None),
        }

        # 3. Prepare surface gaze data
        surface_gaze_list_to_send = []
        if surface_definition.uid in surface_gaze_result.mapped_gaze:
            for surf_gaze_item in surface_gaze_result.mapped_gaze[surface_definition.uid]:
                surface_gaze_list_to_send.append({
                    "timestamp_unix_seconds": surf_gaze_item.timestamp_unix_seconds,
                    "x_surface_px": surf_gaze_item.x,  # Pixel coordinates on the defined surface
                    "y_surface_px": surf_gaze_item.y,
                    "on_surf": surf_gaze_item.on_surf,
                    "confidence": surf_gaze_item.confidence,
                })

        # 4. Combine and send data
        data_payload = {
            "raw_gaze_data": raw_gaze_data_to_send,
            "surface_gaze_data": surface_gaze_list_to_send  # Usually a list with a single element
        }
        udp_sender.send_data(data_payload)
        # print(f"Data sent at {gaze.timestamp_unix_seconds:.3f}") # For debugging

async def run_main_application():
    """Main function to initialize and start the streaming loop."""
    device = None
    udp_sender = None

    try:
        print("Searching for a Pupil Labs device...")
        # discover_one_device is synchronous
        device = discover_one_device(max_search_duration_seconds=10)
        if device is None:
            print("No Pupil Labs device found.")
            return
        print(f"Connected to: {device.phone_name} ({device.dns_name})")

        # Get calibration (synchronous)
        calibration = device.get_calibration()
        print("Calibration received.")

        gaze_mapper = GazeMapper(calibration)

        # Add surface to GazeMapper
        # The `marker_verts_screen_px` must match the IDs and positions of your AprilTag markers
        surface_definition = gaze_mapper.add_surface(
            marker_verts_px=marker_verts_screen_px,
            surface_size_px=screen_surface_size_px
        )
        print(f"Surface '{surface_definition.name}' (ID: {surface_definition.uid}) added to GazeMapper.")

        udp_sender = AsyncUDPSender(host=UNITY_IP, port=UNITY_PORT)
        await udp_sender.connect()

        # Start streaming loop
        await stream_data_loop(device, gaze_mapper, surface_definition, udp_sender)

    except KeyboardInterrupt:
        print("\nStreaming stopped by user.")
    except ConnectionRefusedError:
        print(f"Connection error: Is the UDP receiver on {UNITY_IP}:{UNITY_PORT} active?")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if udp_sender:
            udp_sender.close()
        if device:
            print("Closing device connection...")
            # device.close() is synchronous for simple.Device and handles its own internal async closing.
            device.close()
        print("Application terminated.")

if __name__ == "__main__":
    try:
        asyncio.run(run_main_application())
    except KeyboardInterrupt:
        # Handled in run_main_application, but in case interruption happens earlier.
        print("\nProgram interrupted.")
