"""Generate the SVG figures used in summary.md.

Run from the repository root:  python3 figures/make_figures.py

The cost figure takes its numbers from projections.py. The other two are diagrams.
Each SVG carries its own light and dark colours and follows the viewer's colour scheme.
Set FIGURES_FORCE_DARK=1 to write the dark variant as the default, for checking it.
"""
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import projections as p  # noqa: E402

LIGHT = {"surface": "#ffffff", "ink": "#191919", "ink2": "#666666", "line": "#d4d4d4", "soft": "#f4f4f4",
         "s1": "#257de0", "s1soft": "#e4effc", "s2": "#f47230", "s2soft": "#fdeadf"}
DARK = {"surface": "#191919", "ink": "#efefef", "ink2": "#9c9c9c", "line": "#3d3d3d", "soft": "#262626",
        "s1": "#338ced", "s1soft": "#1a3350", "s2": "#e76624", "s2soft": "#4b2817"}
FORCE_DARK = os.environ.get("FIGURES_FORCE_DARK") == "1"


def css():
    def block(c):
        return "".join(f"--{k}:{v};" for k, v in c.items())
    base = DARK if FORCE_DARK else LIGHT
    return f"""<style>
svg{{{block(base)}font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif}}
@media (prefers-color-scheme: dark){{svg{{{block(DARK)}}}}}
.surface{{fill:var(--surface)}} .ink{{fill:var(--ink)}} .ink2{{fill:var(--ink2)}}
.box{{fill:var(--soft);stroke:var(--line);stroke-width:1}}
.frame{{fill:none;stroke:var(--line);stroke-width:1.5}}
.reg{{fill:var(--s1soft);stroke:var(--s1);stroke-width:1.5}}
.qry{{fill:var(--s2soft);stroke:var(--s2);stroke-width:1.5}}
.bar{{fill:var(--s1)}}
.grid{{stroke:var(--line);stroke-width:1}}
.arrow{{stroke:var(--ink2);stroke-width:1.5;fill:none}}
.head{{fill:var(--ink2)}}
text{{font-size:13px}} .t{{font-size:15px;font-weight:600}} .h{{font-size:14px;font-weight:600}} .s{{font-size:12px}}
</style>"""


def svg(width, height, body, title):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" height="{height}" '
            f'role="img" aria-label="{title}">\n<title>{title}</title>\n{css()}\n'
            f'<rect class="surface" x="0" y="0" width="{width}" height="{height}" rx="8"/>\n{body}\n</svg>\n')


def rect(x, y, w, h, cls="box", rx=6):
    return f'<rect class="{cls}" x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}"/>'


def text(x, y, s, cls="ink", anchor="start"):
    return f'<text class="{cls}" x="{x}" y="{y}" text-anchor="{anchor}">{s}</text>'


def lines(x, y, rows, cls="ink2", anchor="start", step=17):
    return "\n".join(text(x, y + i * step, r, cls, anchor) for i, r in enumerate(rows))


def arrow(x1, y1, x2, y2):
    ang = math.atan2(y2 - y1, x2 - x1)
    size = 7
    bx, by = x2 - size * math.cos(ang), y2 - size * math.sin(ang)
    px, py = -math.sin(ang) * size * 0.5, math.cos(ang) * size * 0.5
    return (f'<line class="arrow" x1="{x1}" y1="{y1}" x2="{bx:.1f}" y2="{by:.1f}"/>'
            f'<polygon class="head" points="{x2},{y2} {bx + px:.1f},{by + py:.1f} {bx - px:.1f},{by - py:.1f}"/>')


# ---------------------------------------------------------------------------------------
def fig_architecture():
    b = []
    # sources
    b += [rect(94, 24, 92, 44), text(140, 51, "People", "ink", "middle"),
          rect(196, 24, 92, 44), text(242, 51, "Agents", "ink", "middle"),
          rect(340, 24, 216, 44), text(448, 51, "Bulk conversion of datasets", "ink", "middle")]
    b += [arrow(140, 68, 140, 166), arrow(242, 68, 242, 166), arrow(448, 68, 448, 166)]
    b += [text(254, 98, "publish one at a time", "ink2 s"), text(460, 98, "publish as segments", "ink2 s")]
    # registry
    b += [rect(40, 116, 540, 216, "frame", 10), text(56, 142, "Registry", "ink t")]
    b += [rect(64, 168, 216, 140, "reg"), text(80, 194, "Live store", "ink h"),
          lines(80, 218, ["MongoDB", "accepts single records", "trust, lists, quotas"])]
    b += [rect(340, 168, 216, 140, "reg"), text(356, 194, "Segments", "ink h"),
          lines(356, 218, ["sealed files of 1 to 10 million", "copied and verified as files", "SPARQL on the file"])]
    b += [arrow(280, 238, 340, 238), text(310, 228, "seal", "ink2 s", "middle")]
    # query
    b += [rect(700, 116, 220, 216, "frame", 10), text(716, 142, "Query", "ink t")]
    b += [rect(720, 168, 180, 140, "qry"), text(736, 194, "Loaded repositories", "ink h"),
          lines(736, 218, ["RDF4J, as today", "complete for the types", "the node declares"])]
    b += [arrow(580, 238, 700, 238), text(640, 212, "loads", "ink2 s", "middle"), text(640, 228, "selected types", "ink2 s", "middle")]
    # routing strip and clients
    b += [rect(40, 396, 880, 44), text(480, 423, "Router, coverage map and global indexes: who holds what, and where to find it", "ink", "middle")]
    b += [arrow(310, 396, 310, 332), text(322, 360, "fetch, lists,", "ink2 s"), text(322, 376, "SPARQL per dataset", "ink2 s")]
    b += [arrow(810, 396, 810, 332), text(798, 360, "queries over", "ink2 s", "end"), text(798, 376, "declared types", "ink2 s", "end")]
    b += [rect(40, 480, 880, 44), text(480, 507, "Nanodash, applications, agents", "ink", "middle"), arrow(480, 480, 480, 440)]
    return svg(960, 548, "\n".join(b), "How publishing, registries, segments and query services fit together")


