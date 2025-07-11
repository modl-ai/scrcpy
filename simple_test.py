#!/usr/bin/env python3
"""
Simple test script to connect to scrcpy server and read raw data
"""

import socket
import struct
import sys
import time
import subprocess

def setup_adb_tunnel(port, socket_name):
    """Set up ADB tunnel"""
    cmd = f"adb forward tcp:{port} localabstract:{socket_name}"
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

def connect_and_test(port, socket_name):
    """Connect to scrcpy server and test protocol"""
    host = '127.0.0.1'
    
    # Set up ADB tunnel
    if not setup_adb_tunnel(port, socket_name):
        return
    
    try:
        # Connect to all three sockets in the correct order
        # scrcpy protocol expects: video, audio, control
        print("Connecting to video socket...")
        video_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        video_sock.connect((host, port))
        print(f"Connected to video socket on {host}:{port}")
        
        print("Connecting to audio socket...")
        audio_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        audio_sock.connect((host, port))
        print(f"Connected to audio socket on {host}:{port}")
        
        print("Connecting to control socket...")
        control_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        control_sock.connect((host, port))
        print(f"Connected to control socket on {host}:{port}")
        
        # Now read from the first socket (video) for device metadata
        print("\n1. Checking for dummy byte on video socket...")
        video_sock.settimeout(2.0)
        try:
            dummy_byte = video_sock.recv(1)
            if dummy_byte:
                print(f"Received dummy byte: {dummy_byte.hex()}")
            else:
                print("No dummy byte received")
        except socket.timeout:
            print("Timeout waiting for dummy byte - proceeding anyway")
        except Exception as e:
            print(f"Error reading dummy byte: {e}")
        
        # Step 2: Read device metadata (64 bytes) from video socket
        print("\n2. Reading device metadata from video socket...")
        video_sock.settimeout(10.0)
        try:
            device_meta = video_sock.recv(64)
            print(f"Received {len(device_meta)} bytes for device metadata")
            if len(device_meta) == 64:
                device_name = device_meta.decode('utf-8').rstrip('\x00')
                print(f"Device name: {device_name}")
            else:
                print(f"Partial device metadata: {device_meta.hex()}")
        except socket.timeout:
            print("Timeout waiting for device metadata")
            return
        except Exception as e:
            print(f"Error reading device metadata: {e}")
            return
        
        # Step 3: Read video metadata (12 bytes: codec_id, width, height)
        print("\n3. Reading video metadata...")
        try:
            video_meta = video_sock.recv(12)
            print(f"Received {len(video_meta)} bytes for video metadata")
            if len(video_meta) == 12:
                codec_id, width, height = struct.unpack('>III', video_meta)
                print(f"Video: {width}x{height}, codec: 0x{codec_id:08x}")
                
                # Decode codec name
                codec_name = ""
                for i in range(4):
                    codec_name += chr((codec_id >> (24 - i * 8)) & 0xFF)
                print(f"Codec name: '{codec_name}'")
            else:
                print(f"Partial video metadata: {video_meta.hex()}")
        except Exception as e:
            print(f"Error reading video metadata: {e}")
            return
        
        # Step 4: Read video frames
        print("\n4. Reading video frames...")
        frame_count = 0
        try:
            while frame_count < 5:  # Read first 5 frames
                # Read frame header (12 bytes)
                header = video_sock.recv(12)
                if len(header) != 12:
                    print(f"Failed to read frame header, got {len(header)} bytes")
                    break
                
                # Parse frame header
                # Format: 8 bytes PTS (with flags in MSB) + 4 bytes packet size
                pts_and_flags = struct.unpack('>Q', header[0:8])[0]
                size = struct.unpack('>I', header[8:12])[0]
                
                # Extract flags from PTS (flags are in the 2 most significant bits)
                config_flag = (pts_and_flags >> 63) & 1
                keyframe_flag = (pts_and_flags >> 62) & 1
                pts = pts_and_flags & ((1 << 62) - 1)  # Remove the 2 flag bits
                
                print(f"Frame {frame_count + 1}: size={size}, config={config_flag}, keyframe={keyframe_flag}, pts={pts}")
                
                # Read frame data
                frame_data = video_sock.recv(size)
                if len(frame_data) != size:
                    print(f"Failed to read frame data, got {len(frame_data)} bytes, expected {size}")
                    break
                
                frame_count += 1
                
        except Exception as e:
            print(f"Error reading video frames: {e}")
        
        print(f"\nSuccessfully read {frame_count} frames")
        
        # Clean up
        video_sock.close()
        audio_sock.close()
        control_sock.close()
        
    except Exception as e:
        print(f"Connection error: {e}")
        return

def main():
    if len(sys.argv) < 3:
        print("Usage: python simple_test.py <port> <socket_name>")
        print("Example: python simple_test.py 27183 scrcpy_5d9de392")
        sys.exit(1)
    
    port = int(sys.argv[1])
    socket_name = sys.argv[2]
    
    connect_and_test(port, socket_name)

if __name__ == "__main__":
    main() 