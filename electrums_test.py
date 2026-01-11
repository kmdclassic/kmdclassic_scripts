#!/usr/bin/env python3
"""
Script to test Electrum servers by making verbose blockchain.transaction.get requests.

Copyright (c) KmdClassic, 2025
"""

import json
import socket
import sys
import time
from typing import Dict, Any, Optional, Tuple


# ANSI color codes for output formatting
GREEN = '\033[32m'
YELLOW = '\033[33m'
RED = '\033[31m'
BLUE = '\033[34m'
CYAN = '\033[36m'
GRAY = '\033[90m'
RESET = '\033[0m'
BOLD = '\033[1m'

# Transaction hash to query
TX_HASH = "adf3a2698e31900f9b710da73d71748cda96ce26b12bddcb8d69eaa835bedc73"

# Electrum servers to test
SERVERS = [
    {
        "host": "kmd.electrum3.cipig.net",
        "port": 10001,
        "name": "Electrum Server 1 (cipig.net)"
    },
    {
        "host": "electrum.kmdclassic.com",
        "port": 50001,
        "name": "Electrum Server 2 (kmdclassic.com)"
    }
]


def connect_to_server(host: str, port: int, timeout: int = 10) -> Optional[socket.socket]:
    """
    Establish TCP connection to Electrum server.
    
    Args:
        host: Server hostname
        port: Server port
        timeout: Connection timeout in seconds
        
    Returns:
        Socket object if successful, None otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect((host, port))
        return sock
    except socket.timeout:
        print(f"{RED}  Connection timeout{RESET}")
        return None
    except socket.gaierror as e:
        print(f"{RED}  DNS resolution failed: {e}{RESET}")
        return None
    except ConnectionRefusedError:
        print(f"{RED}  Connection refused{RESET}")
        return None
    except Exception as e:
        print(f"{RED}  Connection error: {e}{RESET}")
        return None


def send_request(sock: socket.socket, method: str, params: list, request_id: int = 1) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    Send JSON-RPC request to Electrum server and read full response.
    
    According to Electrum protocol, each JSON-RPC message is separated by newline.
    We need to read all data until the server stops sending (connection closed or no more data).
    
    Args:
        sock: Connected socket
        method: RPC method name
        params: Method parameters
        request_id: Request ID for JSON-RPC
        
    Returns:
        Tuple of (Response dictionary or None if failed, elapsed time in seconds)
    """
    # Build JSON-RPC request
    request = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params
    }
    
    # Convert to JSON string and add newline (Electrum protocol requirement)
    request_json = json.dumps(request) + "\n"
    
    # Start timing
    start_time = time.time()
    
    try:
        # Send request
        sock.sendall(request_json.encode('utf-8'))
        
        # Receive full response
        # Electrum protocol: read all data until server stops sending
        # Each JSON-RPC message is separated by newline
        response_data = b""
        
        # Set socket to non-blocking mode temporarily to check for more data
        sock.settimeout(2.0)  # 2 second timeout for reading
        
        # Read all available data
        while True:
            try:
                chunk = sock.recv(65536)  # Read up to 64KB at a time
                if not chunk:
                    # No more data available (connection closed or EOF)
                    break
                response_data += chunk
                
                # Try to read more if available, but don't wait too long
                # If no data arrives within timeout, assume we got everything
            except socket.timeout:
                # No more data available within timeout
                # Check if we have any data, if yes, try one more recv with very short timeout
                if response_data:
                    # Set very short timeout for final check
                    sock.settimeout(0.1)
                    try:
                        final_chunk = sock.recv(65536)
                        if final_chunk:
                            response_data += final_chunk
                            continue
                    except socket.timeout:
                        pass
                break
            except Exception as e:
                # Other socket errors - break and try to parse what we have
                print(f"{GRAY}  Socket read error (may be normal): {e}{RESET}")
                break
        
        # Calculate elapsed time
        elapsed_time = time.time() - start_time
        
        if not response_data:
            print(f"{RED}  No response data received{RESET}")
            return None, elapsed_time
        
        # Decode response
        try:
            response_str = response_data.decode('utf-8')
        except UnicodeDecodeError as e:
            print(f"{RED}  Unicode decode error: {e}{RESET}")
            print(f"{GRAY}  Response length: {len(response_data)} bytes{RESET}")
            return None, elapsed_time
        
        # Electrum protocol: messages are separated by newlines
        # Split by newlines and parse each message
        messages = response_str.strip().split('\n')
        
        # Find the response that matches our request ID
        for msg in messages:
            if not msg.strip():
                continue
            try:
                parsed = json.loads(msg)
                # Check if this is a response (has 'id' field) matching our request
                if isinstance(parsed, dict):
                    # Check if it's a response to our request
                    if 'id' in parsed and parsed['id'] == request_id:
                        return parsed, elapsed_time
                    # Also handle notifications (no 'id' field) - but we want the response
                    # If we don't find a matching response, return the first valid JSON
            except json.JSONDecodeError:
                # Skip invalid JSON messages
                continue
        
        # If no matching response found, try to parse the entire response as one JSON
        # (some servers might send everything as one message)
        try:
            full_response = json.loads(response_str.strip())
            if isinstance(full_response, dict) and 'id' in full_response:
                if full_response['id'] == request_id:
                    return full_response, elapsed_time
        except json.JSONDecodeError:
            pass
        
        # If we still haven't found a match, return the first valid message
        for msg in messages:
            if not msg.strip():
                continue
            try:
                parsed = json.loads(msg)
                if isinstance(parsed, dict):
                    return parsed, elapsed_time
            except json.JSONDecodeError:
                continue
        
        # Last resort: show what we got
        print(f"{YELLOW}  Warning: Could not find matching response for request ID {request_id}{RESET}")
        print(f"{GRAY}  Received {len(messages)} message(s), total length: {len(response_str)} chars{RESET}")
        print(f"{GRAY}  First 500 chars: {response_str[:500]}{RESET}")
        elapsed_time = time.time() - start_time
        return None, elapsed_time
        
    except socket.timeout:
        elapsed_time = time.time() - start_time
        print(f"{RED}  Request timeout{RESET}")
        return None, elapsed_time
    except json.JSONDecodeError as e:
        elapsed_time = time.time() - start_time
        print(f"{RED}  JSON decode error: {e}{RESET}")
        if response_data:
            response_preview = response_data.decode('utf-8', errors='ignore')[:500]
            print(f"{GRAY}  Response preview (first 500 chars): {response_preview}{RESET}")
            print(f"{GRAY}  Total response length: {len(response_data)} bytes{RESET}")
        return None, elapsed_time
    except Exception as e:
        elapsed_time = time.time() - start_time
        print(f"{RED}  Request error: {e}{RESET}")
        import traceback
        traceback.print_exc()
        return None, elapsed_time


