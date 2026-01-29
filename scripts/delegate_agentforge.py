#!/usr/bin/env python3
"""
AgentForge Delegation Script - Enhanced
Supports build, test, custom integration tasks, and Context Memory operations.
"""
import sys
import os
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

# Ensure antigravity_integration is available
sys.path.insert(0, '/home/user/projects/antigravity_integration')

try:
    from client import AgentForgeClient
    from core_extension import get_extension
except ImportError:
    # Fallback if integration library is missing or path is wrong
    AgentForgeClient = None
    get_extension = None

BRAIN_CONTEXT_DIR = Path("/home/user/projects/.brain/context")

def delegate_integration(task_file):
    """Delegate custom integration task to AgentForge"""
    if not AgentForgeClient:
        print("❌ AgentForge client library not found.")
        return 1
        
    client = AgentForgeClient()
    
    # Read task specification
    try:
        with open(task_file, 'r') as f:
            task_spec = f.read()
    except FileNotFoundError:
        print(f"❌ Task file not found: {task_file}")
        return 1
    
    print(f"🤖 Delegating integration task: {task_file}")
    
    # Send integration command
    prompt = f"""Complete the following integration task for OrcaSlicer belt printer:

{task_spec}

Instructions:
1. Read and understand the task specification
2. Make the code changes as specified
3. Build the project: cd /home/user/projects/ORCA_BELT/build && ninja -j4 orca-slicer
4. Run basic smoke test if build succeeds
5. Report results with exit codes
"""
    
    response = client.send_command(
        action="chat_completion",
        data={
            "prompt": prompt,
            "max_tokens": 4000
        },
        target_agent="assistant"
    )
    
    if response["status"] != "success":
        print(f"❌ Failed to send task: {response['message']}")
        return 1
    
    print("✅ Task sent. Monitoring progress...")
    
    # Monitor for completion
    start = time.time()
    while time.time() - start < 600:  # 10 min timeout
        messages = client.poll_responses(target_agent="chatgpt", limit=5)
        if messages:
            for msg in messages:
                content = msg.get("content", {})
                if isinstance(content, str):
                    print(f"\n📨 Response: {content[:200]}...")
                    if "build success" in content.lower() or "✅" in content:
                        print("\n✅ INTEGRATION COMPLETE!")
                        return 0
                    elif "error" in content.lower() or "❌" in content:
                        print("\n⚠️ Integration encountered issues")
                        return 1
        time.sleep(5)
    
    return 2

def delegate_build():
    """Delegate build task to AgentForge executor"""
    if not AgentForgeClient:
        print("❌ AgentForge client library not found.")
        return 1

    client = AgentForgeClient()
    print("🤖 Delegating ORCA_BELT build to AgentForge...")
    
    response = client.send_command(
        action="shell_exec",
        data={
            "command": "cd /home/user/projects/ORCA_BELT && ./build_linux.sh 2>&1",
            "timeout": 600,
            "working_dir": "/home/user/projects/ORCA_BELT"
        },
        target_agent="executor"
    )
    
    if response["status"] != "success":
        print(f"❌ Failed to send build command: {response['message']}")
        return 1
        
    print("✅ Build command sent.")
    return 0

def delegate_tests():
    """Delegate test execution to AgentForge"""
    if not AgentForgeClient:
        print("❌ AgentForge client library not found.")
        return 1

    client = AgentForgeClient()
    print("🧪 Delegating belt printer tests to AgentForge...")
    
    response = client.send_command(
        action="shell_exec",
        data={
            "command": "cd /home/user/projects/ORCA_BELT/build && ctest --output-on-failure -R belt_printer",
            "timeout": 180
        },
        target_agent="executor"
    )
    
    if response["status"] != "success":
        print(f"❌ Failed to send test command: {response['message']}")
        return 1
        
    print("✅ Test command sent.")
    return 0

def memorize(content, tag="MEMORY"):
    """
    Save content to Hippocampal context (brain/context).
    This allows the Agent to 'remember' this event in future sessions.
    """
    if not BRAIN_CONTEXT_DIR.exists():
        try:
            BRAIN_CONTEXT_DIR.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"❌ Failed to create context directory: {e}")
            return 1
            
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}_{tag}.md"
    file_path = BRAIN_CONTEXT_DIR / filename
    
    try:
        with open(file_path, 'w') as f:
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Tag: {tag}\n")
            f.write("-" * 20 + "\n")
            f.write(content + "\n")
        print(f"🧠 Memorized to: {filename}")
        return 0
    except Exception as e:
        print(f"❌ Failed to memorize: {e}")
        return 1

def recall(limit=5):
    """
    Recall recent memories from Hippocampal context.
    """
    if not BRAIN_CONTEXT_DIR.exists():
        print("🧠 No memories found (directory missing).")
        return 0
        
    files = sorted(BRAIN_CONTEXT_DIR.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    print(f"\n🧠 Recalling last {limit} memories:")
    print("=" * 40)
    
    count = 0
    for p in files:
        if count >= limit:
            break
        print(f"\n📄 {p.name}")
        try:
            content = p.read_text().strip()
            # Preview first few lines
            preview = "\n".join(content.splitlines()[:10])
            print(preview)
            if len(content.splitlines()) > 10:
                print("... [truncated]")
        except Exception as e:
            print(f"   [Error reading file: {e}]")
        print("-" * 40)
        count += 1
        
    return 0

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Delegate OrcaSlicer tasks to AgentForge & Manage Memory")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Build command
    subparsers.add_parser("build", help="Delegate build task")
    
    # Test command
    subparsers.add_parser("test", help="Delegate test task")
    
    # Memorize command
    mem_parser = subparsers.add_parser("memorize", help="Save text to context memory")
    mem_parser.add_argument("content", help="Content to memorize")
    mem_parser.add_argument("--tag", default="NOTE", help="Tag for the memory file")
    
    # Recall command
    recall_parser = subparsers.add_parser("recall", help="Read recent context memories")
    recall_parser.add_argument("-n", "--number", type=int, default=5, help="Number of memories to recall")
    
    # Integration command (legacy argument style, handled as fallback or explicit subcommand)
    int_parser = subparsers.add_parser("integrate", help="Delegate custom integration task")
    int_parser.add_argument("spec_file", help="Path to task specification file")

    args = parser.parse_args()
    
    # Fallback for old positional argument usage: python delegate_agentforge.py <task_file>
    if args.command is None:
        if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
            sys.exit(delegate_integration(sys.argv[1]))
        else:
            parser.print_help()
            sys.exit(1)

    if args.command == "build":
        sys.exit(delegate_build())
    elif args.command == "test":
        sys.exit(delegate_tests())
    elif args.command == "memorize":
        sys.exit(memorize(args.content, args.tag))
    elif args.command == "recall":
        sys.exit(recall(args.number))
    elif args.command == "integrate":
        sys.exit(delegate_integration(args.spec_file))
