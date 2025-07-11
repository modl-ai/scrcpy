#!/usr/bin/env python3
"""
Scrcpy Video Recorder

This script connects to a scrcpy stream and records it to an MP4 file.
Press Ctrl+C to stop recording and save the file.

Usage:
    python scrcpy_recorder.py [port] [socket_name] [output_file]
    
Example:
    python scrcpy_recorder.py 27183 scrcpy_2d7f6828 recording.mp4
"""

import socket
import struct
import sys
import time
import subprocess
import signal
import threading
from datetime import datetime

class ScrcpyRecorder:
    def __init__(self, host='127.0.0.1', port=27183, socket_name=None, output_file=None):
        self.host = host
        self.port = port
        self.socket_name = socket_name
        self.output_file = output_file or f"scrcpy_recording_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4"
        self.video_sock = None
        self.audio_sock = None
        self.control_sock = None
        self.running = False
        self.ffmpeg_process = None
        
    def setup_adb_tunnel(self):
        """Set up ADB tunnel if socket_name is provided"""
        if self.socket_name:
            cmd = f"adb forward tcp:{self.port} localabstract:{self.socket_name}"
            print(f"Setting up ADB tunnel: {cmd}")
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
                if result.returncode == 0:
                    print("ADB tunnel established successfully")
                    return True
                else:
                    print(f"Failed to establish ADB tunnel: {result.stderr}")
                    return False
            except Exception as e:
                print(f"Error setting up ADB tunnel: {e}")
                return False
        else:
            print(f"Connecting to existing tunnel on port {self.port}")
            return True
    
    def connect(self):
        """Connect to all scrcpy sockets"""
        try:
            # Connect to all three sockets in the correct order
            print("Connecting to video socket...")
            self.video_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.video_sock.settimeout(30.0)  # 30 second timeout
            self.video_sock.connect((self.host, self.port))
            print(f"Connected to video socket on {self.host}:{self.port}")
            
            print("Connecting to audio socket...")
            self.audio_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.audio_sock.settimeout(30.0)  # 30 second timeout
            self.audio_sock.connect((self.host, self.port))
            print(f"Connected to audio socket on {self.host}:{self.port}")
            
            print("Connecting to control socket...")
            self.control_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.control_sock.settimeout(30.0)  # 30 second timeout
            self.control_sock.connect((self.host, self.port))
            print(f"Connected to control socket on {self.host}:{self.port}")
            
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def read_device_meta(self):
        """Read device metadata from video socket"""
        try:
            # Check for dummy byte
            print("Checking for dummy byte...")
            self.video_sock.settimeout(2.0)
            dummy_byte = self.video_sock.recv(1)
            if dummy_byte:
                print(f"Received dummy byte: {dummy_byte.hex()}")
            
            # Read device metadata
            print("Reading device metadata...")
            self.video_sock.settimeout(10.0)
            device_meta = self.video_sock.recv(64)
            if len(device_meta) == 64:
                device_name = device_meta.decode('utf-8').rstrip('\x00')
                print(f"Device: {device_name}")
                return True
            else:
                print(f"Failed to read device metadata, got {len(device_meta)} bytes")
                return False
        except Exception as e:
            print(f"Error reading device metadata: {e}")
            return False
    
    def read_video_meta(self):
        """Read video metadata from video socket"""
        try:
            video_meta = self.video_sock.recv(12)
            if len(video_meta) == 12:
                codec_id, width, height = struct.unpack('>III', video_meta)
                print(f"Video: {width}x{height}, codec: 0x{codec_id:08x}")
                
                # Decode codec name
                codec_name = ""
                for i in range(4):
                    codec_name += chr((codec_id >> (24 - i * 8)) & 0xFF)
                print(f"Codec: {codec_name}")
                
                return width, height, codec_name
            else:
                print(f"Failed to read video metadata, got {len(video_meta)} bytes")
                return None, None, None
        except Exception as e:
            print(f"Error reading video metadata: {e}")
            return None, None, None
    
    def start_ffmpeg(self, width, height, codec):
        """Start FFmpeg process to record the video stream"""
        try:
            # Check if FFmpeg is available
            try:
                subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            except (subprocess.CalledProcessError, FileNotFoundError):
                print("Error: FFmpeg is not installed or not in PATH")
                print("Please install FFmpeg to record video streams")
                return False
            
            # FFmpeg command to record H.264 stream with better handling
            cmd = [
                'ffmpeg',
                '-f', 'h264',           # Input format
                '-i', 'pipe:0',         # Read from stdin
                '-c:v', 'copy',         # Copy video codec (no re-encoding)
                '-avoid_negative_ts', 'make_zero',  # Handle timestamp issues
                '-fflags', '+genpts',   # Generate presentation timestamps
                '-y',                   # Overwrite output file
                self.output_file
            ]
            
            print(f"Starting FFmpeg recording to: {self.output_file}")
            print(f"FFmpeg command: {' '.join(cmd)}")
            
            self.ffmpeg_process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                bufsize=0  # Unbuffered output
            )
            
            return True
        except Exception as e:
            print(f"Failed to start FFmpeg: {e}")
            return False
    
    def record_video_stream(self):
        """Record the video stream to FFmpeg"""
        try:
            print("Starting video recording... Press Ctrl+C to stop")
            frame_count = 0
            start_time = time.time()
            
            # Set socket to non-blocking mode for better performance
            self.video_sock.setblocking(True)
            
            while self.running:
                try:
                    # Read frame header (12 bytes)
                    header = self.video_sock.recv(12)
                    if len(header) != 12:
                        print(f"Failed to read frame header, got {len(header)} bytes")
                        break
                    
                    # Parse frame header
                    pts_and_flags = struct.unpack('>Q', header[0:8])[0]
                    size = struct.unpack('>I', header[8:12])[0]
                    
                    # Extract flags from PTS
                    config_flag = (pts_and_flags >> 63) & 1
                    keyframe_flag = (pts_and_flags >> 62) & 1
                    pts = pts_and_flags & ((1 << 62) - 1)
                    
                    # Read frame data more efficiently
                    frame_data = b''
                    remaining = size
                    
                    while remaining > 0:
                        chunk = self.video_sock.recv(remaining)
                        if not chunk:
                            print("Connection closed while reading frame data")
                            break
                        frame_data += chunk
                        remaining -= len(chunk)
                    
                    if len(frame_data) == size:
                        # Write frame data to FFmpeg
                        if self.ffmpeg_process and self.ffmpeg_process.poll() is None:
                            try:
                                self.ffmpeg_process.stdin.write(frame_data)
                                self.ffmpeg_process.stdin.flush()
                            except BrokenPipeError:
                                print("FFmpeg process terminated")
                                break
                        
                        frame_count += 1
                        elapsed = time.time() - start_time
                        fps = frame_count / elapsed if elapsed > 0 else 0
                        
                        if frame_count % 30 == 0:  # Print every 30 frames
                            print(f"Recorded {frame_count} frames ({fps:.1f} fps)")
                    else:
                        print(f"Incomplete frame data: {len(frame_data)}/{size} bytes")
                        break
                        
                except socket.timeout:
                    print("Socket timeout - continuing...")
                    continue
                except Exception as e:
                    print(f"Error reading frame: {e}")
                    break
                    
        except Exception as e:
            print(f"Error recording video stream: {e}")
        finally:
            print(f"Recording stopped. Total frames: {frame_count}")
    
    def stop_recording(self):
        """Stop recording and clean up"""
        print("\nStopping recording...")
        self.running = False
        
        # Close sockets
        if self.video_sock:
            self.video_sock.close()
        if self.audio_sock:
            self.audio_sock.close()
        if self.control_sock:
            self.control_sock.close()
        
        # Stop FFmpeg
        if self.ffmpeg_process:
            self.ffmpeg_process.stdin.close()
            self.ffmpeg_process.wait()
            print(f"Recording saved to: {self.output_file}")
    
    def signal_handler(self, signum, frame):
        """Handle Ctrl+C signal"""
        print("\nReceived interrupt signal")
        self.stop_recording()
        sys.exit(0)
    
    def run(self):
        """Main recording loop"""
        # Set up signal handler for Ctrl+C
        signal.signal(signal.SIGINT, self.signal_handler)
        
        # Set up ADB tunnel
        if not self.setup_adb_tunnel():
            return
        
        # Connect to sockets
        if not self.connect():
            return
        
        # Read device metadata
        if not self.read_device_meta():
            return
        
        # Read video metadata
        width, height, codec = self.read_video_meta()
        if width is None:
            return
        
        # Start FFmpeg recording
        if not self.start_ffmpeg(width, height, codec):
            return
        
        # Start recording
        self.running = True
        self.record_video_stream()

def main():
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    else:
        port = 27183
    
    if len(sys.argv) >= 3:
        socket_name = sys.argv[2]
    else:
        socket_name = "scrcpy_2d7f6828"
    
    if len(sys.argv) >= 4:
        output_file = sys.argv[3]
    else:
        output_file = None
    
    recorder = ScrcpyRecorder(port=port, socket_name=socket_name, output_file=output_file)
    recorder.run()

if __name__ == "__main__":
    main() 