def test_server(server: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Test an Electrum server with blockchain.transaction.get request.
    
    According to Electrum protocol, we MUST send server.version() as the first
    message to negotiate the protocol version before making any other requests.
    
    Args:
        server: Server configuration dictionary
        
    Returns:
        Dictionary with timing results or None if failed
    """
    host = server["host"]
    port = server["port"]
    name = server["name"]
    
    # Timing results
    timing_results = {
        "name": name,
        "host": f"{host}:{port}",
        "connection_time": None,
        "version_time": None,
        "transaction_time": None,
        "total_time": None,
        "success": False
    }
    
    # Start total timing
    total_start_time = time.time()
    
    print(f"\n{BOLD}{'=' * 80}{RESET}")
    print(f"{BOLD}Testing: {CYAN}{name}{RESET}")
    print(f"{BOLD}Host: {GRAY}{host}:{port}{RESET}")
    print(f"{BOLD}{'=' * 80}{RESET}")
    
    # Connect to server
    print(f"\n{YELLOW}[1/4]{RESET} Connecting to {host}:{port}...")
    connection_start = time.time()
    sock = connect_to_server(host, port)
    timing_results["connection_time"] = time.time() - connection_start
    
    if not sock:
        print(f"{RED}✗ Failed to connect to server{RESET}")
        timing_results["total_time"] = time.time() - total_start_time
        return timing_results
    
    print(f"{GREEN}✓ Connected successfully{RESET}")
    print(f"  Connection time: {GRAY}{timing_results['connection_time']:.3f}s{RESET}")
    
    # Version negotiation - MUST be the first message according to protocol
    print(f"\n{YELLOW}[2/4]{RESET} Negotiating protocol version (server.version)...")
    # Client name and supported protocol versions
    # Using a wide range of versions for compatibility
    version_response, version_time = send_request(sock, "server.version", ["ElectrumTestScript/1.0", "1.4"])
    timing_results["version_time"] = version_time
    
    if not version_response:
        print(f"{RED}✗ Failed to negotiate protocol version{RESET}")
        print(f"  Time elapsed: {GRAY}{version_time:.3f}s{RESET}")
        sock.close()
        timing_results["total_time"] = time.time() - total_start_time
        return timing_results
    
    print(f"  Response time: {GRAY}{version_time:.3f}s{RESET}")
    
    # Check for errors in version negotiation
    if "error" in version_response:
        print(f"{RED}✗ Version negotiation error:{RESET}")
        error = version_response["error"]
        print(f"  Code: {error.get('code', 'N/A')}")
        print(f"  Message: {error.get('message', 'N/A')}")
        sock.close()
        timing_results["total_time"] = time.time() - total_start_time
        return timing_results
    
    # Display negotiated version
    version_result = version_response.get("result")
    if version_result:
        if isinstance(version_result, list) and len(version_result) >= 2:
            server_version = version_result[0]
            protocol_version = version_result[1]
            print(f"{GREEN}✓ Protocol version negotiated{RESET}")
            print(f"  Server version: {GRAY}{server_version}{RESET}")
            print(f"  Protocol version: {GRAY}{protocol_version}{RESET}")
        else:
            print(f"{GREEN}✓ Version negotiation successful{RESET}")
            print(f"  Response: {GRAY}{version_result}{RESET}")
    else:
        print(f"{YELLOW}⚠ Version negotiation response has no result field{RESET}")
    
    # Send blockchain.transaction.get request
    print(f"\n{YELLOW}[3/4]{RESET} Sending blockchain.transaction.get request...")
    print(f"  Transaction hash: {GRAY}{TX_HASH}{RESET}")
    
    # Electrum blockchain.transaction.get method with verbose=True
    response, transaction_time = send_request(sock, "blockchain.transaction.get", [TX_HASH, True], request_id=2)
    timing_results["transaction_time"] = transaction_time
    
    # Close socket
    sock.close()
    
    if not response:
        print(f"{RED}✗ Failed to get response from server{RESET}")
        print(f"  Time elapsed: {GRAY}{transaction_time:.3f}s{RESET}")
        timing_results["total_time"] = time.time() - total_start_time
        return timing_results
    
    print(f"{GREEN}✓ Received response{RESET}")
    print(f"  Response time: {GRAY}{transaction_time:.3f}s{RESET}")
    
    # Display results
    print(f"\n{YELLOW}[4/4]{RESET} Response:")
    print(f"{BOLD}{'─' * 80}{RESET}")
    
    # Check for errors
    if "error" in response:
        print(f"{RED}Error in response:{RESET}")
        error = response["error"]
        print(f"  Code: {error.get('code', 'N/A')}")
        print(f"  Message: {error.get('message', 'N/A')}")
        if "data" in error:
            print(f"  Data: {error['data']}")
    else:
        # Display successful response
        result = response.get("result")
        if result:
            print(f"{GREEN}Success! Transaction data:{RESET}\n")
            # Pretty print the JSON response
            print(json.dumps(result, indent=2, ensure_ascii=False))
            timing_results["success"] = True
        else:
            print(f"{YELLOW}Warning: Response has no result field{RESET}")
            print(f"Full response: {json.dumps(response, indent=2, ensure_ascii=False)}")
    
    print(f"{BOLD}{'─' * 80}{RESET}")
    
    # Calculate total time
    timing_results["total_time"] = time.time() - total_start_time
    
    return timing_results


def main():
    """Main function."""
    print(f"\n{BOLD}{BLUE}{'=' * 80}{RESET}")
    print(f"{BOLD}{BLUE}Electrum Server Test Script{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 80}{RESET}")
    print(f"\nTesting transaction: {CYAN}{TX_HASH}{RESET}")
    print(f"Method: {GRAY}blockchain.transaction.get (verbose=True){RESET}")
    print(f"Servers to test: {len(SERVERS)}")
    
    # Store timing results for all servers
    all_timing_results = []
    
    # Test each server
    for i, server in enumerate(SERVERS, 1):
        try:
            timing_result = test_server(server)
            if timing_result:
                all_timing_results.append(timing_result)
        except KeyboardInterrupt:
            print(f"\n\n{RED}Interrupted by user{RESET}")
            sys.exit(1)
        except Exception as e:
            print(f"\n{RED}Unexpected error testing {server['name']}: {e}{RESET}")
            import traceback
            traceback.print_exc()
            # Add failed result
            all_timing_results.append({
                "name": server["name"],
                "host": f"{server['host']}:{server['port']}",
                "connection_time": None,
                "version_time": None,
                "transaction_time": None,
                "total_time": None,
                "success": False
            })
    
    # Display timing summary
    print(f"\n{BOLD}{BLUE}{'=' * 80}{RESET}")
    print(f"{BOLD}{BLUE}Timing Summary{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 80}{RESET}\n")
    
    if all_timing_results:
        # Table header
        print(f"{BOLD}{'Server':<40} {'Connection':<12} {'Version':<12} {'Transaction':<12} {'Total':<12} {'Status':<10}{RESET}")
        print(f"{BOLD}{'─' * 100}{RESET}")
        
        # Display results for each server
        for result in all_timing_results:
            name = result["name"][:38]  # Truncate if too long
            conn_time = f"{result['connection_time']:.3f}s" if result['connection_time'] is not None else "N/A"
            ver_time = f"{result['version_time']:.3f}s" if result['version_time'] is not None else "N/A"
            tx_time = f"{result['transaction_time']:.3f}s" if result['transaction_time'] is not None else "N/A"
            total_time = f"{result['total_time']:.3f}s" if result['total_time'] is not None else "N/A"
            status = f"{GREEN}✓ Success{RESET}" if result['success'] else f"{RED}✗ Failed{RESET}"
            
            print(f"{name:<40} {conn_time:<12} {ver_time:<12} {tx_time:<12} {total_time:<12} {status}")
        
        print(f"{BOLD}{'─' * 100}{RESET}\n")
        
        # Find fastest server
        successful_results = [r for r in all_timing_results if r['success'] and r['total_time'] is not None]
        if successful_results:
            fastest = min(successful_results, key=lambda x: x['total_time'])
            print(f"{BOLD}Fastest server: {GREEN}{fastest['name']}{RESET} (Total: {fastest['total_time']:.3f}s)")
            
            # Compare transaction times
            if len(successful_results) > 1:
                tx_times = [(r['name'], r['transaction_time']) for r in successful_results if r['transaction_time'] is not None]
                if tx_times:
                    fastest_tx = min(tx_times, key=lambda x: x[1])
                    print(f"{BOLD}Fastest transaction response: {GREEN}{fastest_tx[0]}{RESET} ({fastest_tx[1]:.3f}s)")
    
    print(f"\n{BOLD}{BLUE}{'=' * 80}{RESET}")
    print(f"{BOLD}{GREEN}Testing completed{RESET}")
    print(f"{BOLD}{BLUE}{'=' * 80}{RESET}\n")


if __name__ == '__main__':
    main()

