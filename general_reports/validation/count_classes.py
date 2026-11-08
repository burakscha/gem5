"""Events and reloads per class from a schema-8 verbose log (STACK lines)."""
import collections, sys
events, reloads, seen = collections.Counter(), collections.Counter(), set()
for line in open(sys.argv[1]):
    if line.startswith("STACK,"):
        f = line.rstrip().split(",")
        cls, store_pc, store_inst = f[1], f[2], f[8]
        reloads[cls] += 1
        if (store_pc, store_inst) not in seen:
            seen.add((store_pc, store_inst))
            events[cls] += 1
total = sum(events.values())
for cls in ("spill", "csave", "other_stack"):
    print(f"  {cls:12s} events {events[cls]:9,d} ({100*events[cls]/max(1,total):5.1f}%)   reloads {reloads[cls]:9,d}")
print(f"  {'stack':12s} events {total:9,d}            reloads {sum(reloads.values()):9,d}")
