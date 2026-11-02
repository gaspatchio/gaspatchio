# gaspatchio-viewer

The built page behind `gspio calc-graph model.py points.parquet --html out.html`.

One artifact in, one HTML file out: bundle, styles, three font faces and the
soup can, all inside the file. The page fetches nothing, computes nothing and
writes nothing — every number on it is a value the artifact carries. It ends
with the licence notices of the packages and fonts it carries, in a comment
after `</html>`, which says how to read them back.

    pip install "gaspatchio[viewer]"

Nothing here imports gaspatchio. The source it is built from is `viewer/` in
the gaspatchio repository.
