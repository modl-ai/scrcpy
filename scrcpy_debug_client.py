#!/usr/bin/env python3
"""
Scrcpy Debug Client

This script connects to a scrcpy stream and shows the raw packet structure
for debugging and understanding the protocol.

Usage:
    python scrcpy_debug_client.py [port] [socket_name]
    
Example:
    # First, set up the ADB tunnel:
    # adb forward tcp:27183 localabstract:scrcpy_29c1bca9
    
    # Then run this script:
    python scrcpy_debug_client.py 27183
"""

import socket
import struct
import sys
import time
import subprocess

class ScrcpyDebugClient:
    def __init__(self, host='127.0.0.1', port=27183, socket_name=None):
        self.host = host
        self.port = port
        self.socket_name = socket_name
        self.socket = None
        
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
            # If no socket_name provided, assume tunnel is already set up
            print(f"Connecting to existing tunnel on port {self.port}")
            return True
        
    def connect(self):
        """Connect to the scrcpy stream"""
        try:
            # Set up ADB tunnel if needed
            if not self.setup_adb_tunnel():
                return False
                
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            print(f"Connected to scrcpy stream on {self.host}:{self.port}")
            
            # Check for dummy byte (sent on forward connections)
            print("Checking for dummy byte...")
            # Set a short timeout for the dummy byte check
            self.socket.settimeout(2.0)
            try:
                dummy_byte = self.socket.recv(1)
                if dummy_byte:
                    print(f"Dummy byte detected: {dummy_byte.hex()}")
                else:
                    print("No dummy byte detected")
            except socket.timeout:
                print("Timeout waiting for dummy byte - proceeding anyway")
            except Exception as e:
                print(f"Error checking for dummy byte: {e}")
            
            # Reset timeout for normal operation
            self.socket.settimeout(None)
            
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def read_device_meta(self):
        """Read device metadata (device name) from the first socket"""
        try:
            # Set timeout for reading device metadata
            self.socket.settimeout(10.0)  # Increased timeout
            
            print("Waiting for device metadata...")
            # Read device name (64 bytes)
            device_name_bytes = self.socket.recv(64)
            print(f"Received {len(device_name_bytes)} bytes for device metadata")
            
            if len(device_name_bytes) == 64:
                device_name = device_name_bytes.decode('utf-8').rstrip('\x00')
                print(f"Device: {device_name}")
                return True
            elif len(device_name_bytes) > 0:
                # Try to decode what we got
                try:
                    partial_name = device_name_bytes.decode('utf-8').rstrip('\x00')
                    print(f"Partial device name: {partial_name}")
                    print(f"First few bytes: {device_name_bytes[:16].hex()}")
                except:
                    print(f"Raw bytes: {device_name_bytes.hex()}")
                return False
            else:
                print("No device metadata received (connection closed)")
                return False
        except socket.timeout:
            print("Timeout waiting for device metadata")
            print("This might mean:")
            print("  1. The server is not ready yet")
            print("  2. The server encountered an error")
            print("  3. The connection protocol is different")
            return False
        except Exception as e:
            print(f"Error reading device metadata: {e}")
            return False
        finally:
            # Reset timeout
            self.socket.settimeout(None)
    
    def read_video_meta(self):
        """Read video metadata (codec info and dimensions)"""
        try:
            # Read codec metadata (12 bytes)
            # - codec id (4 bytes)
            # - width (4 bytes) 
            # - height (4 bytes)
            meta = self.socket.recv(12)
            if len(meta) == 12:
                codec_id, width, height = struct.unpack('>III', meta)
                print(f"Video: {width}x{height}, codec: 0x{codec_id:08x}")
                
                # Decode codec name
                codec_name = ""
                for i in range(4):
                    codec_name += chr((codec_id >> (24 - i * 8)) & 0xFF)
                print(f"Codec name: '{codec_name}'")
                
                return width, height
            else:
                print(f"Failed to read video metadata, got {len(meta)} bytes")
                return None, None
        except Exception as e:
            print(f"Error reading video metadata: {e}")
            return None, None
    
    def read_frame_header(self):
        """Read frame header (12 bytes)"""
        try:
            header = self.socket.recv(12)
            if len(header) == 12:
                # Parse frame header
                # - config packet flag (1 bit)
                # - key frame flag (1 bit) 
                # - PTS (62 bits)
                # - packet size (32 bits)
                flags_pts, packet_size = struct.unpack('>QI', header)
                is_config = (flags_pts >> 63) & 1
                is_keyframe = (flags_pts >> 62) & 1
                pts = flags_pts & ((1 << 62) - 1)
                return {
                    'is_config': is_config,
                    'is_keyframe': is_keyframe,
                    'pts': pts,
                    'size': packet_size
                }
            else:
                print(f"Failed to read frame header, got {len(header)} bytes")
                return None
        except Exception as e:
            print(f"Error reading frame header: {e}")
            return None
    
    def read_frame_data(self, size):
        """Read frame data"""
        try:
            data = b''
            while len(data) < size:
                chunk = self.socket.recv(size - len(data))
                if not chunk:
                    return None
                data += chunk
            return data
        except Exception as e:
            print(f"Error reading frame data: {e}")
            return None
    
    def run(self):
        """Main loop to read and analyze packets"""
        if not self.connect():
            return
        
        # Read device metadata
        if not self.read_device_meta():
            return
        
        # Read video metadata
        width, height = self.read_video_meta()
        if width is None or height is None:
            return
        
        print(f"Starting packet analysis ({width}x{height})")
        print("Press Ctrl+C to stop")
        
        frame_count = 0
        start_time = time.time()
        
        try:
            while True:
                # Read frame header
                header = self.read_frame_header()
                if header is None:
                    print("Failed to read frame header, stopping")
                    break
                
                # Read frame data
                frame_data = self.read_frame_data(header['size'])
                if frame_data is None:
                    print("Failed to read frame data, stopping")
                    break
                
                # Analyze the frame
                frame_count += 1
                elapsed = time.time() - start_time
                fps = frame_count / elapsed if elapsed > 0 else 0
                
                print(f"Frame {frame_count}: "
                      f"size={header['size']}, "
                      f"config={header['is_config']}, "
                      f"keyframe={header['is_keyframe']}, "
                      f"pts={header['pts']}, "
                      f"fps={fps:.1f}")
                
                # Show first few bytes of frame data for debugging
                if frame_count <= 3:
                    print(f"  First 16 bytes: {frame_data[:16].hex()}")
                
        except KeyboardInterrupt:
            print(f"\nStopped by user. Processed {frame_count} frames in {time.time() - start_time:.1f}s")
        except Exception as e:
            print(f"Error during packet analysis: {e}")
        finally:
            if self.socket:
                self.socket.close()

def main():
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])
    else:
        port = 27183
    
    if len(sys.argv) >= 3:
        socket_name = sys.argv[2]
    else:
        socket_name = "scrcpy_29c1bca9"
    
    client = ScrcpyDebugClient(port=port, socket_name=socket_name)
    client.run()

if __name__ == "__main__":
    main() 