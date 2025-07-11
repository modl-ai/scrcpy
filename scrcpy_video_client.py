#!/usr/bin/env python3
"""
Scrcpy Video Stream Client

This script demonstrates how to connect to a scrcpy video stream
and decode the H.264 video data using Python.

Requirements:
    pip install opencv-python numpy av

Usage:
    python scrcpy_video_client.py [port]
    
Example:
    python scrcpy_video_client.py 27185
"""

import socket
import struct
import threading
import time
import sys
import cv2
import numpy as np
import av
from io import BytesIO

class ScrcpyVideoClient:
    def __init__(self, host='127.0.0.1', port=27185):
        self.host = host
        self.port = port
        self.socket = None
        self.running = False
        self.decoder = None
        
    def connect(self):
        """Connect to the scrcpy video stream"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            print(f"Connected to scrcpy video stream on {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def read_packet(self):
        """Read a single packet from the video stream"""
        try:
            # Read packet header (4 bytes for length)
            header = self.socket.recv(4)
            if len(header) != 4:
                return None
            
            # Parse packet length
            packet_length = struct.unpack('>I', header)[0]
            
            # Read packet data
            packet_data = b''
            while len(packet_data) < packet_length:
                chunk = self.socket.recv(packet_length - len(packet_data))
                if not chunk:
                    return None
                packet_data += chunk
            
            return packet_data
            
        except Exception as e:
            print(f"Error reading packet: {e}")
            return None
    
    def decode_h264_frame(self, h264_data):
        """Decode H.264 data to RGB frame using PyAV"""
        try:
            # Create a BytesIO object for PyAV
            input_buffer = BytesIO(h264_data)
            
            # Use PyAV to decode the H.264 data
            container = av.open(input_buffer, format='h264')
            
            for frame in container.decode(video=0):
                # Convert to RGB
                rgb_frame = frame.to_ndarray(format='rgb24')
                return rgb_frame
                
        except Exception as e:
            print(f"Error decoding H.264 frame: {e}")
            return None
    
    def display_frame(self, frame):
        """Display the frame using OpenCV"""
        if frame is not None:
            # Convert RGB to BGR for OpenCV
            bgr_frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            cv2.imshow('Scrcpy Video Stream', bgr_frame)
            
            # Press 'q' to quit
            if cv2.waitKey(1) & 0xFF == ord('q'):
                return False
        return True
    
    def video_loop(self):
        """Main video processing loop"""
        print("Starting video stream...")
        print("Press 'q' to quit")
        
        frame_count = 0
        start_time = time.time()
        
        while self.running:
            # Read packet from socket
            packet_data = self.read_packet()
            if packet_data is None:
                print("Connection closed")
                break
            
            # Decode H.264 frame
            frame = self.decode_h264_frame(packet_data)
            if frame is not None:
                frame_count += 1
                
                # Calculate FPS
                elapsed_time = time.time() - start_time
                if elapsed_time > 0:
                    fps = frame_count / elapsed_time
                    print(f"FPS: {fps:.2f}, Frame: {frame_count}", end='\r')
                
                # Display frame
                if not self.display_frame(frame):
                    break
            else:
                print("Failed to decode frame")
        
        cv2.destroyAllWindows()
    
    def start(self):
        """Start the video client"""
        if not self.connect():
            return False
        
        self.running = True
        
        # Start video processing in a separate thread
        video_thread = threading.Thread(target=self.video_loop)
        video_thread.daemon = True
        video_thread.start()
        
        try:
            # Keep main thread alive
            while self.running:
                time.sleep(0.1)
        except KeyboardInterrupt:
            print("\nStopping video client...")
        finally:
            self.stop()
        
        return True
    
    def stop(self):
        """Stop the video client"""
        self.running = False
        if self.socket:
            self.socket.close()
        cv2.destroyAllWindows()

def main():
    # Get port from command line argument or use default
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 27185
    
    print(f"Scrcpy Video Client")
    print(f"Connecting to port: {port}")
    print(f"Make sure scrcpy server is running with --server-only mode")
    print()
    
    client = ScrcpyVideoClient(port=port)
    client.start()

if __name__ == "__main__":
    main() 