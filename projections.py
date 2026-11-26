#!/usr/bin/env python3
"""Storage, throughput and cost projections for scaling the nanopublication network.

Run:  python3 projections.py            (prints the tables used in scaling-nanopublications.md)

Every input is a named constant below, tagged as
  [M] measured on the current network or taken from a cited source, or
  [A] an assumption to be replaced by a measurement.
Change a constant, re-run, and the tables follow.
"""

# --------------------------------------------------------------------------------------
# Inputs
# --------------------------------------------------------------------------------------

KB, MB, GB, TB, PB = 1e3, 1e6, 1e9, 1e12, 1e15
MONTH_S = 30.4 * 86400

# --- network today ---------------------------------------------------------------------
N_TODAY = 108_975            # [M] nanopubCount on all three registries, 2026-11-25

# --- size of one nanopublication, by profile -------------------------------------------
# "mix"  = today's live network (templates, queries, views, FIP declarations, ...; RSA-2048)
# "lean" = a bulk dataset record: one small assertion, Ed25519 signature
PROFILES = {
    "mix": dict(
        quads=39.5,          # [M] 4,045,752 content quads / 102,500 nanopubs (snapshot 2026-11-03)
        jelly=2460,          # [M] 252 MB Jelly stream / 102,500
        archive=600,         # [M] 552 B (zstd -19) to 733 B (gzip -9) on the newest 8,975 nanopubs
        index=800,           # [A] rete content quads + list metadata, no blobs (see section 4.2)
        with_blobs=3840,     # [M] 394 MB registry.rete (content + metadata + TriG and Jelly blobs) / 102,500
    ),
    "lean": dict(
        quads=20,            # [A]
        jelly=1000,          # [A]
        archive=300,         # [A] ~65 B of signature entropy instead of ~260 B, less content
        index=400,           # [A] first-generation dump: 233 B per unsigned nanopub of 35 quads [M]
        with_blobs=1600,     # [A]
    ),
}

# --- today's live stack ----------------------------------------------------------------
RDF4J_BYTES_AT_88K = 12 * GB     # [M] nanopub-query doc/operations.md
RDF4J_REPOS = 2800               # [M]
RDF4J_BYTES_PER_QUAD = 125       # [M] RDF4J LMDB store documentation: 120 to 130 bytes per quad with 3 indexes
RDF4J_COPIES = 3.4               # [M] full + key repository + 1.4 type repositories (2.4 list entries per nanopub)
RDF4J_ADMIN_QUADS = 12           # [A] admin-graph triples added per nanopub and repository
RDF4J_MARGINAL = RDF4J_COPIES * (39.5 + RDF4J_ADMIN_QUADS) * RDF4J_BYTES_PER_QUAD   # about 22 KB
QUERY_LOAD_RATE = 12             # [M] nanopubs/s, initial load (87k in about 2 h)
QUERY_LOAD_TARGET = 300          # [A] nanopubs/s after the load path is batched (section 5.1)
REGISTRY_SYNC_RATE = 50          # [M] nanopubs/s, peer sync (89k in about 30 min)
REGISTRY_POST_RATE = 15.5        # [M] nanopubs/s, serialised POST path
MONGO_BYTES_PER_NP = 10 * KB     # [A] not measured; TriG + Jelly + list entries + indexes

# --- static path -----------------------------------------------------------------------
VERIFY_RATE = 295                # [M] nanopubs/s per thread: readonly.Build, 102,500 in 5m48s
RETE_BUILD_RATE = 222_000        # [M] quads/s: rete 0.7.0 changelog, 378.7 M quads in 1,708 s at 4 GB
RETE_STREAM_RATE = 3_900         # [M] nanopubs/s served as one Jelly stream (102,500 in 26 s)

