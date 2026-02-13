"""Quick debug script to trace what the real LLM returns."""
import tempfile, os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from httpx._client import AsyncClient as RealAsyncClient
import httpx
from comms.channel import ChannelFactory, APIChannel
from comms.resilience import ConnectionPool
from fileio import FileSystem
from main import Agent

config = {
    'role': 'developer',
    'system_prompt': 'You are a developer',
    'model': 'qwen/qwen3-coder-30b',
    'temperature': 0.7,
    'max_tokens': 1000,
    'allowed_tools': ['read_file', 'write_file', 'append_file', 'list_directory', 'confirm_task_complete'],
    'model_endpoints': [{'model': 'qwen/qwen3-coder-30b', 'endpoint': 'http://localhost:12345/v1/chat/completions'}]
}

with tempfile.TemporaryDirectory() as tmpdir:
    test_file = os.path.join(tmpdir, 'test.md')
    with open(test_file, 'w') as f:
        f.write('# Original\n\nThis is sample content')

    pool = ConnectionPool(timeout_seconds=120.0)
    pool.client = RealAsyncClient(
        limits=httpx.Limits(max_connections=100, max_keepalive_connections=50),
        timeout=httpx.Timeout(120.0),
    )
    pool._initialized = True
    channel_factory = ChannelFactory(replay_mode=False, connection_pool=pool)
    filesystem = FileSystem(shared_dir=tmpdir)
    agent = Agent(config, channel_factory, filesystem, instance_number=1)

    print(f"Channel type: {type(agent.channel).__name__}")

    result = agent.execute_with_agentic_loop(
        {'user_prompt': (
            "Read the file 'test.md' in the working directory, then overwrite it "
            "with the heading '# Updated' followed by a blank line and "
            "'Content updated by agent'. After writing, call confirm_task_complete()."
        )},
        working_dir=tmpdir,
        max_iterations=10,
    )

    print(f"\n=== RESULT ===")
    print(f"task_complete: {result['task_complete']}")
    print(f"iteration_count: {result['iteration_count']}")
    print(f"final_response (last 800 chars):\n{result['final_response'][-800:]}")
    print()
    for i, tr in enumerate(result.get('tool_results', [])):
        print(f"--- Iteration {i+1} tool results ---")
        print(f"  tools_executed: {tr.get('tools_executed')}")
        print(f"  task_complete: {tr.get('task_complete')}")
        print(f"  code_blocks_found: {tr.get('code_blocks_found')}")
        print(f"  code_blocks_executed: {tr.get('code_blocks_executed')}")
        outputs = tr.get('tool_outputs', [])
        for o in outputs:
            t = o.get('tool', '?')
            kw = o.get('kwargs', {})
            print(f"  tool: {t} | kwargs: {kw}")
    print()
    with open(test_file, 'r') as f:
        print(f"Final file content:\n{f.read()}")
