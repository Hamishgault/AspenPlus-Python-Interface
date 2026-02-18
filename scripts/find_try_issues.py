import ast
from pathlib import Path
p = Path(__file__).resolve().parents[1] / 'Project' / 'Aspen' / 'batch_runner.py'
s = p.read_text()
mod = ast.parse(s)
problems = []
for node in ast.walk(mod):
    if isinstance(node, ast.Try):
        handlers = len(node.handlers)
        final = len(node.finalbody)
        if handlers == 0 and final == 0:
            problems.append((node.lineno, node.col_offset))
if not problems:
    print('No try-without-except/finally found')
else:
    print('Problematic try nodes at:', problems)