# --- prices per month, excluding VAT, list prices read on 2026-11-25 (section 7.1) ------
PRICE_OBJECT_TB = 6.5            # [M] Hetzner Object Storage, EUR 6.47 per TB-month; B2 is USD 6.95
PRICE_HDD_TB = 2.0               # [M] usable TB on a rented storage server: SX65 1.27, SX135 2.19 (RAID 5 / 6)
PRICE_NVME_TB = 22.0             # [M] datacentre NVMe as a server add-on: EUR 170 for 7.68 TB, 320 for 15.36 TB
PRICE_NODE_SMALL = 59            # [M] Hetzner AX41: 6 cores, 64 GB, 2 x 512 GB NVMe (today's class)
PRICE_NODE_BIG = 259             # [M] Hetzner AX102: 16 cores, 128 GB, 2 x 1.92 TB NVMe
PRICE_NODE_HUGE = 614            # [M] Hetzner AX162 base: 48 cores, 128 GB
PRICE_HYPERSCALER_TB = 23.0      # [M] AWS S3 Standard, USD 23 to 24.50 per TB-month, taken at par, before egress
QLEVER_BYTES_PER_TRIPLE = 11.3   # [M] UniProt on QLever: about 3 TB for 265.9 billion triples
QLEVER_BUILD_FACTOR = 2.3        # [M] about 7 TB needed during that build
QLEVER_RATE = 1.66e6             # [M] triples/s: 239.7 billion in about 40 h

# --- signatures, operations per second and core ----------------------------------------
RSA_SIGN, RSA_VERIFY = 2_100, 89_000        # [M] eBACS, Zen 4 at 3.8 GHz
ED_SIGN, ED_VERIFY = 34_000, 10_000         # [M] OpenSSL 4.0 on Zen 4 (lib25519: 119,000 and 31,000)

REPLICAS = 3                     # independent full copies of the static plane

# --- dynamic part, distributed over nodes by key and type coverage ----------------------
DYN_QUADS = 39.5 + RDF4J_ADMIN_QUADS       # quads per loaded nanopublication and copy
TYPES_PER_NP = 1.4               # [M] 142,807 typed list entries / 102,500 nanopublications
NODE_QUADS_RDF4J = 2e9           # [A] quads one RDF4J/LMDB node carries; today's nodes hold 0.02e9, others report 1e9
NODE_QUADS_LARGE = 20e9          # [M] a Wikidata-size store on one machine (QLever, Virtuoso)
DYN_LAYOUTS = [
    # label, copies per nanopublication on a node, quads per node, node price
    ("Today's layout: `full`, key and type repositories, RDF4J", RDF4J_COPIES, NODE_QUADS_RDF4J, PRICE_NODE_BIG),
    ("Type shards, one copy per type, RDF4J", TYPES_PER_NP, NODE_QUADS_RDF4J, PRICE_NODE_BIG),
    ("Type shards, one copy per type, engine at Wikidata scale", TYPES_PER_NP, NODE_QUADS_LARGE, PRICE_NODE_HUGE),
]

# --- pay as you go: unit costs and operator examples ------------------------------------
REGISTRY_NODE_NP = 1e7           # [A] hot-window target per live registry node (section 5.1), on a small node
REGISTRY_NODE_FULL = 1.92 * TB / MONGO_BYTES_PER_NP   # [A] an AX102 filled to its mirrored NVMe, about 190 million; not tested
TRUST_PER_ACCOUNT = 3.1          # [M] 2,849 introductions and endorsements for 919 accounts
TRUST_NP = 1e6 * TRUST_PER_ACCOUNT   # trust cluster at a million accounts
CORE_NP = 1e7                    # [A] core cluster: templates, queries, views, spaces, retractions

SCENARIOS = [N_TODAY, 1e7, 1e8, 3e8, 1e9, 3e9, 1e10, 3e10, 1e11]

# Trajectory used in section 8 (end of quarter)
TRAJECTORY = [
    ("2026-Q4", 1.1e5), ("2027-Q1", 1e7), ("2027-Q2", 3e7), ("2027-Q3", 1e8), ("2027-Q4", 3e8),
    ("2028-Q2", 1e9), ("2028-Q4", 3e9), ("2029-Q2", 1e10), ("2029-Q4", 3e10),
]


# --------------------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------------------

