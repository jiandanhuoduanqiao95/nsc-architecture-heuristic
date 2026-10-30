# References

The two papers the project builds on (local PDFs are not redistributed; the
arXiv pages are authoritative):

- **NSC** — Zhu, Zhao and Lu, *Neural Spectral Capacity: Measuring and
  Designing Architectures from Network Specification Alone*.
  Paper: <https://arxiv.org/abs/2609.23087> ·
  Official implementation: <https://github.com/Optima-CityU/neural-spectral-capacity>
- **LiteTransformerSearch** (source of the 200-configuration panel) —
  Javaheripi, Salahi, Jha, Bubeck, *Training-free Neural Architecture Search
  for Efficient Language Models*, NeurIPS 2022.
  Paper: <https://arxiv.org/abs/2203.02094> ·
  Author code: <https://github.com/microsoft/archai/tree/neurips-lts/archai/nlp>

Citation discipline (official requirement): distinguish what we reproduce
(NSC scoring, the archived panel, the harness) from our own contribution
(the strict-prefix capacity discount and its verification rig). See
`docs/mechanism.md` §11.
