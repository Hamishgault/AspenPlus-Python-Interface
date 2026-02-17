import importlib
try:
    m = importlib.import_module('batch_runner')
    print('imported batch_runner from', getattr(m, '__file__', 'unknown'))
except Exception as e:
    import traceback
    traceback.print_exc()
    raise