def num(n):
    for unit, div in (("trillion", 1e12), ("billion", 1e9), ("million", 1e6), ("thousand", 1e3)):
        if n >= div:
            v = n / div
            return f"{v:.0f} {unit}" if v >= 10 or v == int(v) else f"{v:.1f} {unit}"
    return f"{n:.0f}"


def size(b):
    for unit, div in (("PB", PB), ("TB", TB), ("GB", GB), ("MB", MB)):
        if b >= div:
            v = b / div
            return f"{v:.0f} {unit}" if v >= 10 else f"{v:.1f} {unit}"
    return f"{b / KB:.0f} KB"


def dur(s):
    if s < 3600:
        return f"{s / 60:.0f} min"
    if s < 2 * 86400:
        return f"{s / 3600:.0f} h"
    if s < 730 * 86400:
        return f"{s / 86400:.0f} days"
    return f"{s / 86400 / 365:.0f} years"


def eur(x):
    if x >= 1e6:
        return f"€{x / 1e6:.1f}M"
    if x >= 10_000:
        return f"€{x / 1e3:.0f}k"
    if x >= 1000:
        return f"€{x / 1e3:.1f}k"
    if x >= 10:
        return f"€{x:.0f}"
    return f"€{x:.2f}"


def table(header, rows):
    print("| " + " | ".join(header) + " |")
    print("|" + "|".join("---" if i == 0 else "---:" for i in range(len(header))) + "|")
    for r in rows:
        print("| " + " | ".join(str(c) for c in r) + " |")
    print()


# --------------------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------------------

def t_quads():
    print("### T1. Statements\n")
    table(["Nanopublications", "Quads (mix, 39.5)", "Quads (lean, 20)"],
          [[num(n), num(n * PROFILES["mix"]["quads"]), num(n * PROFILES["lean"]["quads"])] for n in SCENARIOS])


def t_storage():
    print("### T2. Storage of one full replica of the static plane\n")
    rows = []
    for n in SCENARIOS:
        lean = n * (PROFILES["lean"]["archive"] + PROFILES["lean"]["index"])
        mix = n * (PROFILES["mix"]["archive"] + PROFILES["mix"]["index"])
        blobs = n * PROFILES["mix"]["with_blobs"]
        rows.append([num(n), size(n * PROFILES["mix"]["jelly"]), size(lean), size(mix), size(blobs)])
    table(["Nanopublications", "Raw Jelly", "Low (lean)", "Central (mix)", "High (mix, blobs in file)"], rows)


def t_status_quo():
    print("### T3. Today's live stack, extrapolated unchanged\n")
    rows = []
    for n in SCENARIOS:
        rows.append([
            num(n),
            size(n * MONGO_BYTES_PER_NP),
            size(max(RDF4J_BYTES_AT_88K, n * RDF4J_MARGINAL)),
            dur(n / REGISTRY_POST_RATE),
            dur(n / REGISTRY_SYNC_RATE),
            dur(n / QUERY_LOAD_RATE),
        ])
    table(["Nanopublications", "MongoDB per registry", "RDF4J per query node",
           "Publish by POST", "New registry syncs", "New query node loads"], rows)


def t_build():
    print("### T4. Building and moving static segments\n")
    rows = []
    for n in SCENARIOS[1:]:
        q = n * PROFILES["mix"]["quads"]
        b = n * (PROFILES["mix"]["archive"] + PROFILES["mix"]["index"])
        rows.append([
            num(n),
            dur(n / (VERIFY_RATE * 32)),
            dur(q / (RETE_BUILD_RATE * 8)),
            dur(b / 110e6),
            dur(b / 1.1e9),
            dur(n / RETE_STREAM_RATE),
        ])
    table(["Nanopublications", "Verify (32 threads)", "rete build (8 parallel)",
           "Copy a replica at 1 Gbit/s", "at 10 Gbit/s", "Per-nanopub stream, one connection"], rows)


