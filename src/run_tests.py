"""Execute the unit suite and retain structured outcomes and resource use."""
import json
import os
from pathlib import Path
import resource
import time
import unittest


def main():
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU, (35, 35))
    resource.setrlimit(resource.RLIMIT_AS, (3*1024**3, 3*1024**3))
    started=time.perf_counter()
    suite=unittest.defaultTestLoader.discover('tests')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    ru=resource.getrusage(resource.RUSAGE_SELF)
    data={'tests_run':result.testsRun,'failures':len(result.failures),
          'errors':len(result.errors),'skips':len(result.skipped),
          'wall_seconds':time.perf_counter()-started,
          'process_cpu_seconds':ru.ru_utime+ru.ru_stime,'peak_rss_kib':ru.ru_maxrss,
          'workers':1,'cpu_cap_seconds':35,'address_space_cap_bytes':3*1024**3,
          'successful':result.wasSuccessful()}
    Path('results').mkdir(exist_ok=True)
    Path('results/unit-tests.json').write_text(json.dumps(data,indent=2)+'\n')
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