# ---------------------------------------------------------------------------------------
def fig_operators():
    cols = [("trust", 260, 90), ("core", 360, 130), ("biodiversity", 500, 140), ("medicine", 650, 140), ("chemistry", 800, 120)]
    span = {name: (x, x + w) for name, x, w in cols}
    b = [text(40, 53, "Clusters of types", "ink2")]
    for name, x, w in cols:
        b += [rect(x, 30, w, 36), text(x + w / 2, 53, name, "ink", "middle")]
        b.append(f'<line class="grid" x1="{x + w + 5}" y1="78" x2="{x + w + 5}" y2="372"/>' if name != "chemistry" else "")
    rows = [
        ("Museum of nature", 115, [("Query", 96, [("trust", "biodiversity")]), ("Registry", 134, [("trust", "biodiversity")])]),
        ("University hub", 209, [("Query", 190, [("trust", "medicine")]), ("Registry", 228, [("trust", "medicine")])]),
        ("Pharma consortium", 284, [("Registry", 284, [("trust", "core"), ("medicine", "chemistry")])]),
        ("AI startup", 340, [("Query", 340, [("trust", "trust"), ("medicine", "medicine")])]),
    ]
    for label, ly, bars in rows:
        b.append(text(40, ly + 20, label, "ink h"))
        for kind, y, segs in bars:
            cls = "reg" if kind == "Registry" else "qry"
            for a, z in segs:
                x1, x2 = span[a][0], span[z][1]
                b.append(rect(x1, y, x2 - x1, 30, cls))
                b.append(text((x1 + x2) / 2, y + 20, kind, "ink h", "middle"))
    # legend
    b += [rect(260, 392, 22, 16, "reg", 4), text(290, 405, "Registry: keeps and serves the nanopublications", "ink2"),
          rect(610, 392, 22, 16, "qry", 4), text(640, 405, "Query: loads them for SPARQL", "ink2")]
    return svg(960, 428, "\n".join(b), "Operators and the clusters of types they cover with a registry or a query service")


# ---------------------------------------------------------------------------------------
def fig_costs():
    static = p.PROFILES["mix"]["archive"] + p.PROFILES["mix"]["index"]

    def storage(price_tb):
        return static * 1e6 / p.TB * price_tb * 12

    loaded = [1e6 * p.DYN_QUADS * c / q * price * 12 for _, c, q, price in p.DYN_LAYOUTS]
    rows = [
        ("Archived as segment files", "on a disk server, or on NVMe", storage(p.PRICE_HDD_TB), storage(p.PRICE_NVME_TB)),
        ("Live in a registry", "190 million per node, or 10 million", p.PRICE_NODE_BIG * 12 / (p.REGISTRY_NODE_FULL / 1e6),
         p.PRICE_NODE_SMALL * 12 / (p.REGISTRY_NODE_NP / 1e6)),
        ("Loaded in Query", "larger engine, or today's layout", min(loaded), max(loaded)),
    ]
    x0, x1, lo, hi = 300, 900, -2, 3            # log10 axis from EUR 0.01 to EUR 1,000

    def sx(v):
        return x0 + (math.log10(v) - lo) / (hi - lo) * (x1 - x0)

    def money(v):
        return f"€{v:,.2f}" if v < 10 else f"€{v:,.0f}"

    b = [text(40, 34, "One copy of a million nanopublications, per year", "ink t"),
         text(40, 54, "Hardware only, late-2026 list prices. Logarithmic scale.", "ink2 s")]
    for e, label in zip(range(lo, hi + 1), ["€0.01", "€0.10", "€1", "€10", "€100", "€1,000"]):
        x = sx(10 ** e)
        b.append(f'<line class="grid" x1="{x:.1f}" y1="78" x2="{x:.1f}" y2="262"/>')
        b.append(text(x, 282, label, "ink2 s", "middle"))
    for i, (name, note, a, z) in enumerate(rows):
        y = 100 + i * 58
        b += [text(40, y + 6, name, "ink h"), text(40, y + 24, note, "ink2 s")]
        b.append(f'<rect class="bar" x="{sx(a):.1f}" y="{y}" width="{sx(z) - sx(a):.1f}" height="18" rx="4"/>')
        b += [text(sx(a) - 8, y + 14, money(a), "ink", "end"), text(sx(z) + 8, y + 14, money(z), "ink")]
    return svg(960, 300, "\n".join(b), "Cost of one copy of a million nanopublications per year, by way of holding")


if __name__ == "__main__":
    out = os.environ.get("FIGURES_OUT", HERE)
    for name, fn in (("architecture", fig_architecture), ("operators", fig_operators), ("costs", fig_costs)):
        path = os.path.join(out, name + ".svg")
        with open(path, "w") as f:
            f.write(fn())
        print("wrote", path)