def t_rate():
    print("### T5. Required average ingest rate along the trajectory\n")
    rows = []
    quarters = {"Q1": 0.25, "Q2": 0.5, "Q3": 0.75, "Q4": 1.0}
    prev_t, prev_n = None, None
    for label, n in TRAJECTORY:
        t = int(label[:4]) + quarters[label[-2:]]
        if prev_t is None:
            rows.append([label, num(n), "", ""])
        else:
            secs = (t - prev_t) * 365 * 86400
            rate = (n - prev_n) / secs
            rows.append([label, num(n), f"{rate:,.0f}", f"{rate * 86400 / 1e6:.1f} million"])
        prev_t, prev_n = t, n
    table(["End of", "Nanopublications", "Average nanopubs/s", "Per day"], rows)


MEDIA = ("nvme", "hdd", "object")   # replica 1 serves from NVMe, replica 2 is an HDD mirror, replica 3 is on object storage


def media_price(medium):
    return {"nvme": PRICE_NVME_TB, "hdd": PRICE_HDD_TB, "object": PRICE_OBJECT_TB}[medium]


def infra_cost(n, per_np, replicas=REPLICAS, media=MEDIA):
    """Monthly cost in EUR: (stored TB, static storage, global indexes, live plane and front ends)."""
    tb = n * per_np / TB
    storage = sum(tb * media_price(media[i % len(media)]) for i in range(replicas))
    # global indexes on NVMe, two copies: identifier resolver (12 B) + metadata index (60 B)
    indexes = n * (12 + 60) / TB * 2 * PRICE_NVME_TB
    # live plane: four hosts of today's class; from one billion on, three large nodes for the hot
    # window, sealing and query front ends; from ten billion on, six
    live = 4 * PRICE_NODE_SMALL
    if n >= 1e9:
        live += 3 * PRICE_NODE_BIG
    if n >= 1e10:
        live += 3 * PRICE_NODE_BIG
    return tb * replicas, storage, indexes, live


def qlever_snapshot(n, quads=PROFILES["mix"]["quads"]):
    """One analytical index over everything, rebuilt periodically: (NVMe TB incl. build space, EUR/month, build s)."""
    triples = n * quads
    tb = triples * QLEVER_BYTES_PER_TRIPLE * QLEVER_BUILD_FACTOR / TB
    return tb, tb * PRICE_NVME_TB + PRICE_NODE_HUGE, triples / QLEVER_RATE


def per_million(total_month, n):
    v = total_month * 12 / n * 1e6
    return f"€{v:,.0f}" if v >= 10 else f"€{v:.2f}"


def t_cost():
    print("### T6. Monthly infrastructure cost\n")
    per_np = PROFILES["mix"]["archive"] + PROFILES["mix"]["index"]
    rows = []
    for n in SCENARIOS:
        stored, storage, indexes, live = infra_cost(n, per_np)
        total = storage + indexes + live
        rows.append([num(n), size(stored * TB), eur(storage), eur(indexes), eur(live), eur(total),
                     per_million(total, n)])
    table(["Nanopublications", "Stored, 3 replicas", "Static storage", "Global indexes",
           "Live plane and front ends", "Total per month", "Per million per year"], rows)


def t_sensitivity():
    print("### T7. Sensitivity of the monthly total at 30 billion\n")
    n = 3e10
    central = PROFILES["mix"]["archive"] + PROFILES["mix"]["index"]
    lean = PROFILES["lean"]["archive"] + PROFILES["lean"]["index"]
    cases = [
        ("Central: today's mix, 1.4 KB, replicas on NVMe, HDD and object storage", central, 3, MEDIA),
        ("Lean records, 0.7 KB", lean, 3, MEDIA),
        ("Blobs kept in the file, 3.84 KB", PROFILES["mix"]["with_blobs"], 3, MEDIA),
        ("Merged query snapshots as well, 1.9 KB", central + 500, 3, MEDIA),
        ("Five replicas (two NVMe, two HDD, one object)", central, 5, ("nvme", "hdd", "object", "nvme", "hdd")),
        ("All three replicas on NVMe", central, 3, ("nvme",)),
        ("All three replicas on object storage", central, 3, ("object",)),
    ]
    rows = []
    for label, per_np, replicas, media in cases:
        stored, storage, indexes, live = infra_cost(n, per_np, replicas, media)
        rows.append([label, size(stored * TB), eur(storage), eur(storage + indexes + live)])
    stored, storage, indexes, live = infra_cost(n, central, 3, ("object",))
    hyper = storage / PRICE_OBJECT_TB * PRICE_HYPERSCALER_TB
    rows.append([f"All three on hyperscaler object storage at €{PRICE_HYPERSCALER_TB:.0f} per TB, before egress",
                 size(stored * TB), eur(hyper), eur(hyper + indexes + live)])
    stored, storage, indexes, live = infra_cost(n, central)
    snap_tb, snap_cost, _ = qlever_snapshot(n)
    rows.append([f"Central, plus one global SPARQL snapshot node ({snap_tb:.0f} TB NVMe)", size(stored * TB),
                 eur(storage), eur(storage + indexes + live + snap_cost)])
    table(["Case", "Stored", "Static storage per month", "Total per month"], rows)


