# Scaling nanopublications: summary

> **Draft, work in progress.** 26 November 2026. The content is incomplete and will change.

This is the short version of [`scaling-nanopublications.md`](scaling-nanopublications.md). It leaves out the calculations and the reasoning behind each choice. Everything here is a proposal, and most of the mechanisms have not been tried yet.

## The goal

| | Nanopublications |
|---|---:|
| Today (November 2026) | 109 thousand |
| End of 2027 | 300 million |
| End of 2029 | 30 billion |

Today every node holds everything. A registry accepts about 16 nanopublications per second, and a query node loads about 12 per second into its database. At 300 million, a new query node would need 289 days to load. The current design works well at today's size and stops working somewhere around 10 million per node.

## The idea

![How publishing, registries, segments and query services fit together](figures/architecture.svg)

Four changes carry the design.

1. **No node holds everything.** Each operator covers the clusters of types it cares about. A cluster is a named set of nanopublication types, such as "biodiversity" or "medicine".
2. **Registries hold nanopublications in two ways.** New records arrive one at a time in a live store, as today. Older and bulk content sits in *segments*: sealed files of one to ten million nanopublications that are copied and verified like any other file. A registry seals its live content into segments as it ages. Large datasets are published as segments directly.
3. **Query services stay as they are.** They load the types they select, from any registry, and answer completely for what they have loaded. Queries state which types they need and how many nanopublications at most, so that one huge list from one publisher cannot slow down anyone else. The `full` repository of everything is retired.
4. **Registries answer simple queries on their segments.** A dataset can be queried where it is held, without loading it anywhere.

A small set of shared services tells clients who holds what: the Router, a coverage map, and indexes for finding a nanopublication by identifier, publisher, type or date.

## Who runs what

![Operators and the clusters of types they cover with a registry or a query service](figures/operators.svg)

The network becomes a grid of operators and clusters. Every node carries the small trust cluster. Most carry the core cluster with templates, queries and views. Beyond that, each operator chooses.

- **Scale out:** a new domain is a new column, carried by whoever needs it. No existing node grows because of it.
- **Pay per use:** an operator pays for what it covers and for what it loads. Whoever wants a whole domain loaded for queries funds the large nodes for it.
- **Copies are an outcome.** Nobody sets a replica count. A monitor reports how many operators hold each cluster, and a cluster with one holder is at risk.

## What it costs

![Cost of one copy of a million nanopublications per year, by way of holding](figures/costs.svg)

Keeping nanopublications as files is cheap. Loading them into a query database costs seventy to several thousand times more. So an operator's bill depends on what it loads, and hardly on what it covers.

For one operator covering a domain of a billion nanopublications, hardware comes to about €60 per month for a registry, about €260 for a query service with 1% loaded, and about €2,500 with everything loaded. A whole network of 30 billion with three copies and little loaded adds up to about €3,200 per month.

Two caveats. The people who build and run the software cost far more than the machines, at every size. And producing the records can cost far more than hosting them, so large numbers have to come from converting existing structured data, not from generating content.

## New nodes start from a copy

Today a new node replays the whole history. A full query node of 28 million nanopublications would take 27 days that way, and 38 minutes to copy. The plan therefore includes a clone feature: nodes publish checkpoints per cluster, and a new node downloads one and then follows only what has arrived since. Without it, operators cannot join or recover in reasonable time.

## What has to be built

About three engineer-years of work in four tracks:

| Track | What it delivers |
|---|---|
| A. Scaling out by cluster | Cluster definitions, declared coverage, routing by coverage, query services that choose what to load, declared query scopes, cloning |
| B. The cheap level | Static registries on segments, sealing, queries on segments, mirrors |
| C. Rate and record format | Faster publishing and loading, smaller signatures |
| D. Finding things without `full` | Network-wide indexes |

Tracks A and B do not depend on each other. The shortest path to a second operator with partial coverage is about eight months of work.

| When | Target | Main steps |
|---|---:|---|
| 2027 Q1 | 10 million | First static registry, built from the first-generation corpus. Cluster definitions. |
| 2027 Q2 | 30 million | Query services load from several registries by their own policy. Routing by coverage. First node with partial coverage. |
| 2027 Q3 | 100 million | Sealing. Cloning. Mirrors. A second operator. |
| 2027 Q4 | 300 million | Network-wide indexes. Test with a billion records. |
| 2028 to 2029 | 30 billion | Templates moved off `full`. Many independent operators. |

## What is open

- **Untested assumptions.** How much one registry and one query node can carry, how large the files are without stored serializations, and how well the file format (rete, an early-stage project with one maintainer) holds up.
- **Questions that name no type,** such as "everything that mentions this term". They need an index that has no design yet. About 190 existing query templates depend on it.
- **Shared services and orphaned content.** The Router, the monitor and the indexes serve everyone and need an owner. Content that no operator covers has no copy.
- **Content.** The plan makes large numbers cheap. It does not make them useful, and the choice of what to publish in bulk deserves as much care as the engineering.

The full document has the measurements, the cost model, the risks and a list of fourteen decisions that are needed.
