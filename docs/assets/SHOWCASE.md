# README showcase

`grader-showcase.gif` is a 21.5-second, infinitely looping introduction to the
grader. `grader-showcase.png` is its still-image alternative. The surrounding
frame is editorial artwork; the report excerpts retain the report's text and
stylesheet. This is a documentation asset, not a new product interface.

The four scenes show independent, committed synthetic examples:

| Scene | Source | Evidence shown |
| --- | --- | --- |
| Verify | `examples/grade-cja-clean.html` | A, 100%, 40 components; six category scores |
| Diagnose | `examples/grade-cja-messy.html` | Mixed category scores, including naming at 100% and governance at 0% |
| Act | `examples/grade-cja-messy.html` | CALC-014, high severity, affected component group and remediation |
| Repeat | `examples/grade-aa-clean.html` | A, 100%, 19 components; six category scores |

These are excerpts, not a before/after experiment or evidence of automatic
remediation. The affected-component field retains the report's horizontal
overflow. Open the complete report to inspect the full group. No private corpus,
customer data, Adobe connection, or live API is used in rendering.

## Reproduce

Use Node.js, Google Chrome, and FFmpeg. Install the capture dependency in a
temporary directory; it is not a grader dependency. From the repository root:

```sh
mkdir -p /tmp/sdr-showcase-tools
npm install --prefix /tmp/sdr-showcase-tools playwright-core@1.58.2
SHOWCASE_TOOLS=/tmp/sdr-showcase-tools node docs/assets/capture-showcase.mjs
```

Set `SHOWCASE_CHROME` to the Chrome executable on other systems. Optionally set
`SHOWCASE_OUTPUT` to a temporary preview directory. The capture blocks network
requests, extracts only the listed public report sections, and writes a GIF,
poster, and four scene PNGs for visual review. Commit only the GIF and poster;
the individual scene PNGs are inspection outputs. Frames are removed after
encoding. Font availability and Chrome/FFmpeg versions can affect raster bytes.

Check every scene for clipping and readability, inspect the encoded GIF, and
confirm it loops and stays below 2 MB. Keep the opening frame meaningful for
clients that do not animate GIFs. The README provides a still-image link and
links to complete, release-pinned reports for readers who need more time.

The README's image and still-image URLs pin the documentation asset commit,
independently of the package version. When replacing the assets, commit them
first, then update both absolute URLs to that commit. This keeps the URLs usable
on GitHub and PyPI without moving a release tag or inventing a package release.
Existing version-pinned documentation and example links remain unchanged.
