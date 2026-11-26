# Scaling nanopublications to billions and beyond

> **Draft, work in progress.** Version 0.1, 26 November 2026. The content is incomplete and will change. The design is a proposal, and several inputs are assumptions.

A working document: concepts, calculations, costs and a plan.

All tables marked T1 to T15 are produced by [`projections.py`](projections.py). Each input there is tagged as measured or assumed, so a better measurement can replace an assumption and the tables follow. Sources for the measured values are in [Appendix A](#appendix-a-measurements-and-sources).

## Summary

The network holds 108,975 nanopublications today. The targets are hundreds of millions within one year (taken here as 300 million by the end of 2027) and tens of billions within two to three years (30 billion by the end of 2029). That is a factor of 3,000 and then another factor of 100.

The main findings:

1. **Storage is not the problem.** One full copy of 30 billion nanopublications, compressed and indexed for lookup and SPARQL, needs about 42 TB (range 21 to 115 TB, depending on record size and on one design choice about stored serializations). Three independent copies cost about €1,300 per month to store at late-2026 list prices.
2. **One node of the current stack carries about 10 million.** A registry accepts about 16 nanopublications per second by POST and syncs about 50 per second from a peer. A query node loads about 12 per second and stores 136 KB per nanopublication across 2,800 LMDB repositories. At 300 million, a new query node would need 289 days for its initial load, so new nodes have to start from copied checkpoints and not from a replay (4.11). Tuning one node buys an order of magnitude. The rest has to come from distributing nodes by key and type coverage, which the design provides for and production does not use yet, and from static storage.
3. **Nanopublications are immutable and append-only, so the right storage engine is a set of sealed, immutable files.** The read-only registry mode on the `202-read-only-rete-mode` branch is the first instance of this: 102,500 nanopublications built into one 394 MB file in under eight minutes on a laptop, served by a stateless container with no database, and queryable with SPARQL in place.
4. **The proposal is to split the network into two planes.** A *live plane* (today's Registry and Query, improved, and distributed over many nodes by key and type coverage) handles interactive publishing, trust, spaces, templates, views and whatever data is worth keeping in a mutable, fully queryable store. A large *static plane* holds sealed *segments* of one to ten million nanopublications each, replicated as files and verified by hash. The live plane seals its older content into segments continuously, the way a log-structured store compacts. The split is one of storage only, and there are levels between the two ends: a nanopublication can be live in a registry without being loaded in any Query instance, which frees publishing from Query's load rate, or it can be queried from segments without being loaded. Query instances stay as they are and load the types they need, from live registries and from static ones alike. What is not loaded is fetched and queried at the registries, which can offer SPARQL on their segments at almost no extra cost. The dynamic part is sharded strictly by type. A query declares the types it reads and a quantity, lists are capped so that one excessive key cannot affect it, and the `full` repository is retired. How large the dynamic part is then becomes a target to set. Ten percent is eight nodes of today's design at 300 million. At 30 billion it is between 33 and 790 nodes, depending on how much one node can carry.
5. **Trust does not grow with the data.** IDEBT runs over introductions and endorsements only. A bulk dataset of a billion records needs one key, one introduction and a handful of endorsements.
6. **Query is the hard part.** 30 billion nanopublications are about 1.2 trillion quads, 4.5 times the largest public SPARQL endpoint today (UniProt, 266 billion triples). Interactive queries have to be routed to the slice they need (by key, by type, by segment), and cross-cutting questions answered from a compact global metadata index and from precomputed views. Arbitrary SPARQL over everything is possible only as a periodically rebuilt snapshot, which by extrapolation from QLever's published UniProt figures would need about 31 TB of NVMe and eight days to build.
7. **Costs are per operator and per nanopublication, and small next to people.** The network has no central budget. Each operator pays for the clusters of types it covers and for the share it keeps loaded. One copy of a million nanopublications costs €0.03 to €0.37 per year as static files and €27 to €272 loaded in a query store. An operator covering one billion pays about €60 per month for a registry, about €260 for Query with 1% loaded, and about €2,500 with everything loaded. Summed over a network of 30 billion with three copies and little loaded, that is about €3,200 per month. A team to build and operate this costs between six and a hundred times more than the machines at every scale considered here. And if each record cost even a tenth of a cent to produce, 30 billion of them would cost 30 million euros, so the bulk has to come from deterministic conversion of existing structured data.

What to do first, in order: finish and merge the read-only mode on a current rete version; decide whether serialized blobs stay in the file (they are about four fifths of it); define the segment and its manifest; republish the first-generation corpus of about 10.8 million nanopublications as the first static registry; then expose SPARQL on the segments at the static registry, and let Nanopub Query load selected types from it.

## 1. Where we are

### 1.1 The network on 25 November 2026

| | Value | Source |
|---|---:|---|
| Nanopublications | 108,975 | `/.json` of all three registries |
| Agents / accounts | 810 / 919 | same |
| Growth | 79,672 (4 May), 88,977 (31 Aug), 102,500 (3 Nov), 108,975 (25 Nov) | paper, admin log, design notes |
| Growth rate | about 120 to 300 per day | derived |
| Registries | 3 full (OVH Canada, Hetzner Finland, Hetzner Germany), 1 at Univ. of Vienna | admin repository |
| Query nodes | 3, one per host above | admin repository |
| Hosts | 6 to 14 cores, 32 to 64 GB RAM, 2 × 512 GB NVMe | admin repository |

All three registries hold every nanopublication, and so do all three query nodes.

### 1.2 What one nanopublication costs today

Measured on the snapshot of 3 November (102,500 nanopublications) unless noted.

| | Per nanopublication | Total |
|---|---:|---:|
| Quads | 39.5 | 4.05 million |
| N-Quads, uncompressed | 10.6 KB | 1.09 GB |
| TriG as served | 4.4 KB | 453 MB |
| Jelly stream | 2.46 KB | 252 MB |
| Jelly, compressed (newest 8,975: zstd / gzip) | 0.55 / 0.73 KB | |
| Registry file (`registry.rete`: content, list metadata, TriG and Jelly blobs) | 3.84 KB | 394 MB |
| RDF4J store of one query node (at 88,000) | 136 KB | 12 GB |
| RDF4J memory | | 6.2 GB resident |
| MongoDB memory of one registry | | about 1.5 GB resident |

Two things stand out. First, compressed Jelly is 0.55 KB, of which roughly 0.26 KB is the RSA-2048 signature, which is random and cannot be compressed. Second, the query node spends 136 KB per nanopublication, 250 times the compressed record. Most of that is the fixed cost of 2,800 separate LMDB repositories (one per public key and one per type), which works out to 4.3 MB per repository.

The first-generation corpus gives a second data point: rete's changelog reports a nanopublication dump of 378.7 million quads in 43.2 million named graphs (about 10.8 million nanopublications, 35 quads each) built into a 2.52 GB file. That is 233 bytes per nanopublication for the indexed content quads, for records that are mostly unsigned.

### 1.3 Rates

| | Rate | Source |
|---|---:|---|
| Registry, publishing by POST | 15 to 16 per second | nginx configuration notes: the POST path is one ordered queue |
| Registry, sync from a peer | about 50 per second | 89,000 in about 30 minutes |
| Query node, initial load | about 12 per second | 87,000 in about 2 hours |
| Query node, RDF4J CPU under normal traffic | 4.7 cores sustained | about 100 API calls per minute fleet-wide |
| Static build: verify and write N-Quads | 295 per second per thread | 102,500 in 5 min 48 s |
| Static build: `rete build` | 64,000 quads per second (0.5.0, laptop); 222,000 (0.7.0, per changelog) | |
| Static serve: all nanopublications as one stream | 3,900 per second | 102,500 in 26 s |
| Static serve: one nanopublication, one list page | 10 to 50 ms | |

### 1.4 What the incident log says about scaling

The admin log for August to October 2026 is mostly about the query layer, at a corpus size of 90,000:

- Eleven LMDB corruption events in three weeks, each repaired by wiping the store and reloading for two hours. The root causes were an RDF4J bug in value-identifier allocation after reopening a store, and unclean shutdowns.
- The single `full` repository is read constantly. RDF4J only writes to disk when no read is open, so `full` went 16 hours without persisting and lost records on restart. A watchdog now forces a flush.
- Splitting data into per-key and per-type repositories made page loads federate across repositories through one HTTP route, which deadlocked the connection pool. The fix was to route queries back to `full`.
- A resync on a live node cycles 2,800 repositories through a 100-slot cache and drops to 50 nanopublications per minute.
- One nanopublication with a valid signature and a wrong hash stopped ingestion on every query node until the loader learned to skip it.
- Crawlers were three quarters of front-end traffic and triggered most of the overload windows.

The registry and MongoDB do not appear in the log as a source of trouble at this size. The lesson for scaling is that mutable stores under concurrent read and write load were the expensive part to operate, with five orders of magnitude still to go.

## 2. What the targets mean

### 2.1 Statements

**T1. Statements**

| Nanopublications | Quads (mix, 39.5) | Quads (lean, 20) |
|---|---:|---:|
| 109 thousand | 4.3 million | 2.2 million |
| 10 million | 395 million | 200 million |
| 100 million | 4.0 billion | 2 billion |
| 300 million | 12 billion | 6 billion |
| 1 billion | 40 billion | 20 billion |
| 3 billion | 118 billion | 60 billion |
| 10 billion | 395 billion | 200 billion |
| 30 billion | 1.2 trillion | 600 billion |
| 100 billion | 4.0 trillion | 2 trillion |

For comparison, all of Wikidata is 17.9 billion triples (August 2026 dump), and UniProt, the largest public SPARQL endpoint, is 266 billion (release 2026_04). The one-year target of 300 million nanopublications is already two thirds of Wikidata. Thirty billion nanopublications of today's shape would be 4.5 times UniProt. Lean bulk records of about 20 quads halve that.

Wikidata is also the cautionary case. Its query service ran one mutable Blazegraph store of 16 billion triples. A full reload last took about three months, the graph had to be split in two, and the service is now moving to QLever.

A good share of those quads are structural. Every nanopublication has four head triples and about five signature triples that follow mechanically from the rest. A query index does not need them, and leaving them out saves about a quarter of the quads for today's mix and nearly half for lean records.

### 2.2 Rates

**T5. Required average ingest rate along the trajectory**

| End of | Nanopublications | Average nanopubs/s | Per day |
|---|---:|---:|---:|
| 2026-Q4 | 110 thousand |  |  |
| 2027-Q1 | 10 million | 1 | 0.1 million |
| 2027-Q2 | 30 million | 3 | 0.2 million |
| 2027-Q3 | 100 million | 9 | 0.8 million |
| 2027-Q4 | 300 million | 25 | 2.2 million |
| 2028-Q2 | 1 billion | 44 | 3.8 million |
| 2028-Q4 | 3 billion | 127 | 11.0 million |
| 2029-Q2 | 10 billion | 444 | 38.4 million |
| 2029-Q4 | 30 billion | 1,268 | 109.6 million |

The trajectory is a choice, not a forecast: a factor of about three per quarter in 2027 and per half year after that. The averages are modest for machines. Day-to-day publishing by people through Nanodash, at a few hundred per day, will never produce these numbers. They come from two sources.

**Bulk conversion of existing structured data.** The table gives the order of magnitude of what exists. The figures are approximate and need checking before they are quoted elsewhere.

| Source | Natural unit | Count |
|---|---|---:|
| First-generation nanopublication corpus | nanopublication | 10.8 million |
| Wikidata | statement with qualifiers and references | about 1.6 billion |
| OpenCitations Index | citation | over 2 billion |
| OpenAlex | work | 476 million |
| Crossref, DataCite | DOI record | 100 to 200 million each |
| UniProtKB | protein entry | about 250 million |
| PubChem | compound | about 120 million |
| GBIF | occurrence record | about 3 billion |

Two or three sources of this kind reach the one-year target. All of them together reach about ten billion.

**Software agents.** A million agents publishing 100 records a day would produce 36 billion a year. This is where tens of billions and beyond would come from, and it is the reason the live plane has to seal continuously (section 4.3).

### 2.3 The count is not the goal

Republishing an existing dataset as nanopublications adds value when per-record provenance, signatures, citation, versioning or uniform access across sources is worth something to a reader. Where it is not, it adds a larger number and a storage bill. The plan below makes large numbers cheap. It does not make them useful, and the choice of what to publish in bulk deserves the same care as the engineering.

The cost of producing records matters more than the cost of hosting them. Storing a million nanopublications for a year on three replicas costs between €0.25 and €1.40 (section 7.8). Producing a million records with a language model, at 500 to 1,000 output tokens each and a few euros per million tokens, costs thousands of euros. At 30 billion records that is tens of millions of euros against a hosting bill of a few thousand per month. Deterministic conversion costs close to nothing per record.

## 3. Why the current stack does not get there unchanged

**T3. Today's live stack, extrapolated unchanged**

| Nanopublications | MongoDB per registry | RDF4J per query node | Publish by POST | New registry syncs | New query node loads |
|---|---:|---:|---:|---:|---:|
| 109 thousand | 1.1 GB | 12 GB | 2 h | 36 min | 3 h |
| 10 million | 100 GB | 219 GB | 7 days | 2 days | 10 days |
| 100 million | 1.0 TB | 2.2 TB | 75 days | 23 days | 96 days |
| 300 million | 3.0 TB | 6.6 TB | 224 days | 69 days | 289 days |
| 1 billion | 10 TB | 22 TB | 2 years | 231 days | 3 years |
| 3 billion | 30 TB | 66 TB | 6 years | 694 days | 8 years |
| 10 billion | 100 TB | 219 TB | 20 years | 6 years | 26 years |
| 30 billion | 300 TB | 657 TB | 61 years | 19 years | 79 years |
| 100 billion | 1.0 PB | 2.2 PB | 205 years | 63 years | 264 years |

The MongoDB size per nanopublication (10 KB) is an assumption. The marginal RDF4J size (22 KB) is derived: RDF4J documents 120 to 130 bytes per quad for its LMDB store, and each nanopublication is stored about 3.4 times (in `full`, in its key repository and in 1.4 type repositories on average) with about 12 admin triples each time. The durations are measured rates extrapolated linearly, which flatters them, since insert rates into B-tree stores fall as the data outgrows memory.

The binding constraints, in the order they bite:

1. **Query load rate.** At 12 per second, a new or wiped query node takes 10 days at 10 million and most of a year at 300 million. Every corruption event so far was repaired by a full reload.
2. **One LMDB repository per key and per type.** The fixed cost of 4.3 MB per repository means a million agents would need about 4 TB of mostly empty stores, before any data. The number of keys grows with the number of agents, so this layout fails on agent count, independent of nanopublication count.
3. **The `full` repository.** The Query README already calls it not scalable. It is also where the write-starvation and changeset problems occurred.
4. **Serialized publishing.** One ordered queue at 16 per second. The profiling in registry issue #57 found the time goes to round trips to MongoDB, with the CPU nearly idle.
5. **Sync by nanopublication.** Peers replicate by walking lists entry by entry. At 30 billion, streaming everything over one connection takes 89 days at the best measured rate.
6. **Everyone holds everything.** Coverage by type and key exists in the registry, and the simulation in the ecosystem paper shows that type-sharded coverage lifts cluster ingest by about 1.5 times. All production nodes still run with full coverage.

None of this is a design flaw at today's size. The stack was built for interactive use, and it does that. With the fixes in section 5.1 one node should carry 10 million nanopublications comfortably. Beyond that, the dynamic part grows by adding nodes that each cover a set of types (section 4.10), and the static plane holds everything that does not need a mutable store.

## 4. Principles for scaling

### 4.1 Immutable data wants immutable storage

A nanopublication never changes. The only mutable facts about it are which lists it is on and whether a later nanopublication invalidated it. MongoDB and LMDB are built for data that is updated in place. They pay for that with write amplification, with caches that must fit the working set, and with recovery procedures when a write is interrupted. None of it buys anything for append-only records.

The alternative is the log-structured pattern: new records go to a small mutable store, and at intervals a batch is sealed into an immutable, sorted, indexed file. Readers consult the sealed files and the small mutable remainder. Sealed files are trivially safe (a crash cannot corrupt a file nobody writes), cacheable, and copyable with any file transfer tool. Their integrity is one hash.

Two other open networks of signed records have made this move or were built this way:

- **Certificate Transparency.** Let's Encrypt ran its logs on databases at an annual cloud cost it described as approaching seven figures, with 7 to 10 TB per log shard. The static tile design (Sunlight) serves a log from plain files. One operator reports running such a log, with 1.9 billion entries in its largest six-month shard and 314 GiB in total, for $10,000 per year including hardware and bandwidth. Let's Encrypt shut down its database-backed logs in February 2026.
- **Bluesky.** The AT Protocol network holds tens of billions of signed records from 48 million accounts. An individual runs a full-network application view on one rented server with 16 TB of data for about $200 per month, and a relay for $30 per month.

### 4.2 Two planes

**The live plane** is today's Registry and Query, which are two services with separate holdings (see the levels below). It accepts publications, runs the trust computation, and holds whatever changes: introductions, endorsements, spaces, roles, templates, queries, views, recent content. One node carries about 10 million nanopublications. The plane as a whole is distributed by type over as many nodes as the chosen dynamic part requires (4.10), and content that no longer needs a mutable store is sealed.

**The static plane** is a set of *segments*. A segment is a sealed file holding a batch of nanopublications with everything a registry needs to serve them: the content, the per-key and per-type lists with their checksum chains, and the lookup structures. The registry file of the read-only mode is exactly this. A stateless registry process serves any number of segments from local disk or from object storage, and the same file answers SPARQL.

```
                        publish                                  bulk build
                           |                                         |
                 +---------v----------+                    +---------v---------+
   LIVE PLANE    |  Registry (hot)    |  -- seal ------->  |     Segments      |   STATIC PLANE
   10^7 per node |  trust, quotas     |                    |  sealed files of  |   10^8 to 10^11
                 |  Query (hot)       |                    |  1 to 10 million  |
                 |  spaces, views     |                    |  nanopublications |
                 +---------+----------+                    +---------+---------+
                           |                                         |
                           |   manifests, introductions,             |  copied as files,
                           |   endorsements, invalidations           |  verified by hash
                           |                                         |
                 +---------v-----------------------------------------v---------+
                 |  Routing: identifier resolver, metadata index, catalog      |
                 +-------------------------------+-----------------------------+
                                                 |
                              Nanodash, agents, query clients
```

**The planes are the two ends, and there are levels between them.** Registry and Query are separate services, and each holds a nanopublication in its own way. A nanopublication can be live in a registry without being loaded in any Query instance, and it can be queryable from segments without being loaded.

| Level | Where it is held | Publish one at a time | Fetch by identifier, sync by list | SPARQL | One copy of a million, per year |
|---|---|:-:|:-:|---|---:|
| Archived | Segment files, served by a read-only registry | | yes | at the registry, over the segment or dataset | €0.03 to €0.37 |
| Live in a registry | MongoDB | yes | yes | no | €16 to €71 |
| Loaded in Query | RDF4J, fed from a live registry or from segments | | | everything Query offers, complete for the instance's coverage | €27 to €272 |

The first two rows are the ways of holding a nanopublication. Every nanopublication is archived or live in at least one registry, or it does not exist in the network. The last row is a copy that a Query instance makes for querying. Each operator chooses per cluster of types (4.10) what its registry holds and what its Query instance loads, and the choices combine freely. Archived content costs €0.03 per million and year on disk and €0.37 on NVMe, which is where it should sit if it is queried often.

**Listed is not a way of holding.** A node that holds no copy of a nanopublication can still know that it exists. The global indexes (4.6) carry an entry for it, with its key, types and date and with the nodes that do hold it. This document calls that *listed*. It costs €0.02 per million and year, and it is a pointer to a copy elsewhere. If the last holder goes away, the entry points to nothing, which is why the number of holders per cluster has to be watched (4.10).

Three combinations matter most.

- *Live in a registry, in no Query instance.* The record is accepted at once, fetched by identifier, synced by list, retracted and superseded like any other, and counted against quotas. It cannot be queried, so Nanodash does not list it. This is the right level for a stream of records that arrive one at a time and that nobody queries yet, and for an operator who keeps a domain without offering queries over it.
- *Live in a registry, queryable by checkpoint.* The registry publishes a checkpoint per type (4.11) and offers SPARQL on it, as on any segment. The content is queryable with a lag of one checkpoint interval and without any load.
- *Archived and loaded.* A static dataset whose structural types, or a capped part of whose lists, are loaded into Query (4.9).

**Publishing no longer waits for Query.** Today every Query instance loads everything its registry holds, at 12 nanopublications per second, so the slowest component sets the pace of the whole network. When a registry may hold what no Query instance loads, live publishing is bounded by the registry, at 16 per second today and several hundred with the batch path, and each Query instance loads what its policy selects. The incident log of 2026 is also almost entirely about the query layer, so content that stays out of Query stays out of that risk.

**The registry's live store can then be much larger than what Query loads.** Its limit is not known. The 10 million per node used elsewhere in this document is a target for the hot window, not a ceiling of MongoDB. A node filled to its disks would hold about 190 million at the assumed 10 KB per nanopublication, which has not been tested. Three billion live in registries would cost €4,000 to €18,000 per month for one copy, against €6,600 to €68,000 loaded in Query. Live content is still 40 to 2,000 times more expensive to hold than archived content, so sealing stays the destination for everything that is no longer recent.

**What this needs.** A load policy in Query that is narrower than its registry's coverage (4.9), since today Query loads all that its registry has. And global indexes that are fed from the registries, not from Query. Otherwise a nanopublication that is live in a registry and loaded nowhere can be found only by someone who already knows its identifier or its key.

The split is about storage. A reader, a Nanodash view or a query template should not have to know which plane a nanopublication is on. The planes are joined in five places: trust (4.4), sealing (4.3), invalidation (4.7), routing (4.6), and selective loading of static content into the live query services (4.9).

### 4.3 The segment

Proposed properties:

- **Size.** One million nanopublications by default, ten million at most. One million is about 1.4 GB for today's mix and 0.7 GB for lean records. Reasons to stay small: rete readers currently support 32-bit term identifiers only, which caps a file at 4.3 billion terms, somewhere between 150 and 400 million nanopublications depending on what the file holds; a legally required deletion means rebuilding the segment; a failed transfer or a failed validation costs one segment; and objects up to 512 MB stay cacheable on Cloudflare's standard plans, which argues for half a million lean records per file where CDN caching matters.
- **Scope.** One signing key per segment where the key is large enough to fill one. Small keys share segments. The per-key and per-type lists inside the file are what a peer or a query service reads, so a segment can mix keys and types without affecting consumers.
- **Canonical source.** The compressed Jelly stream (or the N-Quads file the build already writes) is the authoritative form, and the segment file is derived from it. rete is before version 1.0 and has changed its file format three times since July. Keeping the source means a format change costs one rebuild at about 200,000 quads per second.
- **Manifest.** A nanopublication, published on the live plane and signed by the builder, that states: the hash of the segment file and of its source, sizes, the number of nanopublications, the keys and types covered, for each list the range of positions and the XOR checksum of the segment's entries, the format and builder versions. Trusty URIs already have a module for byte content, so the file gets a verifiable identifier of the same kind as the nanopublications in it.
- **Availability statements.** Each mirror publishes a small nanopublication saying that it serves a given segment at a given address. These can be retracted, so the catalog of who holds what is itself a set of nanopublications and needs no central registry. This is the Knowledge Space pattern of service introductions and assessments applied to files.

**Checksums compose.** A list checksum is the XOR of the hashes of its entries. So the checksum of a list that spans segments is the XOR of the per-segment checksums in the manifests. A peer can check that it holds a complete list of a billion entries by combining a thousand values, without touching the entries.

**Sealing.** A live registry seals when a list or the store reaches a threshold: it writes the oldest entries to a segment, publishes the manifest, and drops them from MongoDB once enough mirrors have published availability statements. The same mechanism gives regular bulk archives (registry issue #115), since a sealed segment can be deposited at Zenodo or a library as it is.

For agent-scale publishing the sealing interval shrinks. At 100 nanopublications per second, a million-record segment fills in under three hours. The pattern is then a few small recent segments built every few minutes and merged into full-size ones later, which `rete merge` supports.

### 4.4 Trust stays on the live plane

The trust computation reads introductions and endorsements. Its size is bounded by the number of endorsements (Lemma 2 in the ecosystem paper): 772 paths for 692 accounts in the May snapshot. A bulk publisher adds one account. A million agents would add a million accounts and a few million endorsements, on the order of gigabytes, which one machine handles.

A read-only registry therefore publishes no trust state of its own, as the design notes on the branch already decide. A consumer establishes trust in static content in two steps: the signing key is introduced and endorsed on the live plane, and the manifest is signed by a key the consumer accepts. Every nanopublication in the segment still carries its own signature, so any reader can check any record without trusting the builder.

Full validation of a segment by every mirror would be wasteful. The validation run on the branch took 26 minutes for 102,500 nanopublications with content sampling. The proportionate scheme is: the file hash on every copy, a random sample on every mirror, and complete re-verification by a few independent parties who publish the result as an assessment.

### 4.5 Replication is file copying, and coverage is partial

Copying one replica of 30 billion nanopublications at 1 Gbit/s takes four days (T4). Any tool works: HTTP range requests, object storage sync, rsync, BitTorrent.

At 42 TB per copy, not every participant will hold everything, and nobody needs to. The existing coverage settings by key and type extend to segments: a mirror declares what it covers, and the definition of "published" in the Knowledge Space (held by several independent services) is checked per segment from the availability statements. A monitor can then report segments with fewer than three holders, which is the number that matters for durability.

### 4.6 Finding a nanopublication

Today any registry answers for any identifier. With partial coverage, a resolver must map an artifact code to a holder.

Trusty hashes are uniformly distributed, which makes this cheap. A sorted array of hash prefixes with a segment number takes 12 bytes per nanopublication, and interpolation search finds an entry in one or two reads, so the array can sit on object storage and be queried with range requests. A set of per-segment filters takes about 9 bits per nanopublication and fits in memory.

**T8. Global indexes**

| Nanopublications | Identifier resolver (sorted, 12 B) | Same as filters (9 bit) | Metadata index (60 B) | Invalidation overlay (3%, 40 B) |
|---|---:|---:|---:|---:|
| 300 million | 3.6 GB | 338 MB | 18 GB | 360 MB |
| 3 billion | 36 GB | 3.4 GB | 180 GB | 3.6 GB |
| 30 billion | 360 GB | 34 GB | 1.8 TB | 36 GB |
| 100 billion | 1.2 TB | 112 GB | 6.0 TB | 120 GB |

The resolver for 30 billion nanopublications is 360 GB as a sorted file or 34 GB as filters. It is derived entirely from the manifests and the segments, so anyone can build one, and the Nanopub Router is the natural place to run it.

### 4.7 Invalidation

Retractions and new versions arrive after the nanopublication they affect, possibly after it was sealed. A sealed file cannot take the `invalidated` flag that MongoDB sets today.

The log-structured answer is an overlay: a small mutable table of (invalidated identifier, invalidating identifier), kept on the live plane and published as periodic sealed deltas. Readers apply it at query time. At 3% invalidated and 40 bytes per entry it is 36 GB at 30 billion. When a segment is rebuilt or merged, the overlay entries for it are folded into the file. Invalidations are only honoured within one key, as today, so the overlay partitions by key.

### 4.8 Query in tiers

No single mutable store can hold a trillion quads and answer arbitrary SPARQL interactively. The realistic design offers different guarantees at different scopes:

| Tier | Scope | Mechanism | Cost |
|---|---|---|---|
| 0 | One nanopublication, one list page | Registry API on a segment | 10 to 50 ms, measured |
| 1 | One segment | SPARQL at the registry that serves the file, or in the client by range requests | No extra storage |
| 2 | One dataset: the segments one registry holds for a publisher | Federation over those segments at the registry, or a merged snapshot per dataset. Complete for the dataset, not for a key or type. | Grows with the number of segments, unless merged |
| 3 | Everything, metadata only | Global metadata index: identifier, key, types, creation time, signer, invalidation | 60 bytes per nanopublication |
| 4 | A declared scope: a set of types up to a stated quantity | RDF4J on a node that carries those types, with lists capped where a type exceeds the quantity (4.10), next to the structural types and the small mutable repositories (spaces, trust) | As today, bounded at about 10 million per node |
| 5 | Everything, arbitrary joins | A periodically rebuilt analytical snapshot with query time limits. Not what applications depend on. Anyone can build one from the segments. | About 31 TB of NVMe and 8 days to build at 30 billion (section 7.3) |

Consequences for the existing software:

- `full` is retired. Queries declare the types they read and a quantity (4.10). Questions that name no type go to the global indexes.
- Per-key and per-type repositories are kept only for keys and types above a size threshold. Small ones share repositories, bucketed by hash prefix.
- Query templates declare the scope they need. Most already target a type repository. The few that scan `full` are the ones to rewrite or to back with a precomputed view.
- Tier 2 has a real design choice. Federating a selective query over a thousand segments is slow, even with per-file statistics to skip segments. Merging a dataset's segments into one query snapshot of up to about 100 million nanopublications avoids that (rete has built 9.8 billion triples into one 52 GB file) but stores the index a second time, which adds roughly 0.5 KB per nanopublication to the estimates in section 6.
- Finding which segments mention a given IRI needs a term-to-segment index. For rare terms that is a real structure, on the order of 100 GB at 30 billion. It is the least worked-out part of this plan.

### 4.9 Blending the two planes

Static content has to show up in the live query services, or the static plane is an archive next to the network instead of a part of it. The rule proposed here is simple. Query instances stay as they are: RDF4J repositories filled by loading, and complete for what the instance declares to cover. Static content enters them the way live content does, by being loaded from a registry. What is not loaded is queried where it is held, at the registry that serves the segments.

**Why Query does not answer from segment files.** A segment holds a batch. It can never be assumed to hold all of a key or all of a type. A type repository answered from segments would give partial answers under an address that promises the type, and a type that is partly loaded and partly in files would need federation for every count and join. So the repository addresses of Query keep one meaning: loaded content, complete within the instance's declared coverage and caps.

**How much depends on Query staying as it is.** The local mirror of the published query templates has 761 of them. 391 target the `full` repository and 231 a type repository. 746 use the admin graph that Nanopub Query writes (`npa:graph`), and 660 exclude invalidated nanopublications with a graph pattern on `npx:invalidates`. All of this keeps working for static content that is loaded, because nothing in Query changes.

**A load policy per type.** Types are the natural unit. Registry lists are already kept per key and type, inside segments as well, and Query repositories are per type. Each Query instance decides for each type, or for each pair of key and type, whether it is loaded:

| | Where the data is | What works | Cost per nanopublication on this instance |
|---|---|---|---|
| Loaded | Copied into RDF4J from a live registry or from a static registry's segments, like any nanopublication today | Everything Query offers, including text search and joins without federation | About 22 KB of NVMe, and load time |
| Not loaded | At the registries that hold it, live or in segments | Fetching by identifier and by list. SPARQL at the segment endpoints of those registries (below). Listings from the global indexes. | Nothing |

A loaded copy is a cache of the static truth. It can be dropped and rebuilt at any time, and it does not count towards durability.

**Which types are loaded.** By role first, by size second.

- *Structural types, always loaded, from whichever plane they were published on:* introductions and endorsements, spaces with their roles and memberships, templates, queries, views, class and property definitions, dataset descriptions, segment manifests, retractions. They make everything else interpretable, they are what Nanodash renders pages from, and they grow with the number of communities and agents, not with the number of records.
- *Data types an instance's users work with,* within the instance's budget. This is a choice per instance. A biodiversity node loads biodiversity types and leaves the rest to others.
- *Mass record types* are not loaded, or are loaded with capped lists (4.10).

A publisher can recommend in the manifest which types to load. The operator of the Query instance decides.

**T12. Bringing a static type into one Query instance**

| Nanopublications of the type | RDF4J size | NVMe per month | Load time today | Load time at 300 per second |
|---|---:|---:|---:|---:|
| 100 thousand | 2.2 GB | €0.05 | 2 h | 6 min |
| 1 million | 22 GB | €0.48 | 23 h | 56 min |
| 10 million | 219 GB | €4.82 | 10 days | 9 h |
| 100 million | 2.2 TB | €48 | 96 days | 4 days |

A type of a million nanopublications takes a day to load today and an hour once the load path is faster. Ten million is then the practical ceiling per node. A larger type is loaded with capped lists (4.10), and the rest is queried at the registries that hold it.

**SPARQL at a segment-based registry.** The read-only registry already reads its file through a SPARQL endpoint, and the file contains the nanopublications' own graphs next to the registry metadata. Offering queries on segments is therefore mostly a matter of exposing that endpoint, with time and result limits. What such an endpoint is and is not:

- *Its scope is the segments it is opened on,* as described by their manifests: one segment, or the segments of one dataset, federated or merged into one snapshot (4.8). It makes no claim about a key or a type as a whole.
- *It needs no Query instance and no load.* A bulk dataset is queryable where it is held as soon as the file is served.
- *It answers the state as sealed.* A retraction published later is not in the file. The registry applies the invalidation overlay (4.7) to its lookup and list answers, but SPARQL results come from the file as it is, and a client that needs current validity in a query checks against a Query instance, where retractions are always loaded.
- *It is not a Query repository.* The admin graph that Query writes is not in the file, so existing templates do not run there unchanged. The builder could add it at 0.1 to 0.2 KB per nanopublication, which is optional and can wait for demand.
- *A live registry offers the same on its sealed segments and checkpoints,* not on the part in MongoDB.

**What works with today's code.** A Query instance follows exactly one registry, by that registry's load counter, and inherits its coverage. A registry can already restrict its coverage to a set of types and then pulls only those per-type lists from its peers, skipping ahead by checksum. So a coverage-restricted registry that has a static registry among its peers, with a Query instance behind it, should load selected static types into RDF4J without new code in Query. This has not been tried yet, and it is the cheapest way to test the blend on the first static dataset. Its limits: one policy per pair of registry and Query instance, a second copy of the loaded types in MongoDB, and the dataset's key has to be admitted by the bridge registry's coverage and quota settings.

**What Query needs.**

1. *Several sources, a cursor per source.* A live registry is followed by its load counter, as now. A static source is followed by its manifests: the cursor is the set of segments already processed, and the counter ranges in the manifests take the place of load numbers.
2. *A load policy of its own.* Per cluster and type, with list caps, and narrower than the coverage of the registries it follows. Today Query loads all that its registry has.

**What happens to `full`.** Half of the published templates target `full`. With scopes declared per query, `full` is retired, except on deliberately restricted instances where it means that instance's small coverage (4.10). Each instance advertises which types it has loaded, with counts and caps, so that the Router can send a query to an instance that can answer it.

**Validity across the boundary.** A retraction published in Nanodash today may hit a record sealed two years ago. Retractions and new versions are therefore among the always-loaded types, wherever they were published. For loaded content this works as today: an invalidating nanopublication is on every list of the nanopublication it invalidates, so it arrives with the list, and the usual pattern in the templates gives the right answer. For content that is not loaded, the registry's overlay answers (4.7).

**Loading by reference.** When a live nanopublication refers to a static one (a comment, an endorsement, a citation, a new version, membership in a collection), the Query instance fetches that one target from the registry and loads it. Query already records such links in its network graph, so the trigger exists. The loaded set then consists of the structural types plus the part of the static plane that somebody has touched. It grows with activity, not with the size of the archive.

**Sealing is not unloading.** When a live registry seals old content into segments, the registry's storage moves. What a Query instance keeps loaded is decided separately by the type policy: structural types stay, a mass type keeps a recent window (today's `last30d`, bounded by count), and the rest is unloaded and remains at the registries.

### 4.10 Distributing the dynamic part by type

The dynamic part, as the term is used in this section, is what is loaded into Query, whether it was published live or loaded from segments. What registries hold live without any Query instance loading it is a separate and cheaper quantity (4.2). Ten million nanopublications is roughly what one node of today's design carries. It is not a bound on the network. With enough nodes the dynamic part can be any size, so its size is a target to choose, like the replica count.

**Shards are types.** A node covers a set of types and holds each of them whole. Types are semantic, they are what a query is about, and the registry already organizes everything by them. Within a type the unit is the list of one key, which is how the registry stores and syncs it. A type is never split between nodes, and no node needs to hold everything.

**Coverage is declared in clusters of types.** There are 1,502 types today, and operators cannot be expected to choose among them one by one. A cluster is a named set of types, such as trust, core, biodiversity, medicine or chemistry. It is the unit in which an operator declares coverage, in which checkpoints are published (4.11), and in which small types share a store. The network is then a matrix of operators and clusters, where R stands for a registry and Q for a Query instance:

| Operator | trust | core | biodiversity | medicine | chemistry |
|---|:-:|:-:|:-:|:-:|:-:|
| Museum of nature | R Q | R Q | R Q | | |
| University hub | R Q | R Q | R Q | R Q | |
| Pharma consortium | R | R | | R | R |
| AI startup | Q | | | Q | |

- *Trust is on every node.* It is small and grows with accounts, not with content: 2,849 introductions and endorsements today for 919 accounts, so about three million at a million accounts. Every registry needs it to compute trust, and every Query instance mirrors the result.
- *Core is on most nodes.* Templates, queries, views, spaces and retractions. The six largest of these types hold about 19,000 nanopublications today. A node that serves Nanodash needs them. A node that runs only its operator's own queries over one domain can do without and load what it needs by reference (4.9).
- *Registry and Query are separate decisions.* An operator can keep and serve a domain without offering queries over it, or query a domain from a registry that somebody else runs. The second case needs a Query instance that follows several registries (4.9).
- *Scaling out means adding a row or a column.* A new domain is a new cluster, carried by whoever cares about it. No existing node grows because of it.
- *The number of copies is an outcome.* In the example medicine has three holders and chemistry one. Nobody sets a replica count for the network. The Monitor reports holders per cluster, and a cluster with a single holder is at risk until its content is sealed and mirrored.

Clusters need a definition that nodes can read: a nanopublication listing the types, or a rule over type IRIs. Open points are who maintains these definitions, whether a type may belong to several clusters, and where a type goes that nobody has assigned.

**A query declares its scope.** A query template states two things: the types it reads, and the largest number of nanopublications across those types it is meant to run over. An instance serves the query from a store that holds those types within that quantity. When a type has more members than the quantity allows, the instance caps the lists, longest first: it finds the largest cap L such that the lists, each cut to at most L entries, fit the quantity. Short lists are loaded whole, and only the excessive ones are cut. One key that has published a billion nanopublications of a type therefore cannot push a hundred thousand other keys out of a query's scope, and cannot make the query slow.

Measured on today's typed lists (8,481 lists, 142,807 entries, median length 1):

| Cap per list | Entries loaded | Share of all | Lists cut |
|---:|---:|---:|---:|
| 10 | 24,791 | 17% | 883 |
| 100 | 54,014 | 38% | 155 |
| 1,000 | 98,917 | 69% | 17 |
| 10,000 | 128,256 | 90% | 1 |

A cap of 1,000 leaves 8,464 of 8,481 lists untouched. The volume sits in a handful of lists, and the cap removes exactly that.

Two details need a decision. A cut list keeps either its newest L entries, which degrades gracefully and can be fetched from the end of the list, or its first L by position. List order can differ between registries, so the rule has to name the order it uses. And the instance has to report which lists it cut, so that a result over a capped scope is never mistaken for a complete one. The rest of a cut list stays reachable at the registries that hold it, by list and, where it is sealed, through the segment endpoints (4.9).

**`full` is retired.** With scopes declared, no query needs a repository of everything, and none can be offered at scale. `full` remains only on deliberately restricted instances, where it means that instance's small coverage, for example a community node with a few dozen types. Of the 391 templates that target `full` today, about 181 name a fixed nanopublication type and can move to a declared scope mechanically. About 190 contain no type pattern. They look things up by identifier, by an IRI that is mentioned, or by a link between nanopublications, and they need the global indexes instead (limit 4 below). These counts come from a text search of the mirrored templates and are rough.

**Gathering a list costs its own length.** The nanopublications of one key and type can be collected at a cost proportional to their number, whatever else exists. This is a property of the registry design: each list is append-only with an index on position, and a checksum at every position, so a reader fetches a list, or its tail, or the part it lacks, without touching any other list. It holds in a segment file as well, where list entries sit in fixed-size batches. The read-only registry streams its largest list of 30,738 nanopublications in 5.8 seconds, about 5,000 per second. Three conditions apply:

- The reader has to know which registries hold the list. That is the coverage map below.
- Collecting a whole type means collecting one list per key, and most lists are tiny: 7,598 of today's 8,481 typed lists have ten entries or fewer, and one type already has 1,234 keys. The registry API goes from key to types. It needs the other direction as well: for a type, the keys with their list lengths and checksums, and one stream of all its lists.
- Retractions and new versions come along, since an invalidating nanopublication is placed on every list of the nanopublication it invalidates.

**What it costs.** The table sums over a network that holds every type three times and loads the stated share. What one operator pays for its own coverage is in sections 7.2 and 7.3.

**T13. Nodes and monthly cost of the dynamic part, three replicas of every type**

| Total | Dynamic share | Dynamic nanopublications | Dynamic quads | Today's layout: `full`, key and type repositories, RDF4J | Type shards, one copy per type, RDF4J | Type shards, one copy per type, engine at Wikidata scale |
|---|---:|---:|---:|---:|---:|---:|
| 300 million | 1% | 3 million | 154 million | 3 nodes, €777 | 3 nodes, €777 | 3 nodes, €1.8k |
| 300 million | 10% | 30 million | 1.5 billion | 8 nodes, €2.1k | 4 nodes, €1.0k | 3 nodes, €1.8k |
| 300 million | 30% | 90 million | 4.6 billion | 24 nodes, €6.2k | 10 nodes, €2.6k | 3 nodes, €1.8k |
| 3 billion | 1% | 30 million | 1.5 billion | 8 nodes, €2.1k | 4 nodes, €1.0k | 3 nodes, €1.8k |
| 3 billion | 10% | 300 million | 15 billion | 79 nodes, €20k | 33 nodes, €8.5k | 4 nodes, €2.5k |
| 3 billion | 30% | 900 million | 46 billion | 237 nodes, €61k | 98 nodes, €25k | 10 nodes, €6.1k |
| 30 billion | 1% | 300 million | 15 billion | 79 nodes, €20k | 33 nodes, €8.5k | 4 nodes, €2.5k |
| 30 billion | 10% | 3 billion | 154 billion | 788 nodes, €204k | 325 nodes, €84k | 33 nodes, €20k |
| 30 billion | 30% | 9 billion | 464 billion | 2,364 nodes, €612k | 974 nodes, €252k | 98 nodes, €60k |

The three layouts carry 11, 28 and 277 million nanopublications per node. The table is written in terms of a dynamic share of the total. With declared scopes the dynamic part is better described as the sum of what the published queries need, which grows with the number of communities and applications and not with the number of nanopublications. The table then says what a given sum costs.

- *Year one.* A dynamic part of 30 million, 10% of 300 million, is eight nodes of today's design, twice the present fleet, for about €2,100 per month. It needs partial coverage in production and little else.
- *At 30 billion.* A dynamic part of 3 billion is 154 billion quads, kept three times: about 790 nodes and €200,000 per month with today's layout, about 325 nodes and €84,000 with type shards that store each nanopublication once per type, and 33 nodes and €20,000 with a store that carries a Wikidata-size graph per node.

A dynamic nanopublication costs between €80 and €800 per million and year on three nodes, against €0.50 for a static one, a factor of 160 to 1,600.

Two levers set the efficiency of a node. Today each nanopublication is stored about 3.4 times on a node, in `full`, in its key repository and in its type repositories. With type shards and no `full`, it is stored once per type it has, 1.4 times on average. And the table assumes 2 billion quads for an RDF4J node, where today's nodes hold about 20 million and other RDF4J users report a billion. Stores that hold all of Wikidata (18 billion) on one machine exist. A second engine behind the same repository addresses is real work, since Nanopub Query depends on RDF4J for federation between local repositories and for text search, and it is the difference between 325 nodes and 33.

**What scales without a limit.** The total number of nanopublications, the number of types and the number of keys: each adds lists and nodes, and no component has to see all of them. Read load on a type: put the type on more nodes. The cost of gathering any one list. Trust, which every registry computes from two small types.

**Where the limits are.**

1. *The scope of one query has to fit one node.* That is 11, 28 or 277 million nanopublications, depending on the layout. The declared quantity is what makes this checkable before the query runs. A query over two types on different nodes can still be answered with one federated hop, at a cost.
2. *A type larger than a node cannot be dynamic in full.* Types are not split, so such a type is loaded with capped lists and the remainder is queried at the registries that hold its segments. Today the largest type holds 24% of all nanopublications, and all of it is one list from one key. If the shape of the distribution holds at 30 billion, the largest type would have several billion members. This is the main price of sharding strictly by type, and the cap is what makes it acceptable.
3. *Write rate into one type.* Every node that carries a type takes all writes to it. At a few hundred nanopublications per second per node, a type absorbs about 25 million a day. A bulk dataset of a billion in one type has to arrive as segments.
4. *Questions that name no type.* Everything that mentions a given IRI, what links to a given nanopublication, the latest publications across the network, text search over everything. Type shards cannot answer these, and this is what `full`, `meta` and `text` are used for today. They need global indexes: the identifier resolver, the metadata index, and an index from terms to nanopublications with their types, on the order of a few terabytes at 30 billion. A client then asks the index which types are involved and queries those with a quantity. This index is the least developed part of the plan.
5. *Nanopublications without a type.* 12,949 of the 102,500 in the snapshot, 13%, are on no type list. With type shards and no `full` they are out of reach of any query. Either the registry places them under a reserved type, or they are served by identifier only.
6. *Co-location.* A query over several types needs them on one node. Templates are published and declare their types, so the combinations in use are known and placement can be computed from them. A type may sit on many nodes, at the cost of copies. The structural types sit on all of them.
7. *Types are chosen by publishers.* Semantic shards are as good as the typing. Too coarse, and one generic type collects a billion unrelated records. Too fine, and there are millions of types: today there are 1,502 types for 102,500 nanopublications, 489 of them with a single member. So small types have to share stores, as a repository per type costs 4.3 MB before any data. Anyone can also attach a popular type to their own nanopublications. Per-list caps, quotas and loading only the lists of approved keys keep that from affecting anyone else.
8. *Operations.* With hundreds of nodes a failed store is a daily event. A node has to rebuild itself from a checkpoint (4.11). Loading 10 million takes ten days at today's rate and nine hours at 300 per second, and copying a store takes about an hour. Eleven corruption events on three nodes in three weeks, as in 2026, cannot be multiplied by a hundred and handled by hand. Store stability and automatic rebuild limit the dynamic part before money does.

**What has to be built.** Registries can already restrict coverage by type, reject what they do not cover, and sync only the covered lists. Query inherits the coverage of its registry. Missing are:

1. *Scope declarations* in query templates (types and quantity), and their enforcement in Query.
2. *List caps* in the loader, with the cut lists reported.
3. *A published coverage map.* Each node states the types it carries, with counts and caps, in a service description nanopublication. The Monitor computes the number of nodes per type and reports types with too few.
4. *Placement.* Inside one operator's fleet, a controller assigns types to nodes from the declared scopes and rebalances as types grow. Across operators, coverage is declared, and the map shows what is missing.
5. *Routing by coverage.* The Router sends a publication to a registry that covers its types, and a query to a node that carries its scope. Today it picks any healthy instance.
6. *The type direction in the registry API,* as described above.
7. *Structural types on every node,* so that the joins nearly every template makes against templates, spaces, trust, definitions and invalidations stay local.
8. *Node replacement without a person,* by cloning from a checkpoint (4.11).

**Durability comes from the static plane.** Once content is sealed, a dynamic node is a derived copy that can be rebuilt. Replicas of a type then serve availability and query capacity, and two may be enough, which lowers every figure in the table by a third. Content that is published live and not yet sealed still needs three registries.

### 4.11 Cloning instead of replaying

A new registry builds its state by fetching nanopublications from its peers, and a new Query instance replays its registry's stream and derives every repository again. Both are replays of history, and both grow with the content.

**T14. Bringing up one node: replaying history or copying a checkpoint**

| Node | Nanopublications | Store size | Replay at today's rate | Replay at 300 per second | Copy at 1 Gbit/s | at 10 Gbit/s | Verify all signatures (16 threads) |
|---|---:|---:|---:|---:|---:|---:|---:|
| Query node today | 109 thousand | 15 GB | 3 h | 6 min | 2 min | 0 min | 0 min |
| Query node, today's layout, full | 11 million | 250 GB | 11 days | 11 h | 38 min | 4 min | 40 min |
| Query node, type shards, RDF4J, full | 28 million | 250 GB | 27 days | 26 h | 38 min | 4 min | 2 h |
| Query node, type shards, engine at Wikidata scale, full | 277 million | 226 GB | 268 days | 11 days | 34 min | 3 min | 16 h |
| Registry today | 109 thousand | 1.1 GB | 36 min | 6 min | 0 min | 0 min | 0 min |
| Registry, 10 million | 10 million | 100 GB | 2 days | 9 h | 15 min | 2 min | 35 min |
| Registry, 100 million | 100 million | 1.0 TB | 23 days | 4 days | 3 h | 15 min | 6 h |

A full node of the kind section 4.10 counts on takes between eleven days and nine months to replay at today's rate, between half a day and eleven days at the improved rate, and about half an hour to copy. The registry sizes rest on the assumed 10 KB per nanopublication in MongoDB, and the last Query row on QLever's index size. At these sizes a clone feature is a requirement. Node replacement, rebalancing and adding read capacity all depend on it.

**Why a plain copy does not work today.**

1. *Identity travels with the content.* A registry's database holds its setup id and its load counter. A restored dump is a twin with the same id and the same counters. Once both twins accept publications, the same counter means different nanopublications on each, and a Query instance that moves between them misses or repeats entries without noticing. A fresh registry avoids this by minting a new setup id, and then every Query instance behind it treats it as a reset and reloads from zero. The 2026 migration plan preferred the dump for this reason. In the end both stores were rebuilt, which took half an hour for a registry of 89,000.
2. *Position is one number per instance.* Query stores the load counter of the one registry it follows. A copied Query store is usable only behind that registry or its twin.
3. *A running store cannot be copied safely, and a copy cannot be checked.* RDF4J holds recent writes in memory until told to write them out, so the files of a running store are behind. The same migration plan says not to copy the LMDB stores at all, since they had held silent defects and a rebuild was the only way to be sure.

**Four pieces make it work.**

1. *A checkpoint.* A consistent state at a stated position, written as files. The registry's lists and nanopublication store are append-only, so a consistent export needs no lock: record the tail position of every list when the checkpoint starts, export up to those positions, and add the trust state by its hash. Query pauses its loader at a counter, has RDF4J write everything out (the flush script and the shutdown guard in the admin repository do this for the large repositories), copies the repository directories and resumes. With a filesystem snapshot the pause is seconds. Queries keep running throughout.
2. *Lineage.* An instance restored from a checkpoint mints a new setup id, keeps the counter numbering up to the checkpoint, and states which setup id and counter it was cloned at. A follower positioned at or below that point on any instance of the same lineage keeps its position. A follower above it falls back to the clone point and reads the tail again, which is harmless because the loader skips what it already has. Databases solve the same problem this way: PostgreSQL restores a base backup, replays the log, and starts a new timeline id at the fork. Lineage also gives Query what it lacks today, the ability to change registries without a reload.
3. *The existing sync for the tail.* The clone inherits the source's positions on its peers, which are valid because its content equals the source's at the checkpoint, and gets a position on the source itself. From its first cycle it asks each peer for what came after. Nothing new is needed here.
4. *Verification.* Every Query repository already records the count and the XOR checksum of the nanopublications it holds, computed with the same function as the registry's list checksums. The set of nanopublications in a cloned type repository can therefore be compared with the registry's lists for that type per type, once the registry API has the direction from a type to its keys (4.10). That confirms which nanopublications are present. A background pass over all signatures (last column of T14) confirms that each one is genuine. Neither confirms that the derived triples and indexes are intact. For that, each repository should also record an order-independent checksum over its quads. Of the 33 kinds of triples Query derives, only three depend on the instance (load number, load checksum and load timestamp), so with those left out two nodes holding the same nanopublications must arrive at the same value. A clone is then checked by one scan of the store against a node built by someone else, at the cost of reading the data and not of deriving it again.

**Two forms of checkpoint.**

| | Exchange form | Store image |
|---|---|---|
| Content | The files of the static plane: the registry file of the read-only mode, per type | A MongoDB dump or snapshot, RDF4J repository directories |
| Start-up | Opened in place, or bulk-loaded | Copied and opened |
| Valid for | Any version and any engine that reads the format | The same engine build, configuration and Query version |
| Store defects | Not carried over | Carried over |
| Next checkpoint | Shares everything but the list tails | A new full copy |
| Use | The canonical checkpoint; the fallback when versions differ or the source is unknown | The normal way to bring up a node, within a fleet and between operators, taken from a node that passed the probe |

A checkpoint of a dynamic part of 3 billion nanopublications takes 4.2 TB in exchange form, about €27 per month on object storage, and 27 TB as RDF4J store images, about €176 per month.

**The unit is the type.** With shards by type, a checkpoint is one type's lists from a registry and one type's repository from Query. To carry a type on a node means to fetch its checkpoint, open it and follow the tail. This is one operation for a new node, a replacement after a failure, a rebalancing move and added read capacity. It requires that each repository records its own position. Today there is one position for the whole instance, in the admin repository. A node assembled from checkpoints of different age then restarts its stream at the lowest of its positions, and the loader's check per repository skips the rest. Per-type streams from the registry (4.10) remove that re-reading.

**Clone and seal are one mechanism.** A per-type checkpoint in exchange form is a segment that has not been declared final. Sealing (4.3) declares the newest checkpoint final and lets the live store drop it. Cloning opens it and continues writing behind it. A registry can also offer SPARQL on it (4.9). One format and one builder serve all of these, and the builder on the read-only branch already turns a live registry into such a file.

**A registry clone needs no import.** In the store planned in section 5.1, MongoDB holds the hot window and the read-only reader serves sealed files in the same process. A new registry then fetches the checkpoint files and serves them at once, and its MongoDB only takes what arrives afterwards.

**What remains of syncing.** Following the tail, with the mechanism that exists. Cloning does not remove it. It reduces the replayed history from everything to the minutes since the last checkpoint. A static registry has no tail, and there the copy is the whole of replication (4.5).

**Cautions.**

- *A store image copies defects.* Eleven corruption events on three nodes in three weeks is the record of this engine. Images are taken only from nodes that pass the probe, and the exchange form is kept as the fallback.
- *Copies of one image agree with each other.* The fleet agreement check loses its meaning when every node descends from the same image. At least one node per type should be built from the exchange form by a different builder.
- *Images are tied to versions.* Query changes the triples it derives between releases, and an image has to state the Query version and engine build it was made with.
- *Removal.* A removed nanopublication lives on in old checkpoints. Their retention has to follow the removal procedure of section 4.14.
- *Between operators.* Cloning across operators is the normal case and not an exception. Nanopublications verify themselves, a registry computes its trust state from its own setting whatever it was cloned from, and neither store holds private keys. On the query side, clients already accept the answers of whichever instance the Router sends them to, so they trust every operator in the network today. What a cross-operator clone needs: the checkpoint is published as files with a manifest signed by the operator, stating position, versions, counts and checksums; it leaves out the instance's identity and peer state; and the receiver runs the checks above. One difference to a clone inside a fleet remains. LMDB and MongoDB data files are read by native code that is not written to withstand a deliberately malformed file, so store images are accepted from operators the receiver already lists as peers, and from anyone else only the exchange form.

### 4.12 Bytes per record

Three choices set the storage bill, in this order.

**Serialized blobs.** The registry file stores each nanopublication three times: as indexed quads, as TriG text and as base64 Jelly, so that serving needs no re-serialization. An estimate from the uncompressed sizes puts the blobs at about four fifths of the 394 MB file. The alternatives are to serialize from the quads on request (the hash is defined over the RDF, so any faithful serialization verifies), or to keep the compressed Jelly source next to the segment with an offset index and read records from it by range. The second makes the canonical archive double as the content store, at 0.55 KB per nanopublication, and is what the central estimate assumes. The exact split needs one measurement: build the content, metadata and blob graphs separately.

**Signatures.** An RSA-2048 signature is 256 bytes of incompressible data per nanopublication, half of the compressed record. Ed25519 signatures are 64 bytes.

**T9. Signatures**

| Nanopublications | RSA-2048 signatures | Ed25519 signatures | Sign, RSA, 32 cores | Sign, Ed25519, 32 cores | Verify, RSA, 32 cores | Verify, Ed25519, 32 cores |
|---|---:|---:|---:|---:|---:|---:|
| 300 million | 77 GB | 19 GB | 1 h | 5 min | 2 min | 16 min |
| 30 billion | 7.7 TB | 1.9 TB | 5 days | 8 h | 3 h | 26 h |

At 30 billion, RSA signatures alone are 7.7 TB per copy, against 1.9 TB for Ed25519. The saving is about 14% of the central storage estimate. Signing is 16 times faster with Ed25519 (34,000 against 2,100 per second and core), which matters to a publisher signing billions of records. Verification is the other way round: RSA-2048 verifies at about 89,000 per second and core, Ed25519 at 10,000 to 31,000 depending on the library. Neither is a bottleneck. The measured build verifies 295 nanopublications per second and thread, so parsing, normalization and hashing take over 99% of the time, and that is where optimization pays.

Supporting Ed25519 next to RSA is worth doing before the first billion-record dataset is signed, since a published signature is permanent. It is a moderate gain, not a precondition.

**Granularity.** A nanopublication with one assertion triple carries about 15 structural and metadata quads. Whether a dataset is cut into one record per statement or one per entity changes the count by ten and the bytes per assertion triple by about as much. The limits of 1,200 triples and 1 MB per nanopublication leave room for either. The choice should follow what a reader wants to cite, retract or endorse as a unit.

### 4.13 Quotas and who pays

Quotas on the live plane stay as they are: derived from trust, capped at 100,000 per account by default, with an hourly allowance for unapproved keys. Two additions matter at scale. Quotas must also apply to what a registry loads from peers (issue #221), or a permissive registry becomes the way around them. And a quota should count hot nanopublications, so that sealing returns capacity.

Bulk publishing does not go through quotas at all. A publisher builds segments, hosts or pays for at least one copy, and publishes manifests. Mirrors decide by their own coverage policy whether to carry them. This is the arrangement the ecosystem paper anticipates: open registries for the long tail, and dedicated capacity paid for by whoever needs it. Section 7.8 gives the price a publisher would face.

**Pay as you go.** Nobody funds the network as a whole. An operator pays for the clusters it covers and for the share of them it keeps loaded (7.3). Whoever needs a domain funds nodes for it, whoever needs it fully loaded funds large nodes, and occasional readers use other operators' nodes within rate limits. Three things have no natural payer under this rule and need an explicit arrangement:

- *The commons.* Router, Monitor, coverage map, identifier resolver and metadata index serve everyone. In hardware they cost about €100 per month at 30 billion. They need an owner more than they need money.
- *Clusters nobody covers.* Content lives as long as some operator carries it. A publisher who pays for one static copy keeps bulk content available, and an archive of last resort (a library, or Zenodo for selected datasets) covers the case where the publisher disappears.
- *The long tail.* People publishing a few records through an open registry pay nothing. Quotas bound what that costs the operators who run those registries.

### 4.14 Deletion

Registries may have to remove a nanopublication for legal reasons. In a sealed file that means rebuilding the segment without it and publishing a new manifest that supersedes the old one, together with a signed removal notice, so that mirrors follow and the list checksums stay explainable. Small segments keep this cheap. A removal list that serving nodes consult closes the gap until the rebuild. The privacy notes in the admin repository should be extended to cover mirrors operated by third parties, since a mirror in another jurisdiction is a data transfer.

### 4.15 Operations

The two months of query-layer incidents came from mutable stores, unclean shutdowns and reload times. A static node has none of these: no database, no write path, no recovery, and a restart is instant. Replacing a failed static node means copying files. The live plane keeps its operational weight, but bounded, since its stores stay small enough to reload in minutes.

## 5. Target architecture by component

### 5.1 Live plane

| Component | Today | Needed for 10 million hot and 100 per second |
|---|---|---|
| Registry publish path | One ordered queue, 16 per second | Batch endpoint taking a Jelly stream; parallel verification; one bulk write per batch. Several branches already point this way (`perf/batched-list-entry-writer`, `perf/eliminate-redundant-signature-verification`). |
| Registry store | MongoDB, everything | MongoDB for the hot window and the mutable state; sealing into segments; serving segments through the read-only reader, in one process |
| Peer sync | Per entry | Per entry for the hot window, per segment below it |
| Quotas | At POST only | Also at peer sync (#221); counted on the hot window |
| Trust | Periodic, with many transactions in the final steps (#102) | Unchanged in design. Split the trust state hash as in #223 so that static content does not perturb it. |
| Query load | 12 per second, about 1,600 quads per second | Larger transactions into fewer repositories. RDF4J's LMDB store has been reported to load about 50,000 quads per second, so a few hundred nanopublications per second is a fair target. |
| Query repositories | 2,800, one per key and type, plus `full` | Dedicated repositories only above a threshold; shared buckets below; no `full`, except on restricted instances |
| Coverage | By type and by agent in the registry; all production nodes cover everything | Partial coverage in production, declared in clusters of types; coverage published as a service description, with counts and caps; placement within a fleet from the scopes that templates declare |
| Query scope | The endpoint a template names; `full` in half of them | Declared types and quantity per template; list caps in the loader; cut lists reported |
| Registry API by type | From a key to its types | Also from a type to its keys, with list lengths and checksums, and one stream per type |
| Routing | The Router redirects to any healthy instance | By coverage, for publishing and for repository requests |
| Node replacement | By hand: wipe and reload | Clone from a published checkpoint per type, then follow the tail (4.11) |
| Instance identity and position | Setup id and load counter; a copied database is an identical twin; Query keeps one position for the whole instance | Lineage: a clone gets a new setup id and states the setup id and counter it was cloned at; a position per repository in Query |
| Query sources and coverage | One registry, one load counter, coverage inherited from that registry | Several sources (a live registry and static registries), a cursor per source, and a load policy of its own per cluster and type, with list caps (4.9) |
| Query engine | RDF4J with LMDB | Unchanged. Query answers only from what it has loaded. |

### 5.2 Static plane

| Component | State | Work |
|---|---|---|
| Read-only registry | Branch `202-read-only-rete-mode`: builder, validator, SPARQL-backed reader, parity tests against MongoDB | Move from rete 0.5 to a current version with the quad index (its changelog reports files up to a quarter smaller); settle the blob question; serve many segments from one process |
| Segment builder | `scripts/build-readonly.sh`, one thread | Parallel verification; Jelly source with offset index; manifest output; resumable |
| Manifest and availability vocabulary | None | Define in the `npx:` and `npa:` namespaces; templates |
| Mirror tool | None | Fetch by manifest, verify, sample, publish availability |
| SPARQL on segments | The read-only registry reads its file through a rete SPARQL endpoint. rete can federate files. | Expose the endpoint at the registry, per segment and per dataset, with limits, and describe its scope in the manifest |
| Checkpoints | None. Stores are rebuilt by replay. | Per-type checkpoints of live state in the segment format, from the same builder; store images between nodes on the same versions; a content checksum per repository (4.11) |
| Query's admin graph in segments | Not in the registry file | Optional, if templates should run on segment endpoints. Not needed for the plan. |
| Resolver, catalog, metadata index | Router redirects to a healthy instance | Build from manifests; serve from the Router |
| Invalidation overlay | Flag set at build time only | Overlay table and its deltas; applied by registry and query readers |
| Monitor | Per-service health | Per-segment replica counts, checksum agreement between mirrors, nodes per dynamic slice |

### 5.3 Dependence on rete

The static plane is defined by a contract: the registry read API and SPARQL over a sealed file. rete is the implementation that exists and fits, with measured numbers. It is also experimental, maintained by one person, and its documentation says files may need rebuilding until 1.0. Three precautions follow. Keep the canonical source and treat rete files as rebuildable. Keep the reader interface on the branch (`RegistryReader`) free of rete-specific assumptions, so that HDT, a QLever index or sorted Jelly with a sidecar index could stand in. And get involved upstream on the points this plan depends on: 64-bit term identifiers in the reader, serving many files from one process, and memory-bounded builds at segment size.

## 6. Calculations

### 6.1 Storage

**T2. Storage of one full replica of the static plane**

| Nanopublications | Raw Jelly | Low (lean) | Central (mix) | High (mix, blobs in file) |
|---|---:|---:|---:|---:|
| 109 thousand | 268 MB | 76 MB | 153 MB | 418 MB |
| 10 million | 25 GB | 7.0 GB | 14 GB | 38 GB |
| 100 million | 246 GB | 70 GB | 140 GB | 384 GB |
| 300 million | 738 GB | 210 GB | 420 GB | 1.2 TB |
| 1 billion | 2.5 TB | 700 GB | 1.4 TB | 3.8 TB |
| 3 billion | 7.4 TB | 2.1 TB | 4.2 TB | 12 TB |
| 10 billion | 25 TB | 7.0 TB | 14 TB | 38 TB |
| 30 billion | 74 TB | 21 TB | 42 TB | 115 TB |
| 100 billion | 246 TB | 70 TB | 140 TB | 384 TB |

The three columns are: lean records with Ed25519 (0.3 KB archive plus 0.4 KB index); today's mix with the Jelly source as content store (0.6 plus 0.8 KB); and today's mix with blobs kept inside the file as on the branch (3.84 KB, measured). The index figures for the first two are estimates, bracketed by the measured 233 bytes for unsigned first-generation records and the measured 3.84 KB with blobs.

### 6.2 Building and moving

**T4. Building and moving static segments**

| Nanopublications | Verify (32 threads) | rete build (8 parallel) | Copy a replica at 1 Gbit/s | at 10 Gbit/s | Per-nanopub stream, one connection |
|---|---:|---:|---:|---:|---:|
| 10 million | 18 min | 4 min | 2 min | 0 min | 43 min |
| 100 million | 3 h | 37 min | 21 min | 2 min | 7 h |
| 300 million | 9 h | 2 h | 1 h | 6 min | 21 h |
| 1 billion | 29 h | 6 h | 4 h | 21 min | 3 days |
| 3 billion | 4 days | 19 h | 11 h | 1 h | 9 days |
| 10 billion | 12 days | 3 days | 35 h | 4 h | 30 days |
| 30 billion | 37 days | 8 days | 4 days | 11 h | 89 days |
| 100 billion | 123 days | 26 days | 15 days | 35 h | 297 days |

Verification runs at the measured single-thread rate times 32, with no optimization assumed. Everything on the static path is parallel across segments, so these times fall with more machines. The last column shows why replication has to be by file: the same data as a stream of individual nanopublications takes twenty times longer than copying it.

### 6.3 Memory and processes

The read-only registry and its rete sidecar used 1.2 GB and 1.0 GB of memory for one 394 MB file. rete's documentation reports queries on a 52 GB file inside a 2 GB container using a 256 MB block cache, so memory does not have to grow with file size. Whether one process can serve several thousand segments within a fixed memory budget is not yet measured and decides how many serving nodes a replica needs.

## 7. Costs

The network has no central budget. Each operator pays for the clusters it covers and for what it keeps loaded (4.10, 4.13). The figures that matter are therefore the cost per million nanopublications (7.2) and the cost per operator (7.3). Section 7.4 adds up what all operators together would spend under an assumed number of copies. Nobody receives that bill.

All prices are monthly list prices without VAT, read from the providers' pages on 25 November 2026. US dollar prices are taken at par with the euro, which is accurate enough next to the other uncertainties.

### 7.1 Unit prices

| Item | Price | Per TB-month |
|---|---:|---:|
| Hetzner AX41: 6 cores, 64 GB, 2 × 512 GB NVMe (the class of today's hosts) | €59 | |
| Hetzner AX102: 16 cores, 128 GB, 2 × 1.92 TB NVMe | €259 | |
| Hetzner AX162 base: 48 cores, 128 GB | €614 | |
| Hetzner SX65: 4 × 22 TB HDD, 2 × 1 TB NVMe, 64 GB | from €84 | €1.27 usable (RAID 5) |
| Hetzner SX135: 8 × 22 TB HDD, 2 × 1.92 TB NVMe, 128 GB | from €289 | €2.19 usable (RAID 6) |
| Datacentre NVMe as a server add-on, 7.68 TB / 15.36 TB | €170 / €320 | €22 / €21 |
| Hetzner Object Storage | | €6.47, egress €1 per TB |
| Backblaze B2 / Wasabi | | $6.95 / $7.99, egress free within limits |
| OVHcloud Object Storage, one zone | | about €7, egress free |
| Cloudflare R2 | | $15, egress free |
| AWS S3 Standard, Frankfurt | | $24.50, egress $50 to $90 per TB |

Hardware became much more expensive in 2026. Hetzner raised prices in April and roughly doubled them for new orders in June. Enterprise SSD prices rose about sixfold within a year, to roughly $750 per TB, while large HDDs sit near $40 per TB. Flash now costs about ten times as much to rent and nearly twenty times as much to buy as disk. The design should therefore keep the bulk of every replica on disk or object storage and reserve NVMe for the live plane, the global indexes and caches. The model uses €22 per TB for NVMe, €2 for disk and €6.50 for object storage.

The four hosts of today's fleet are not priced in the admin notes. At the list prices above they come to roughly €240 to €350 per month.

### 7.2 What a million nanopublications cost to carry

**T15. Carrying one copy of a million nanopublications for a year**

| Way of holding | Per nanopublication | Per million and year | Carried for €100 per month |
|---|---:|---:|---:|
| Not held, only listed: an entry in the global indexes (NVMe) | 72 B | €0.02 | 63 billion |
| Segment files on a disk server | 1.4 KB | €0.03 | 36 billion |
| Segment files on object storage | 1.4 KB | €0.11 | 11 billion |
| Segment files on NVMe, for SPARQL at the registry | 1.4 KB | €0.37 | 3.2 billion |
| Live in a registry (MongoDB), node filled to its disks: 190 million | 10 KB | €16 | 74 million |
| Live in a registry (MongoDB), node kept at 10 million | 10 KB | €71 | 17 million |
| Loaded in Query. Today's layout: `full`, key and type repositories, RDF4J | 175 quads | €272 | 4.4 million |
| Loaded in Query. Type shards, one copy per type, RDF4J | 72 quads | €112 | 11 million |
| Loaded in Query. Type shards, one copy per type, engine at Wikidata scale | 72 quads | €27 | 45 million |

One copy of a million nanopublications costs 3 to 37 cents per year as static files, €16 to €71 live in a registry and €27 to €272 loaded in a query store. Between static and loaded lies a factor of 70 to several thousand. An operator's bill is therefore set by what it keeps live and what it loads, and hardly by what it covers.

Three qualifications apply. The prices come in steps: the smallest storage server is €84 per month and holds 47 billion nanopublications, and the smallest useful query node is €59 to €259. Below one node's worth the unit price does not apply and the step does. The two registry rows span an untested range: 10 million per node is the hot-window target, and 190 million is what fits on the disks of a larger node at an assumed 10 KB per nanopublication. And none of the rows includes people (7.7).

### 7.3 What an operator pays

An operator's bill follows from the unit costs and from two choices: which clusters to cover, and how much of them to keep loaded. Take one operator that covers a domain of a billion nanopublications, next to trust and core, at the prices of table T15 and with the cheaper of the two type-shard engines:

- A registry that keeps and serves all of it as segments: about €60 per month on disk, and about €90 on NVMe if the segments are queried often.
- Query with 1% loaded: about €260 per month, one node.
- Query with 10% loaded: about €610 per month.
- Query with everything loaded: about €2,500 per month, four nodes.

Three things follow.

- *Registry coverage is cheap.* Keeping several billion nanopublications as segments costs under €100 per month, so registries can cover broadly and copies should be plentiful.
- *The loaded share is what costs.* Between 1% and everything loaded lies a factor of ten for the same coverage.
- *Heavy users fund big nodes.* An operator that wants a whole domain loaded pays for that choice, and nobody else does.

Per operator the fixed cost is a person who runs the node, and it is larger than the hardware cost of a registry or of a lightly loaded Query node. Pay as you go therefore works for small operators only if a node runs unattended: brought up by clone (4.11), repaired by rebuild, and static wherever possible (4.15).

### 7.4 The network as a whole

For orientation, this is the sum over all operators if every nanopublication is held three times and little is loaded.

**T6. Monthly infrastructure cost**

| Nanopublications | Stored, 3 replicas | Static storage | Global indexes | Live plane and front ends | Total per month | Per million per year |
|---|---:|---:|---:|---:|---:|---:|
| 109 thousand | 458 MB | €0.00 | €0.00 | €236 | €236 | €25,988 |
| 10 million | 42 GB | €0.43 | €0.03 | €236 | €236 | €284 |
| 100 million | 420 GB | €4.27 | €0.32 | €236 | €241 | €29 |
| 300 million | 1.3 TB | €13 | €0.95 | €236 | €250 | €9.99 |
| 1 billion | 4.2 TB | €43 | €3.17 | €1.0k | €1.1k | €13 |
| 3 billion | 13 TB | €128 | €9.50 | €1.0k | €1.2k | €4.60 |
| 10 billion | 42 TB | €427 | €32 | €1.8k | €2.2k | €2.70 |
| 30 billion | 126 TB | €1.3k | €95 | €1.8k | €3.2k | €1.27 |
| 100 billion | 420 TB | €4.3k | €317 | €1.8k | €6.4k | €0.77 |

What the columns contain:

- **Static storage**: three replicas of 1.4 KB per nanopublication, one on NVMe for fast serving, one on a disk server, one on object storage for durability and public range requests.
- **Global indexes**: identifier resolver and metadata index (72 bytes per nanopublication), two copies on NVMe.
- **Live plane and front ends**: four hosts of today's class throughout. From one billion on, three AX102-class nodes for the hot window, sealing and segment query front ends, and from ten billion on, six. This step is an assumption about load, and it is the least certain column.

What they do not contain: people (7.7), the cost of producing the nanopublications (2.3), a dynamic share beyond the structural types and a small hot window (table T13 in section 4.10 gives that cost, which at a share of 10% is larger than everything in this table), and query load beyond today's. Query compute grows with the number of users and applications, not with the number of nanopublications. Today RDF4J needs 4.7 cores per node for about 100 API calls per minute across the fleet. Each additional front end is €259 to €614 per month.

The cost per nanopublication falls from 2.6 euro cents per year today to about a millionth of a euro at 30 billion. Until about one billion, the bill is the fixed cost of running any network at all.

### 7.5 Sensitivity

**T7. Sensitivity of the monthly total at 30 billion**

| Case | Stored | Static storage per month | Total per month |
|---|---:|---:|---:|
| Central: today's mix, 1.4 KB, replicas on NVMe, HDD and object storage | 126 TB | €1.3k | €3.2k |
| Lean records, 0.7 KB | 63 TB | €640 | €2.5k |
| Blobs kept in the file, 3.84 KB | 346 TB | €3.5k | €5.4k |
| Merged query snapshots as well, 1.9 KB | 171 TB | €1.7k | €3.6k |
| Five replicas (two NVMe, two HDD, one object) | 210 TB | €2.3k | €4.2k |
| All three replicas on NVMe | 126 TB | €2.8k | €4.7k |
| All three replicas on object storage | 126 TB | €819 | €2.7k |
| All three on hyperscaler object storage at €23 per TB, before egress | 126 TB | €2.9k | €4.8k |
| Central, plus one global SPARQL snapshot node (31 TB NVMe) | 126 TB | €1.3k | €4.5k |

Every variant stays between €2,500 and €5,400 per month at 30 billion. The blob decision is the largest single factor. The last row adds the one thing section 4.8 leaves to others, an analytical index over everything:

**T11. One analytical SPARQL index over everything (QLever-class, extrapolated from UniProt)**

| Nanopublications | Quads | Index | NVMe incl. build space | Build time | Per month |
|---|---:|---:|---:|---:|---:|
| 300 million | 12 billion | 134 GB | 308 GB | 2 h | €621 |
| 3 billion | 118 billion | 1.3 TB | 3.1 TB | 20 h | €682 |
| 30 billion | 1.2 trillion | 13 TB | 31 TB | 8 days | €1.3k |

This extrapolates from one published data point: QLever indexes UniProt (266 billion triples) into about 3 TB in about 40 hours on one desktop-class machine, using about 7 TB during the build. Its authors report that it has handled over a trillion triples on a single machine. Whether it does so for quads in several hundred million named graphs has to be tested. If it does, a global SPARQL snapshot rebuilt weekly is affordable as a community service, with query time limits, at 30 billion nanopublications.

### 7.6 The current stack at the same sizes

For comparison, today's architecture extrapolated with the sizes of table T3, three registries and three query nodes, all on NVMe as they are now:

| Nanopublications | NVMe needed | Storage per month | Initial load of a query node |
|---|---:|---:|---:|
| 10 million | 1 TB | €21 | 10 days |
| 300 million | 29 TB | €630 | 289 days |
| 30 billion | 2.9 PB | €63,000 | 79 years |

Money is not what stops the current stack at 300 million. The load time is. At 30 billion it is both, and the storage alone is twenty times the cost of the entire two-plane design.

### 7.7 People

No personnel costs are recorded in the sources for this document, so the figures here are placeholders to be replaced. With a fully loaded cost of €120,000 to €180,000 per engineer and year, the work in section 8 (two to three engineers in year one, three to five with operations in years two and three) costs €250,000 to €900,000 per year. Infrastructure costs €3,000 per year at 300 million and €30,000 to €65,000 per year at 30 billion. People are 85 to 99% of the total in every scenario.

Two conclusions follow. Design choices should be judged by the engineering and operating effort they save before the hardware they save, which is the strongest argument for static files: the two months of query-layer incidents in 2026 cost more in engineering time than several years of hosting. And the affordable size of the network is not limited by hosting budgets. A funder deciding on this plan is deciding on a team.

### 7.8 What a bulk publisher pays

**T10. What a bulk publisher pays for storage, three replicas**

| Record profile | 1 million, per year | 100 million, per year | 1 billion, per year | 1 billion, ten years |
|---|---:|---:|---:|---:|
| Lean, 0.7 KB | €0.256 | €26 | €256 | €2.6k |
| Today's mix, 1.4 KB | €0.512 | €51 | €512 | €5.1k |
| Today's mix with blobs, 3.84 KB | €1.405 | €141 | €1.4k | €14k |

This is storage on three replicas at the prices above, without margin and without serving. A billion lean records cost about €260 per year to keep in triplicate, and about €2,600 for ten years. A one-off publication fee that covers a decade of storage is therefore realistic at around €3 to €15 per million nanopublications, and it could fund mirrors run by others.

### 7.9 Owning hardware, bandwidth, archives

- **Owning.** The disks for one 42 TB replica cost about €2,000 at street prices, with redundancy. A university library or computing centre can hold a full replica of 30 billion nanopublications on one storage server. The same replica on enterprise NVMe would cost over €30,000 in drives.
- **Bandwidth.** Dedicated servers at Hetzner include unmetered traffic at 1 Gbit/s, which is about 300 TB per month. Egress from Hetzner Object Storage is €1 per TB, and free at R2, OVHcloud and (within limits) B2. At a hyperscaler, one full copy of a 42 TB replica leaving the cloud costs about $3,600 in egress fees, which rules them out for public mirrors.
- **Archives.** Zenodo accepts 50 GB and 100 files per record by default, and up to 200 GB on request. That fits selected datasets as an independent archive path (35 segments of 1.4 GB per record) but not the whole static plane, which would need about 850 records at 30 billion.
- **Crawlers.** Open range requests on large files are an obvious target, and crawlers already dominate front-end traffic. Whole segments should be cacheable at a CDN (512 MB is the object limit on Cloudflare's standard plans), and the serving nodes need per-client limits from the start.

## 8. Roadmap

### 8.1 Core tasks

The work falls into four tracks. Sizes are rough estimates for one engineer and are not based on recorded effort: S is a few weeks, M one to three months, L three to six months.

**Track A: scaling out by cluster.** This is what makes operators with partial coverage possible. It works with today's stores and does not depend on the static plane.

| | Task | Starting point | Work | Size |
|---|---|---|---|:-:|
| A1 | Type clusters and declared coverage | Registries can restrict coverage by type and agent. All production nodes cover everything. | Cluster definitions as nanopublications. Coverage published as a service description. A coverage map. A reserved type for nanopublications without one. | M |
| A2 | Routing by coverage | The Router redirects to any healthy instance. | Publications go to a registry that covers their types, and repository requests to a node that carries the scope. Identifier resolver. | M |
| A3 | Query independent of one registry | Query follows one registry by its load counter and loads all it has. | A load policy per cluster, with list caps. Several registries as sources, static ones included. A position per repository. Structural types always loaded. Loading by reference. | L |
| A4 | Declared scopes, and the end of `full` | 391 of 761 templates target `full`. | Scope declaration in templates. List caps in the loader, with cut lists reported. The registry API from a type to its keys. Migration of templates and of Nanodash. | L |
| A5 | Clone, and nodes that run unattended | A node is wiped and reloaded by hand. A copied registry is a twin, a fresh one resets its followers. | Checkpoints per cluster. Lineage. A content checksum per repository. Automatic rebuild. Packaging that an outside operator can deploy. | L |

**Track B: the cheap level.** This is what makes billions affordable to hold and gives durability.

| | Task | Starting point | Work | Size |
|---|---|---|---|:-:|
| B1 | Static registry in production | Branch `202-read-only-rete-mode`: builder, validator, reader, parity tests, on rete 0.5. | Current rete. Decision on blobs. Segment and manifest specification. Many segments in one process. Parallel builder. | L |
| B2 | Sealing | MongoDB holds everything. | A registry that serves its live store and its segments in one process, seals old content, and drops it once enough holders exist. | L |
| B3 | SPARQL on segments at the registry | The read-only registry already reads its file through a SPARQL endpoint. | Expose it per segment and per dataset, with time and result limits. Scope described in the manifest. Federation over a dataset's segments, or a merged snapshot. | M |
| B4 | Mirrors and their monitoring | Monitor reports health per service. | Mirror tool. Availability statements. Holders per segment and per cluster. | M |

**Track C: rate and record format.**

| | Task | Starting point | Work | Size |
|---|---|---|---|:-:|
| C1 | Registry publish path | 16 per second through one ordered queue. Branches for batched writes exist. | Batch endpoint taking a stream. Parallel verification. Quotas at peer sync (#221). | M |
| C2 | Query load path | 12 per second into 2,800 repositories. | Larger transactions. Shared repositories for small types. Target 300 per second. | M |
| C3 | Ed25519 and a lean profile for bulk data | RSA-2048 only. | Support in nanopub-java, Registry and Query. Has to be in place before the first large dataset is signed. | M |

**Track D: finding things without `full`.**

| | Task | Starting point | Work | Size |
|---|---|---|---|:-:|
| D1 | Metadata index and invalidation overlay | Query's `meta` repository, complete on every node. | Indexes fed from the registries, served next to the Router. | M |
| D2 | Index from terms to nanopublications and types | `full` and `text`. | A design first. About 190 templates depend on it. | open |

Together this is on the order of three engineer-years, without the term index and without operations.

**How the tracks relate.** A and B are independent and can run in parallel. If rete stalls, scaling out by cluster still happens. If clusters take longer to agree on, the static registry still makes bulk content cheap. They meet in two places: a static registry of B1 is one of the sources that Query loads from in A3, and the checkpoint of A5 is the segment of B1 before it is sealed. Query itself does not change its way of answering in any of this. The shortest path to a second operator with partial coverage is A1, A2 and A3, about eight months of work. A4 can follow later, because a node with partial coverage can keep a `full` repository over what it covers in the meantime.

**What is needed besides code.**

- *Decisions that block tasks:* blobs (B1), cluster definitions (A1), the form of scope declarations and the cut rule (A4), whose checkpoints a node accepts (A5). All are in section 10.
- *Measurements,* each a matter of days: the split of the registry file, MongoDB bytes per nanopublication and a registry at 100 million, quads per RDF4J node, a thousand segments in one process, and the bridge mechanism of section 4.9.
- *Content:* the first-generation corpus as the first static dataset, then one bulk dataset with a named consumer.
- *A second operator with partial coverage.* This is the test of the whole model, and it should happen in 2027 and not after everything else is built.
- *Owners* for the Router, the Monitor, the coverage map and the indexes, and a process for defining clusters.

### 8.2 Year one: to 300 million by the end of 2027

| Quarter | Target | Work | Exit criteria |
|---|---:|---|---|
| 2026 Q4 to 2027 Q1 | 10 million | B1: merge read-only mode on current rete, decide on blobs and measure, segment and manifest specification, parallel builder. Republish the first-generation corpus as the first static registry, with three mirrors. A1: cluster definitions and declared coverage. C3: Ed25519 in nanopub-java and the registry. | A static registry of 10 million validates completely. A new mirror is serving within one hour of starting. Bytes per nanopublication measured for each layer. |
| 2027 Q2 | 30 million | A3: Nanopub Query with several sources and a load policy per cluster, structural types of static datasets loaded, reference-driven loading. B3: SPARQL on segments at the static registry. Invalidation overlay in the registry. A2: routing by coverage and the resolver in the Router. A first production node with partial coverage. Registry clone with lineage. C1: registry batch publish endpoint. First new bulk dataset, chosen for its use and its license. | Nanodash views and existing query templates work unchanged on the loaded types of a static dataset. The dataset as a whole answers SPARQL at its registry. A retraction published in Nanodash hides a loaded static nanopublication in query results within a minute. Any artifact code resolves through the Router. One production node runs with partial coverage, and the Router sends it only what it covers. Live publishing sustains 100 per second on a test instance. |
| 2027 Q3 | 100 million | B2: sealing from the live registry. A5: checkpoints per cluster, and node bring-up by clone. B4: mirror tool, availability statements, holders per segment and cluster in the Monitor. C2: Query load path and repository consolidation. A4 begins: scope declarations and list caps. A second operator with partial coverage. Second bulk dataset. | Every cluster has at least two holders, and the Monitor shows the count. A node rebuilds itself without manual steps. Hot stores stay bounded while the total grows. Every segment has at least three holders. A query node reloads its hot window in under 30 minutes. |
| 2027 Q4 | 300 million | D1: global metadata index, fed from the registries. D2: design of the term index. An external operator runs a mirror. Load test at one billion with synthetic lean records. | Total infrastructure cost matches section 7 within a factor of two. The billion-record test passes on lookup, list sync and tier 1 to 3 queries. |

### 8.3 Years two and three: to 30 billion by the end of 2029

- **2028, to 3 billion.** Shard nodes that store each nanopublication once. Measured quads per node, and from that the dynamic share for 2029. Templates migrated from `full` to declared scopes. Index from terms to nanopublications and types. Continuous sealing with small recent segments and background merging, for agent-rate publishing at 1,000 per second per registry. Merged query snapshots per dataset. Term-to-segment index. Partial-coverage mirrors as the normal case, with five to ten independent operators. A published price for bulk hosting.
- **2029, to 30 billion.** Thirty thousand segments. Catalog and resolver at full size. Segment-level deletion procedure exercised. Query routing by scope enforced for public endpoints, with tier 5 left to those who build it. Governance for the mirror network: who may publish manifests that mirrors accept by default, and how disputes over removals are settled.

### 8.4 Beyond

At 100 billion a replica is 140 TB and at a trillion 1.4 PB. Nothing in the design changes at these sizes. What changes is that a full replica becomes an institutional commitment, so the network consists of partial mirrors, and the replica count per segment becomes the central health metric. The global metadata index (6 TB at 100 billion) and the term-to-segment index become the largest single structures and would themselves be published as segments.

## 9. Risks and open questions

| Risk or question | Why it matters | What would settle it |
|---|---|---|
| Split of the registry file between content, metadata and blobs | Moves the storage estimate by a factor of three | Three builds on the existing snapshot |
| MongoDB and marginal RDF4J size per nanopublication | The limit of the live plane rests on two assumptions | Measure on a production host |
| Serving thousands of segments from one process | Sets the number of serving nodes | Test with 1,000 segments of one million |
| rete maturity | Format changes, single maintainer, 32-bit term identifiers | Section 5.3 |
| Query across many segments | Tier 2 may be too slow without merged snapshots | Benchmark federation over 100 and 1,000 segments with real Nanodash queries |
| Existing query templates without `full` | Half of the templates target `full` | Count which mirrored templates change their results when `full` holds only what an instance has loaded |
| Finding segments by term | No design yet | Prototype on the first-generation corpus |
| Demand | Nobody may query a billion converted records | Choose bulk datasets with a named consumer |
| Unsigned first-generation records | The second generation accepts only signed nanopublications | Decide between serving them as a marked legacy archive and re-signing with a bot key and derivation provenance, which changes their identifiers |
| Crawlers | Already most of the traffic, and static files with open range requests are an easy target | Rate limits per segment, CDN caching of whole segments, a requester-pays option |
| Ordering and counters | Registries expose a load counter that query nodes follow. Segments arrive out of order. | Counter ranges per segment in the manifest, with the hot counter above all of them |
| Operating many dynamic nodes | The 2026 incident rate on three nodes does not scale to a hundred | Store stability, automatic rebuild, and a measured ceiling of quads per node before the share is raised |
| Questions that name no type | About 190 of the 391 templates on `full` contain no type pattern, and type shards cannot answer them | Design and size the index from terms to nanopublications and types; migrate those templates to a lookup followed by a scoped query |
| Nanopublications without a type | 13% of the snapshot is on no type list | Decide on a reserved type in the registry, and check how type inference differs between Registry and Query |
| Typing discipline | Shards are as good as the types publishers choose; the largest type is 24% of the network today | Guidance for bulk publishers; caps and quotas per list; watch the type size distribution |
| Semantics of a capped scope | Results over cut lists are incomplete, and list order differs between registries | Fix the cut rule and report cut lists with every result |
| Clones share faults | A store image copies corruption, and copies of one image agree with each other, so the fleet checks stop detecting anything | Images only from probed nodes; one node per type built from the exchange form by another builder; checksums against the registry lists, and a content checksum per repository compared between independently built nodes |
| Clusters with one holder or none | Copies are an outcome of who chooses to cover what, so unpopular content can end up with a single copy | Holders per cluster in the Monitor; one static copy paid by the publisher; an archive of last resort |
| Fixed cost per operator | A node costs little, and a person to run it costs much more, which keeps small operators out | Nodes that run unattended: clone, automatic rebuild, static where possible |
| Live in a registry, loaded nowhere | Such content is invisible to Nanodash and to every query | Global indexes fed from the registries; SPARQL on the registry's checkpoints where queries are wanted |
| Size of a registry's live store | The cost of keeping content live without loading it rests on an untested MongoDB capacity per node | Load a registry to 100 million and measure storage, memory and list operations |
| SPARQL on segments | rete's SPARQL coverage and speed under public load are untested, and a segment endpoint answers the state as sealed | Run real queries against the first static dataset; limits per client; document the scope and the validity caveat in the manifest |
| Operators | Three replicas run by one organization are one failure domain | Recruit mirrors early, starting with partners who already run a registry |

## 10. Decisions needed

1. Confirm the targets used here (300 million by the end of 2027, 30 billion by the end of 2029) or replace them. The tables rescale directly.
2. Blobs in the segment file, serialization on request, or the Jelly source as content store.
3. Segment size and the manifest vocabulary.
4. Which types are loaded into every Query instance by default.
5. The form of scope declarations in query templates (types and quantity), the rule for cutting a list (newest entries or first by position), and the schedule for retiring `full`.
6. What happens to nanopublications without a type.
7. How much Knowledge Pixels itself keeps loaded, for 2027 and after, and whether a second query engine behind the same repository addresses is in scope.
8. Type clusters: who defines them, whether a type may belong to several, where unassigned types go, and which clusters every node carries.
9. Who owns what has no natural payer: Router, Monitor, coverage map, global indexes, and content that no operator covers.
10. Whose checkpoints a node accepts by default: store images from listed peers and the exchange form from anyone, as proposed in 4.11, or something stricter.
11. Ed25519 next to RSA, and from which versions of nanopub-java and the registry.
12. Which bulk datasets, and what is done with the unsigned first-generation corpus.
13. Whether Knowledge Pixels operates all three initial replicas or seeks external mirrors from the start.
14. A price for bulk hosting, if any.

## Appendix A. Measurements and sources

| Value | Source |
|---|---|
| 108,975 nanopublications, 810 agents, 919 accounts | `https://registry.knowledgepixels.com/.json`, `registry.petapico.org`, `registry.nanodash.net`, 25 November 2026 |
| 79,672 on 4 May 2026; simulation results | Ecosystem paper, sections 5.1 to 5.3 (`../nanopub-ecosystem-paper`) |
| Snapshot of 102,500: build 5 min 48 s, `rete build` 1 min 42 s, 377 MB and 394 MB, memory, latencies, validation 26 min | `design.md` on branch `202-read-only-rete-mode` of `../nanopub-registry`, section "Measured on the full network (2026-11-03)" |
| 6,540,316 quads: 4,045,752 content, 2,289,564 registry metadata, 205,000 blobs; uncompressed 1,087, 660 and 990 MB | Counted from `readonly-data-full/registry.nq.gz` for this document |
| Compressed Jelly 552 and 733 bytes | `/nanopubs.jelly?afterCounter=100000` (8,975 nanopublications, 28.2 MB), zstd -19 and gzip -9 |
| 12 GB RDF4J store at 88,000, 2,800 repositories, 6.2 GB memory, 2 hour load | `../nanopub-query/doc/operations.md`; `../kpxl-admin/migrations/kpxl-to-ovh.md` |
| Publish 15 to 16 per second; 4.7 cores; sync 89,000 in 30 minutes; incidents | `../kpxl-admin/conf/nginx-registry-query-vhosts.conf`, `incidents.md` |
| Registry loading 50 to 80 per second, time spent in MongoDB round trips | Registry issue #57 |
| Limits of 1,200 triples and 1 MB; quota defaults | `RegistryDB.java`, `Task.java`, `UnapprovedPublishBudget.java` in `../nanopub-registry` |
| First-generation dump: 378.7 million quads, 43.2 million graphs, 2.52 GB; 222,000 quads per second; DataCite 9.83 billion triples in 52 GB | rete `CHANGELOG.md` (0.7.0) and benchmark page, `https://caviri.github.io/rete/docs/` |
| Query templates: 391 of 761 target `full`, 231 a type repository; 746 use `npa:graph`; 660 use `npx:invalidates`; of those on `full`, 181 name a fixed type and 190 have no type pattern | Counted in the local mirror `../nanopub-skill/queries/` for this document; the last two by text search |
| 1,738 keys, 1,502 types, 8,481 typed lists with 142,807 entries; largest type 24,551; 12,949 nanopublications on no type list; effect of list caps | Counted from the list metadata in `readonly-data-full/registry.nq.gz` for this document |
| Query loads from one registry by its load counter and inherits its coverage; 33 kinds of admin triples | `JellyNanopubLoader.java` and `doc/admin-triple-table.csv` in `../nanopub-query` |
| Setup id and load counter as instance identity; reset detection in Query and in peer sync; count and XOR checksum per Query repository; loader skips nanopublications already present | `RegistryDB.java`, `RegistryPeerConnector.java` and `ListAppendBatch.java` in `../nanopub-registry`; `JellyNanopubLoader.java`, `StatusController.java` and `NanopubLoader.java` in `../nanopub-query` |
| Migration plan: copy MongoDB to keep the setup id, do not copy the LMDB stores; writes held in memory by RDF4J | `../kpxl-admin/migrations/kpxl-to-ovh.md`, `incidents.md` and `README.md` (watchdog, shutdown guard) |
| Trust types: 1,794 introductions on 1,234 lists and 1,055 endorsements on 65 lists; sizes of the largest structural types | Counted from the list metadata in `readonly-data-full/registry.nq.gz` for this document |
| Operators, type clusters and the pay-per-use principle in sections 4.10 and 7.3 | Slide "Scalability (technical, economical)" |
| Knowledge Space concepts: records, services, quotas, settings, "published" | `https://w3id.org/knowledge-space/`, version 1.0 |
| RDF4J LMDB store: 120 to 130 bytes per quad; one billion triples loaded in about 6 hours | `https://rdf4j.org/documentation/programming/lmdb-store/`; RDF4J issue #4967 |
| Hetzner server, add-on and storage prices | `https://www.hetzner.com/dedicated-rootserver/` (ax41, ax102, ax162, sx65, sx135), `https://docs.hetzner.com/robot/dedicated-server/dedicated-server-hardware/price-server-addons/`, `https://www.hetzner.com/storage/object-storage/` |
| Other object storage prices | `https://www.backblaze.com/cloud-storage/pricing`, `https://wasabi.com/pricing`, `https://developers.cloudflare.com/r2/pricing/`, OVHcloud object storage documentation, AWS Price List API (S3 and data transfer, eu-central-1) |
| Drive prices; 2026 increases | geizhals.eu listings; Vdura index as reported by notebookcheck.net, 21 August 2026; Hetzner press statements of 23 February and 27 May 2026 |
| Wikidata 17.9 billion triples; UniProt 266 billion | `https://qlever.dev/api/wikidata?cmd=stats`; `https://sparql.uniprot.org/.well-known/void` |
| Wikidata query service: reload times, graph split, move to QLever | `https://www.wikidata.org/wiki/Wikidata:SPARQL_query_service/WDQS_backend_update` and its graph split page |
| QLever on UniProt: 40 hours, 3 TB index, 7 TB during the build | `Qleverfile.uniprot` in `ad-freiburg/qlever-control` |
| Certificate Transparency: Sunlight cost and size; Let's Encrypt database logs | `https://words.filippo.io/run-sunlight/`; `https://letsencrypt.org/2025/08/14/rfc-6962-logs-eol` |
| Bluesky: accounts, records, cost of a full-network application view and of a relay | Bluesky transparency report 2025; `https://whtwnd.com/futur.blue/3ls7sbvpsqc2w`; `https://whtwnd.com/bnewbold.net/3lo7a2a4qxg2l` |
| Signature speeds and sizes | `https://bench.cr.yp.to/results-sign/amd64-hertz.html`, `https://lib25519.cr.yp.to/speed.html` |
| OpenAlex 476 million works; Zenodo limits; Cloudflare cache limit | `https://help.openalex.org/download-all-data/openalex-snapshot`; `https://support.zenodo.org/`; `https://developers.cloudflare.com/cache/concepts/default-cache-behavior/` |

Not verified, and to be checked before they are quoted: the counts for Wikidata statements, OpenCitations, Crossref, DataCite, UniProtKB, PubChem and GBIF in section 2.2; the prices of Hetzner server variants other than the base models; current personnel costs.

Not measured, and assumed in the model: the size of the core cluster (10 million) in section 7.3; the 10 million and 190 million live nanopublications per registry node; MongoDB bytes per nanopublication; marginal RDF4J bytes per nanopublication; the size of a registry file without blobs; all figures for the lean profile. The attempt to build the three parts of the snapshot separately for this draft did not run, so that split is an estimate from uncompressed sizes. Not tried: restoring a registry or a Query store from a copy, comparing a Query repository checksum with the registry's list checksums, whether Registry and Query assign the same types to a nanopublication, and whether Query derives identical triples for the same nanopublication on two nodes.
