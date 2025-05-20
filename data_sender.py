import asyncio
import json  # WARNING: Slow for 200Hz, consider a binary format.
# socket import is not strictly needed here anymore as AsyncUDPSender handles its needs.

from pupil_labs.real_time_screen_gaze.gaze_mapper import GazeMapper
# Use asynchronous components
from pupil_labs.realtime_api.discovery import Network
from pupil_labs.realtime_api.device import Device
from pupil_labs.realtime_api.streaming.gaze import RTSPGazeStreamer
from pupil_labs.realtime_api.streaming.video import RTSPVideoFrameStreamer
from pupil_labs.realtime_api.streaming.
from pupil_labs.realtime_api import models # For Status, GazeData, VideoFrame if type hinting

# --- Configuration ---
UNITY_IP = "127.0.0.1"  # IP address
UNITY_PORT = 5005       # UDP port

# pixels
SCREEN_WIDTH_PX = 1920
SCREEN_HEIGHT_PX = 1080
screen_surface_size_px = (SCREEN_WIDTH_PX, SCREEN_HEIGHT_PX)

MARKER_DISPLAY_SIZE_PX = 80
PADDING_PX = 50

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
            message = json.dumps(data_dict).encode('utf-8')
            self.transport.sendto(message)
        except Exception as e:
            print(f"Error sending UDP data: {e}")

    def close(self):
        if self.transport:
            self.transport.close()
            print("UDP Sender connection closed.")


async def stream_data_from_matcher(matcher: DataMatcher, gaze_mapper: GazeMapper, surface_definition, udp_sender: AsyncUDPSender):
    """Main loop to retrieve, process, and send data using DataMatcher."""
    print("Starting data streaming with matcher...")
    async with matcher: # Use matcher as an async context manager
        async for item in matcher.receive(): # item is MatchedItem(gaze, frame)
            gaze: models.GazeData = item.gaze
            frame: models.VideoFrame = item.frame

            if frame is None or gaze is None:
                continue

            surface_gaze_result = gaze_mapper.process_frame(frame, gaze)

            raw_gaze_data_to_send = {
                "timestamp_unix_seconds": gaze.timestamp_unix_seconds,
                "x_raw_normalized": gaze.x,
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
                "eyelid_angle_top_left": getattr(gaze, 'eyelid_angle_top_left', None),
                "eyelid_angle_bottom_left": getattr(gaze, 'eyelid_angle_bottom_left', None),
                "eyelid_aperture_left": getattr(gaze, 'eyelid_aperture_left', None),
                "eyelid_angle_top_right": getattr(gaze, 'eyelid_angle_top_right', None),
                "eyelid_angle_bottom_right": getattr(gaze, 'eyelid_angle_bottom_right', None),
                "eyelid_aperture_right": getattr(gaze, 'eyelid_aperture_right', None),
            }

            surface_gaze_list_to_send = []
            if surface_definition.uid in surface_gaze_result.mapped_gaze:
                for surf_gaze_item in surface_gaze_result.mapped_gaze[surface_definition.uid]:
                    surface_gaze_list_to_send.append({
                        "timestamp_unix_seconds": surf_gaze_item.timestamp_unix_seconds,
                        "x_surface_px": surf_gaze_item.x,
                        "y_surface_px": surf_gaze_item.y,
                        "on_surf": surf_gaze_item.on_surf,
                        "confidence": surf_gaze_item.confidence,
                    })

            data_payload = {
                "raw_gaze_data": raw_gaze_data_to_send,
                "surface_gaze_data": surface_gaze_list_to_send
            }
            udp_sender.send_data(data_payload)

async def run_main_application():
    """Main function to initialize and start the streaming loop."""
    network = Network()
    async_pl_device = None
    udp_sender = None

    try:
        print("Searching for a Pupil Labs device (async)...")
        device_info = await network.wait_for_new_device(timeout_seconds=10)
       
        if device_info is None:
            print("No Pupil Labs device found.")
            return
        # device_info is DiscoveredDeviceInfo, has .name, .address, .port
        print(f"Device info found: {device_info.name} at {device_info.address}:{device_info.port}")

        async_pl_device = Device(host=device_info.address, port=device_info.port)
        
        # Get status to confirm connection and get stream URLs
        # This will implicitly connect if the Device class handles it upon first API call.
        status = await async_pl_device.get_status()
        print(f"Connected to: {status.phone.device_name if status.phone else 'Unknown Device Name'}") # status.phone might be None

        calibration = await async_pl_device.get_calibration()
        print("Calibration received.")

        gaze_mapper = GazeMapper(calibration)

        surface_definition = gaze_mapper.add_surface(
            marker_verts_px=marker_verts_screen_px,
            surface_size_px=screen_surface_size_px
        )
        print(f"Surface '{surface_definition.name}' (ID: {surface_definition.uid}) added to GazeMapper.")

        udp_sender = AsyncUDPSender(host=UNITY_IP, port=UNITY_PORT)
        await udp_sender.connect()

        # Get streaming URLs from status
        gaze_url = status.direct_gaze_url()
        video_url = status.direct_scene_video_url()

        if not gaze_url:
            print("Could not get gaze streaming URL from device status.")
            return
        if not video_url:
            print("Could not get scene video streaming URL from device status.")
            return
            
        print(f"Gaze stream URL: {gaze_url}")
        print(f"Video stream URL: {video_url}")

        gaze_streamer = RTSPGazeStreamer(url=gaze_url)
        video_streamer = RTSPVideoFrameStreamer(url=video_url)
        matcher = DataMatcher(gaze_streamer=gaze_streamer, frame_streamer=video_streamer)

        await stream_data_from_matcher(matcher, gaze_mapper, surface_definition, udp_sender)

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
        if async_pl_device:
            print("Closing device connection (async)...")
            await async_pl_device.close()
        print("Closing network discovery...")
        await network.close() # Close the network discovery
        print("Application terminated.")

if __name__ == "__main__":
    try:
        asyncio.run(run_main_application())
    except KeyboardInterrupt:
        print("\nProgram interrupted.")
