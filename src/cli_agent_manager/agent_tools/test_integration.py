"""Integration test for HTTP-based agent communication.

This module provides a simple test to verify that the HTTP client
can communicate with the FastAPI server endpoints.
"""

import asyncio
import os
from typing import Dict, Any

from cli_agent_manager.clients.agent_communication import (
    assign,
    handoff,
    send_message,
)


async def test_agent_communication():
    """Test the HTTP-based agent communication tools."""
    print("Testing HTTP-based agent communication...")
    
    # Check if TRON_TERMINAL_ID is set (required for send_message)
    terminal_id = os.getenv("TRON_TERMINAL_ID")
    if not terminal_id:
        print("Warning: TRON_TERMINAL_ID not set. Some tests may fail.")
    
    try:
        # Test assign (should create terminal and return immediately)
        print("\n1. Testing assign...")
        assign_result = await assign(
            agent_profile="test_agent",
            message="Test assignment message"
        )
        print(f"Assign result: {assign_result}")
        
        # Test handoff (should create terminal and wait for completion)
        print("\n2. Testing handoff...")
        handoff_result = await handoff(
            agent_profile="test_agent",
            message="Test handoff message",
            timeout=30  # Short timeout for testing
        )
        print(f"Handoff result: {handoff_result}")
        
        # Test send_message (requires TRON_TERMINAL_ID)
        if terminal_id:
            print("\n3. Testing send_message...")
            message_result = await send_message(
                receiver_id="test12345",  # This will likely fail but tests the interface
                message="Test message"
            )
            print(f"Send message result: {message_result}")
        else:
            print("\n3. Skipping send_message test (TRON_TERMINAL_ID not set)")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        raise


async def main():
    """Main test function."""
    await test_agent_communication()


if __name__ == "__main__":
    asyncio.run(main())