def t_publisher():
    print("### T10. What a bulk publisher pays for storage, three replicas\n")
    rows = []
    blended = sum(media_price(m) for m in MEDIA)
    for label, per_np in (("Lean, 0.7 KB", PROFILES["lean"]["archive"] + PROFILES["lean"]["index"]),
                          ("Today's mix, 1.4 KB", PROFILES["mix"]["archive"] + PROFILES["mix"]["index"]),
                          ("Today's mix with blobs, 3.84 KB", PROFILES["mix"]["with_blobs"])):
        year_per_million = 1e6 * per_np / TB * blended * 12
        rows.append([label, f"€{year_per_million:.3f}", eur(year_per_million * 100), eur(year_per_million * 1000),
                     eur(year_per_million * 1000 * 10)])
    table(["Record profile", "1 million, per year", "100 million, per year", "1 billion, per year",
           "1 billion, ten years"], rows)


def t_global_indexes():
    print("### T8. Global indexes\n")
    rows = []
    for n in (3e8, 3e9, 3e10, 1e11):
        rows.append([num(n), size(n * 12), size(n * 9 / 8), size(n * 60), size(n * 0.03 * 40)])
    table(["Nanopublications", "Identifier resolver (sorted, 12 B)", "Same as filters (9 bit)",
           "Metadata index (60 B)", "Invalidation overlay (3%, 40 B)"], rows)


def t_signatures():
    print("### T9. Signatures\n")
    rows = []
    for n in (3e8, 3e10):
        rows.append([num(n), size(n * 256), size(n * 64),
                     dur(n / RSA_SIGN / 32), dur(n / ED_SIGN / 32),
                     dur(n / RSA_VERIFY / 32), dur(n / ED_VERIFY / 32)])
    table(["Nanopublications", "RSA-2048 signatures", "Ed25519 signatures",
           "Sign, RSA, 32 cores", "Sign, Ed25519, 32 cores",
           "Verify, RSA, 32 cores", "Verify, Ed25519, 32 cores"], rows)


def t_snapshot():
    print("### T11. One analytical SPARQL index over everything (QLever-class, extrapolated from UniProt)\n")
    rows = []
    for n in (3e8, 3e9, 3e10):
        tb, cost, secs = qlever_snapshot(n)
        rows.append([num(n), num(n * PROFILES["mix"]["quads"]), size(tb / QLEVER_BUILD_FACTOR * TB), size(tb * TB),
                     dur(secs), eur(cost)])
    table(["Nanopublications", "Quads", "Index", "NVMe incl. build space", "Build time", "Per month"], rows)


