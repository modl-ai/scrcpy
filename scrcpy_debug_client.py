#!/usr/bin/env python3
"""
Scrcpy Debug Client

This script connects to a scrcpy stream and shows the raw packet structure
for debugging and understanding the protocol.

Usage:
    python scrcpy_debug_client.py [port]
    
Example:
    python scrcpy_debug_client.py 27185
"""

import socket
import struct
import sys
import time

class ScrcpyDebugClient:
    def __init__(self, host='127.0.0.1', port=27185):
        self.host = host
        self.port = port
        self.socket = None
        
    def connect(self):
        """Connect to the scrcpy stream"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            print(f"Connected to scrcpy stream on {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Failed to connect: {e}")
            return False
    
    def read_packet(self):
        """Read a single packet from the stream"""
        try:
            # Read packet header (4 bytes for length)
            header = self.socket.recv(4)
            if len(header) != 4:
                return None
            
            # Parse packet length
            packet_length = struct.unpack('>I', header)[0]
            print(f"Packet length: {packet_length} bytes")
            
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
    
    def analyze_packet(self, packet_data):
        """Analyze the packet structure"""
        if not packet_data:
            return
        
        print(f"Packet size: {len(packet_data)} bytes")
        
        # Show first few bytes as hex
        hex_data = ' '.join(f'{b:02x}' for b in packet_data[:32])
        print(f"First 32 bytes: {hex_data}")
        
        # Check for common H.264 start codes
        if packet_data.startswith(b'\x00\x00\x00\x01') or packet_data.startswith(b'\x00\x00\x01'):
            print("✓ H.264 NAL unit detected")
        
        # Show packet type based on first byte
        if len(packet_data) > 0:
            first_byte = packet_data[0]
            nal_type = first_byte & 0x1F
            print(f"NAL type: {nal_type}")
            
            if nal_type == 7:
                print("  → SPS (Sequence Parameter Set)")
            elif nal_type == 8:
                print("  → PPS (Picture Parameter Set)")
            elif nal_type == 5:
                print("  → IDR frame (I-frame)")
            elif nal_type == 1:
                print("  → Non-IDR frame (P-frame)")
            else:
                print(f"  → Other NAL type")
        
        print("-" * 50)
    
    def start(self):
        """Start the debug client"""
        if not self.connect():
            return False
        
        print("Reading packets... Press Ctrl+C to stop")
        print("=" * 50)
        
        packet_count = 0
        start_time = time.time()
        
        try:
            while True:
                packet_data = self.read_packet()
                if packet_data is None:
                    print("Connection closed")
                    break
                
                packet_count += 1
                elapsed_time = time.time() - start_time
                
                print(f"\nPacket #{packet_count} (elapsed: {elapsed_time:.2f}s)")
                self.analyze_packet(packet_data)
                
        except KeyboardInterrupt:
            print(f"\nStopped after {packet_count} packets")
        finally:
            self.stop()
        
        return True
    
    def stop(self):
        """Stop the debug client"""
        if self.socket:
            self.socket.close()

def main():
    # Get port from command line argument or use default
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 27185
    
    print(f"Scrcpy Debug Client")
    print(f"Connecting to port: {port}")
    print(f"Make sure scrcpy server is running with --server-only mode")
    print()
    
    client = ScrcpyDebugClient(port=port)
    client.start()

if __name__ == "__main__":
    main() 