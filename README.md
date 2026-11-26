# Scaling nanopublications

A working document on how the nanopublication network can grow from about 100,000 nanopublications today to hundreds of millions within one year and tens of billions within two to three years, and what that costs.

## Contents

- [`scaling-nanopublications.md`](scaling-nanopublications.md): the document. Where the network stands, why the current stack does not get there unchanged, the proposed design (a live plane and a static plane of sealed segments, shards by type cluster, cloning from checkpoints), calculations, costs per million nanopublications and per operator, a roadmap, risks, and the decisions that are needed.
- [`projections.py`](projections.py): the model behind the tables T1 to T15 in the document.

## Regenerating the tables

```
python3 projections.py
```

This prints all tables as Markdown. It needs Python 3 and no packages. Every input at the top of the file is tagged `[M]` for measured or `[A]` for assumed. To update the document after changing an input, run the script and replace the affected tables. Figures quoted in the running text are not updated automatically and have to be checked against the new output.

## Status

Draft 0.1, November 2026. The design sections are proposals. Several of the inputs are assumptions, and the mechanisms for blending, type shards and cloning have not been tried. The document marks these, and Appendix A lists the sources of all measured values together with what is unverified.
