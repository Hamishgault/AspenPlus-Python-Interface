import ast
from pathlib import Path
p = Path(__file__).resolve().parents[1] / 'Project' / 'Aspen' / 'batch_runner.py'
s = p.read_text()
try:
    ast.parse(s)
    print('ast parse OK')
except Exception as e:
    import traceback
    traceback.print_exc()