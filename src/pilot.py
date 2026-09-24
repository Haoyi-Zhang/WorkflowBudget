"""Bounded, exact-oracle pilot. Run from the repository root."""
import json
import os
from pathlib import Path
import resource
import time
from examples import curated
from producer import compare, static_width
from checker import check
from oracle import decide, canonical
from negative_controls import chronological, forget_everything, independent_worlds, terminal_only



if not __debug__:
    raise SystemExit("claim-critical validation refuses optimized Python; rerun without -O or PYTHONOPTIMIZE")

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_CPU,(35,35))
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    start_wall = time.perf_counter()
    start_cpu = time.process_time()
    out = []
    for name,description,pair,want_eq,want_budget in curated():
        cert,info = compare(pair)
        truth = decide(pair)
        accepted = check(pair,cert)
        assert info["equivalent"] == truth["equivalent"] == want_eq
        assert info["budget"] == truth["budget"] == want_budget
        assert (canonical(pair["left"]) == canonical(pair["right"])) == want_eq
        assert info["max_retained_keys"] <= static_width(pair)
        Path("inputs").mkdir(exist_ok=True)
        Path("certificates").mkdir(exist_ok=True)
        Path(f"inputs/{name}.json").write_text(json.dumps(pair,indent=2)+"\n")
        Path(f"certificates/{name}.json").write_text(json.dumps(cert,indent=2)+"\n")
        out.append({"case":name,"description":description,**info,
                    "oracle_worlds":truth["worlds"],"certificate_accepted":accepted["accepted"],
                    "static_frontier_width":static_width(pair)})
    examples = {row[0]:row[2] for row in curated()}
    neg = {
        "chronological_false_rejection":chronological(examples["case-01"]),
        "premature_forgetting_false_rejection":forget_everything(examples["case-02"]),
        "independent_worlds_false_rejection":independent_worlds(examples["case-03"]),
        "terminal_only_false_acceptance":terminal_only(examples["case-04"])}
    assert neg == {"chronological_false_rejection":3,
                   "premature_forgetting_false_rejection":3,
                   "independent_worlds_false_rejection":2,
                   "terminal_only_false_acceptance":True}
    data = {"cases":out,"negative_controls":neg,
            "resources":{"wall_seconds":time.perf_counter()-start_wall,
                         "cpu_seconds":time.process_time()-start_cpu,
                         "process_cpu_seconds":sum(resource.getrusage(resource.RUSAGE_SELF)[:2]),
                         "peak_rss_kib":resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                         "workers":1,"address_space_cap_bytes":3*1024**3,
                         "cpu_limit_seconds":35}}
    Path("results").mkdir(exist_ok=True)
    Path("results/pilot.json").write_text(json.dumps(data,indent=2)+"\n")
    print(json.dumps(data,indent=2))

if __name__ == "__main__": main()
