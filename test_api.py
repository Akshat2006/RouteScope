"""
RouteScope — Quick API smoke test
Run after starting the backend: python test_api.py
"""
import urllib.request, json, sys

BASE = "http://localhost:8000"

def get(path):
    r = urllib.request.urlopen(BASE + path)
    return json.loads(r.read())

def post(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data,
        headers={"Content-Type": "application/json"}
    )
    r = urllib.request.urlopen(req)
    return json.loads(r.read())

# Health
h = get("/health")
print("HEALTH:", h)

# Graph
g = get("/api/graph")
nodes = g["graph"]["nodes"]
edges = g["graph"]["edges"]
print(f"GRAPH: {len(nodes)} nodes, {len(edges)} edges")
print("Health metrics:", g["health"])
print("Storage:", f"Tier {g.get('storage_tier', '?')} ({g.get('storage_backend', '?')})")

# Algorithms list
a = get("/api/algorithms")
names = [x["name"] for x in a["algorithms"]]
print(f"\nALGORITHMS ({a['count']}):", names)

# Compute between first two nodes if available
if len(nodes) >= 2:
    src = nodes[0]["id"]
    dst = nodes[-1]["id"]
    src_label = nodes[0].get("label", src)
    dst_label = nodes[-1].get("label", dst)
    try:
        c = post("/api/compute", {"source": src, "destination": dst})
        print(f"\nCOMPUTE {src_label} -> {dst_label}:")
        print(f"  {c['algorithm_count']} algorithms | total={c['total_runtime_ms']:.1f}ms | survivability={c['survivability_score']:.3f}")
        for res in c["results"]:
            status = "OK" if res["reachable"] else "UNREACHABLE"
            path_labels = " -> ".join(res["path"]) if res["path"] else "---"
            print(f"  [{status}] {res['algorithm']:12s} cost={res['cost']:.2f} hops={res['hop_count']} rt={res['runtime_ms']:.2f}ms")
            print(f"          path: {path_labels}")
    except Exception as e:
        print(f"Compute failed: {e}")
else:
    print("\nNot enough nodes to run compute test")