def dyn_nodes(n_dynamic, copies, node_quads, replicas=REPLICAS):
    return max(replicas, -(-int(n_dynamic * replicas * DYN_QUADS * copies) // int(node_quads)))


def t_dynamic():
    print("### T13. Nodes and monthly cost of the dynamic part, three replicas of every type\n")
    header = ["Total", "Dynamic share", "Dynamic nanopublications", "Dynamic quads"]
    for label, _, _, _ in DYN_LAYOUTS:
        header.append(label)
    rows = []
    for n in (3e8, 3e9, 3e10):
        for share in (0.01, 0.10, 0.30):
            d = n * share
            row = [num(n), f"{share:.0%}", num(d), num(d * DYN_QUADS)]
            for _, copies, node_quads, price in DYN_LAYOUTS:
                k = dyn_nodes(d, copies, node_quads)
                row.append(f"{k:,} nodes, {eur(k * price)}")
            rows.append(row)
    table(header, rows)
    # nanopublications per node, for the text below the table: node_quads / (DYN_QUADS * copies)


def t_blend():
    print("### T12. Bringing a static type into one Query instance\n")
    rows = []
    for n in (1e5, 1e6, 1e7, 1e8):
        loaded = n * RDF4J_MARGINAL
        rows.append([num(n), size(loaded), eur(loaded / TB * PRICE_NVME_TB), dur(n / QUERY_LOAD_RATE),
                     dur(n / QUERY_LOAD_TARGET)])
    table(["Nanopublications of the type", "RDF4J size", "NVMe per month", "Load time today",
           "Load time at 300 per second"], rows)


def t_clone():
    print("### T14. Bringing up one node: replaying history or copying a checkpoint\n")
    q_rdf4j = NODE_QUADS_RDF4J / DYN_QUADS
    q_large = NODE_QUADS_LARGE / DYN_QUADS
    rows_in = [
        # label, nanopublications, bytes of state, replay rate today
        ("Query node today", N_TODAY, RDF4J_BYTES_AT_88K / 88_000 * N_TODAY, QUERY_LOAD_RATE),
        ("Query node, today's layout, full", q_rdf4j / RDF4J_COPIES, NODE_QUADS_RDF4J * RDF4J_BYTES_PER_QUAD, QUERY_LOAD_RATE),
        ("Query node, type shards, RDF4J, full", q_rdf4j / TYPES_PER_NP, NODE_QUADS_RDF4J * RDF4J_BYTES_PER_QUAD, QUERY_LOAD_RATE),
        ("Query node, type shards, engine at Wikidata scale, full", q_large / TYPES_PER_NP, NODE_QUADS_LARGE * QLEVER_BYTES_PER_TRIPLE, QUERY_LOAD_RATE),
        ("Registry today", N_TODAY, N_TODAY * MONGO_BYTES_PER_NP, REGISTRY_SYNC_RATE),
        ("Registry, 10 million", 1e7, 1e7 * MONGO_BYTES_PER_NP, REGISTRY_SYNC_RATE),
        ("Registry, 100 million", 1e8, 1e8 * MONGO_BYTES_PER_NP, REGISTRY_SYNC_RATE),
    ]
    rows = []
    for label, n, b, rate in rows_in:
        rows.append([label, num(n), size(b), dur(n / rate), dur(n / QUERY_LOAD_TARGET),
                     dur(b / 110e6), dur(b / 1.1e9), dur(n / (VERIFY_RATE * 16))])
    table(["Node", "Nanopublications", "Store size", "Replay at today's rate", "Replay at 300 per second",
           "Copy at 1 Gbit/s", "at 10 Gbit/s", "Verify all signatures (16 threads)"], rows)


def clone_notes():
    """Figures quoted in section 4.11 that are not in a table."""
    d = 3e9   # a dynamic part of 10% of 30 billion
    image = d * DYN_QUADS * TYPES_PER_NP * RDF4J_BYTES_PER_QUAD
    exchange = d * (PROFILES["mix"]["archive"] + PROFILES["mix"]["index"])
    print(f"Checkpoint of {num(d)} dynamic nanopublications on object storage: "
          f"store images {size(image)}, {eur(image / TB * PRICE_OBJECT_TB)} per month; "
          f"exchange form {size(exchange)}, {eur(exchange / TB * PRICE_OBJECT_TB)} per month\n")


def t_unit():
    print("### T15. Carrying one copy of a million nanopublications for a year\n")
    static = PROFILES["mix"]["archive"] + PROFILES["mix"]["index"]

    def storage(bytes_per_np, price_tb):
        return bytes_per_np * 1e6 / TB * price_tb * 12

    def loaded(copies, node_quads, price):
        return 1e6 * DYN_QUADS * copies / node_quads * price * 12

    rows_in = [
        ("Not held, only listed: an entry in the global indexes (NVMe)", "72 B", storage(12 + 60, PRICE_NVME_TB)),
        ("Segment files on a disk server", f"{static / KB:.1f} KB", storage(static, PRICE_HDD_TB)),
        ("Segment files on object storage", f"{static / KB:.1f} KB", storage(static, PRICE_OBJECT_TB)),
        ("Segment files on NVMe, for SPARQL at the registry", f"{static / KB:.1f} KB", storage(static, PRICE_NVME_TB)),
        ("Live in a registry (MongoDB), node filled to its disks: 190 million", f"{MONGO_BYTES_PER_NP / KB:.0f} KB",
         PRICE_NODE_BIG * 12 / (REGISTRY_NODE_FULL / 1e6)),
        ("Live in a registry (MongoDB), node kept at 10 million", f"{MONGO_BYTES_PER_NP / KB:.0f} KB",
         PRICE_NODE_SMALL * 12 / (REGISTRY_NODE_NP / 1e6)),
    ]
    for label, copies, node_quads, price in DYN_LAYOUTS:
        rows_in.append(("Loaded in Query. " + label, f"{DYN_QUADS * copies:.0f} quads", loaded(copies, node_quads, price)))
    rows = []
    for label, per_np, year in rows_in:
        rows.append([label, per_np, f"€{year:,.2f}" if year < 10 else f"€{year:,.0f}", num(100 * 12 / year * 1e6)])
    table(["Way of holding", "Per nanopublication", "Per million and year", "Carried for €100 per month"], rows)


def live_notes():
    """Figures quoted in section 4.2: 3 billion nanopublications live in registries, or loaded in Query, one copy."""
    d = 3e9 / 1e6
    lo, hi = PRICE_NODE_BIG * 12 / (REGISTRY_NODE_FULL / 1e6), PRICE_NODE_SMALL * 12 / (REGISTRY_NODE_NP / 1e6)
    loaded = [1e6 * DYN_QUADS * c / q * price * 12 for _, c, q, price in DYN_LAYOUTS]
    print(f"3 billion, one copy, per month: live in registries {eur(d * lo / 12)} to {eur(d * hi / 12)}; "
          f"loaded in Query {eur(d * min(loaded) / 12)} to {eur(d * max(loaded) / 12)}\n")


def operator_notes():
    """Figures quoted in section 7.3: one operator covering a billion nanopublications of one domain."""
    static = PROFILES["mix"]["archive"] + PROFILES["mix"]["index"]
    mass, small = 1e9, TRUST_NP + CORE_NP        # trust and core are loaded in full
    tb = (mass + small) * static / TB
    out = [f"registry, segments on disk {eur(PRICE_NODE_SMALL + tb * PRICE_HDD_TB)}",
           f"registry, segments on NVMe {eur(PRICE_NODE_SMALL + tb * PRICE_NVME_TB)}"]
    for share in (0.01, 0.10, 1.0):
        cost, k = min((dyn_nodes(small + mass * share, c, q, replicas=1) * price, dyn_nodes(small + mass * share, c, q, replicas=1))
                      for _, c, q, price in DYN_LAYOUTS[1:])
        out.append(f"Query with {share:.0%} loaded {eur(cost)} ({k} nodes)")
    print("One operator covering a billion, per month: " + "; ".join(out) + "\n")


if __name__ == "__main__":
    print(f"RDF4J today: {RDF4J_BYTES_AT_88K / 88_000 / KB:.0f} KB per nanopub, "
          f"{RDF4J_BYTES_AT_88K / RDF4J_REPOS / MB:.1f} MB per repository\n")
    for t in (t_quads, t_storage, t_status_quo, t_build, t_rate, t_cost, t_sensitivity,
              t_global_indexes, t_signatures, t_publisher, t_snapshot, t_blend, t_dynamic, t_clone, t_unit):
        t()
    clone_notes()
    live_notes()
    operator_notes()
