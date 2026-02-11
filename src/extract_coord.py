# Extract coordinator sections
with open('main.py', 'r') as f:
    lines = f.readlines()

# Extract coordinator_init (lines 711-766)
with open('main/coordinator/coordinator_init.txt', 'w') as f:
    f.write(''.join(lines[710:766]))

# Extract agent_factory methods (lines 766-904, 904-958)
with open('main/coordinator/factory_methods.txt', 'w') as f:
    f.write(''.join(lines[765:958]))

# Extract decomposer methods (lines 958-1137)
with open('main/coordinator/decomposer_methods.txt', 'w') as f:
    f.write(''.join(lines[957:1137]))

# Extract orchestrator/execution (lines 1137-1515)
with open('main/coordinator/orchestrator_methods.txt', 'w') as f:
    f.write(''.join(lines[1136:1515]))

print("Extracted sections")
