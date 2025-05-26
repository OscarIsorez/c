import struct
import sys
import json
import socket # Added import

from pupil_labs.realtime_api.simple import discover_one_device
from pupil_labs.real_time_screen_gaze.gaze_mapper import GazeMapper

from PySide6.QtCore import *
from PySide6.QtGui import *
from PySide6.QtWidgets import *

import pyautogui

from ui import TagWindow
from dwell_detector import DwellDetector

pyautogui.FAILSAFE = False
# --- Configuration ---
UNITY_IP = "127.0.0.1"  # IP address
UNITY_PORT = 5005       # UDP port


class PupilPointerApp(QApplication):
    def __init__(self):
        super().__init__()

        self.setApplicationDisplayName('Pupil Pointer')
        self.mouseEnabled = False

        self.tagWindow = TagWindow()

        self.device = None
        self.dwellDetector = DwellDetector(.75, 75)
        self.smoothing = 0.3 # Changed from 0.8 to 0.3 for more responsiveness
        self.gazeFrequency = 0 # Add new instance variable for frequency

        # Initialize UDP Socket
        self.udp_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.tagWindow.surfaceChanged.connect(self.onSurfaceChanged)

        self.tagWindow.dwellTimeChanged.connect(self.dwellDetector.setDuration)
        self.tagWindow.dwellRadiusChanged.connect(self.dwellDetector.setRange)
        self.tagWindow.mouseEnableChanged.connect(self.setMouseEnabled)
        self.tagWindow.smoothingChanged.connect(self.setSmoothing)
        self.tagWindow.leftTagOffsetChanged.connect(self.onSurfaceChanged) # Connect renamed signal
        self.tagWindow.rightTagOffsetChanged.connect(self.onSurfaceChanged) # Connect new signal

        self.last_timestamps = []

        self.pollTimer = QTimer()
        self.pollTimer.setInterval(int(1000 / 60)) # Changed from 1000 / 30 to poll at 60Hz 
        self.pollTimer.timeout.connect(self.poll)

        self.surface = None
        self.firstPoll = True

        self.mousePosition = None
        self.gazeMapper = None

    def onSurfaceChanged(self):
        self.updateSurface()

    def start(self):
        self.device = discover_one_device(max_search_duration_seconds=0.25)

        if self.device is None:
            QTimer.singleShot(1000, self.start)
            return

        calibration = self.device.get_calibration()
        self.gazeMapper = GazeMapper(calibration)

        self.tagWindow.setStatus(f'Connected to {self.device}. One moment...')

        self.updateSurface()
        self.pollTimer.start()
        self.firstPoll = True

    def updateSurface(self):
        if self.gazeMapper is None:
            return

        self.gazeMapper.clear_surfaces()
        self.surface = self.gazeMapper.add_surface(
            self.tagWindow.getMarkerVerts(),
            self.tagWindow.getSurfaceSize()
        )

    def setMouseEnabled(self, enabled):
        self.mouseEnabled = enabled

    def setSmoothing(self, value):
        self.smoothing = value

    def poll(self):
        # Changed timeout_seconds from 1/15 to 1/100 (10ms)
        frameAndGaze = self.device.receive_matched_scene_video_frame_and_gaze(timeout_seconds=1/100)

        # Removed self.device.estimate_time_offset() from the poll loop
        # estimate_offset = self.device.estimate_time_offset( # This call can remain if useful
        # )
        # print(f"Estimate offset  {estimate_offset}")

        
        if frameAndGaze is None:
            return # No new frame and gaze data, so exit poll early

        self.tagWindow.setStatus(f'Streaming data from {self.device}')
        self.firstPoll = False

        frame, gaze = frameAndGaze

        if gaze and hasattr(gaze, 'timestamp_unix_seconds'):
            current_gaze_timestamp = gaze.timestamp_unix_seconds
            
            if len(self.last_timestamps) < 2:
                self.last_timestamps.append(current_gaze_timestamp)
            else:
                self.last_timestamps[0] = self.last_timestamps[1]
                self.last_timestamps[1] = current_gaze_timestamp

            if len(self.last_timestamps) == 2:
                time_difference = self.last_timestamps[1] - self.last_timestamps[0]
                if time_difference > 1e-6:  # Ensure a positive and non-trivial time difference (e.g., > 1 microsecond)
                    self.gazeFrequency = 1.0 / time_difference
                    self.tagWindow.setFrequency(self.gazeFrequency)
                # else: # Optional: handle cases where timestamps are identical or too close
                    # self.tagWindow.setFrequency(0) # Or display "N/A", or keep last valid frequency

        result = self.gazeMapper.process_frame(frame, gaze)

        markerIds = [int(marker.uid.split(':')[-1]) for marker in result.markers]
        self.tagWindow.showMarkerFeedback(markerIds)
        
        if self.surface.uid in result.mapped_gaze:
            for surface_gaze in result.mapped_gaze[self.surface.uid]:
                current_smoothed_norm_x = 0.0
                current_smoothed_norm_y = 0.0
                if self.mousePosition is None:
                    self.mousePosition = [surface_gaze.x, surface_gaze.y] 

                    current_smoothed_norm_x = self.mousePosition[0]
                    current_smoothed_norm_y = self.mousePosition[1]
                else:
                    current_smoothed_norm_x = self.mousePosition[0] * self.smoothing + surface_gaze.x * (1.0 - self.smoothing)
                    current_smoothed_norm_y = self.mousePosition[1] * self.smoothing + surface_gaze.y * (1.0 - self.smoothing)

                window_width = self.tagWindow.width()
                window_height = self.tagWindow.height()
                
                candidate_screen_x = 0.0
                candidate_screen_y = 0.0
                if window_width > 0 and window_height > 0:
                    candidate_screen_x = current_smoothed_norm_x * window_width
                    candidate_screen_y = current_smoothed_norm_y * window_height
                else: 
                    candidate_screen_x = current_smoothed_norm_x * 1920 
                    candidate_screen_y = current_smoothed_norm_y * 1080


                dwell_timestamp = gaze.timestamp_unix_seconds if gaze and hasattr(gaze, 'timestamp_unix_seconds') else 0
                if dwell_timestamp == 0 and self.last_timestamps: 
                    dwell_timestamp = self.last_timestamps[-1]
                
                changed, dwell, dwellPosition = self.dwellDetector.addPoint(candidate_screen_x, candidate_screen_y, dwell_timestamp)

                final_norm_x = 0.0
                final_norm_y = 0.0
                final_screen_qpoint = QPoint()

                if dwell and dwellPosition is not None:
                    if window_width > 0 and window_height > 0:
                        final_norm_x = dwellPosition[0] / window_width
                        final_norm_y = 1.0 - (dwellPosition[1] / window_height)
                    else: 
                        final_norm_x = current_smoothed_norm_x
                        final_norm_y = current_smoothed_norm_y
                    
                    final_screen_qpoint = QPoint(int(dwellPosition[0]), int(dwellPosition[1]))
                else:
                    final_norm_x = current_smoothed_norm_x
                    final_norm_y = current_smoothed_norm_y
                    final_screen_qpoint = QPoint(int(candidate_screen_x), int(candidate_screen_y))

                final_norm_x = max(0.0, min(1.0, final_norm_x))
                final_norm_y = max(0.0, min(1.0, final_norm_y))
                self.mousePosition = [final_norm_x, final_norm_y]

                mousePoint = self.tagWindow.updatePoint(final_norm_x, final_norm_y) 
                try:
                    message = f"{mousePoint.x()},{mousePoint.y(),},  {current_gaze_timestamp}"
                    packet = struct.pack('<ffd', mousePoint.x(), mousePoint.y(), current_gaze_timestamp)
                    self.udp_socket.sendto(packet, (UNITY_IP, UNITY_PORT))
                    print(f"Sent UDP data: {message}")
                except Exception as e:
                    print(f"Error sending UDP data: {e}")


                if changed and dwell and dwellPosition is not None:
                    self.tagWindow.setClicked(False)
                    if self.mouseEnabled:
                        pyautogui.click(x=int(dwellPosition[0]), y=int(dwellPosition[1]))
                else:
                    self.tagWindow.setClicked(False)

                if self.mouseEnabled:
                    QCursor().setPos(final_screen_qpoint) 

            if len(result.mapped_gaze[self.surface.uid]) == 0:
                print("No gaze data")
    def exec(self):
        self.tagWindow.setStatus('Looking for a device...')
        self.tagWindow.showMaximized()
        QTimer.singleShot(1000, self.start)
        super().exec()
        if self.device is not None:
            self.device.close()
        if self.udp_socket: 
            self.udp_socket.close()

def run():
    app = PupilPointerApp()
    app.exec()
if __name__ == "__main__":
    run()