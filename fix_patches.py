#!/usr/bin/env python3
"""Fix patch paths in test files."""
import re

with open('src/tools/test_agent_tools.py', 'r') as f:
    content = f.read()

# Fix agent_tools patches
content = re.sub(r'@mock\.patch\("agent_tools\.', '@mock.patch("tools.agent_tools.', content)
content = re.sub(r"@mock\.patch\('agent_tools\.", "@mock.patch('tools.agent_tools.", content)

# Fix code_runner patches  
content = re.sub(r'@mock\.patch\("code_runner\.', '@mock.patch("tools.code_runner.', content)
content = re.sub(r"@mock\.patch\('code_runner\.", "@mock.patch('tools.code_runner.", content)

with open('src/tools/test_agent_tools.py', 'w') as f:
    f.write(content)

print('Fixed patch paths successfully')
