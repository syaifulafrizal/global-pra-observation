# Dashboard verification

Run the deterministic regression suites from the repository root:

```powershell
python -B -m unittest discover -s tests -q
node --test tests/dashboard.test.js
```

The browser audit requires Playwright and Chromium. Make Playwright available to
Node (install it outside the repository or use the configured runtime's
`NODE_PATH`). If needed, set `CHROMIUM_EXECUTABLE_PATH` to an installed Chromium
executable. Otherwise the script uses Playwright's default browser, with a
fallback for the bundled Windows browser available in this workspace.

```powershell
node tests/dogfood-site.cjs http://127.0.0.1:5000/ output/dogfood/local
node tests/dogfood-site.cjs https://syaifulafrizal.github.io/global-pra-observation/ output/dogfood/live
```

The audit reads the site, selects controls, downloads files, and intercepts
responses inside isolated browser contexts for anomaly and network-failure
fixtures. It does not write to the server or its datasets. It currently covers
the published five-date, 51-station dataset, including all station selections,
figures, numerical chart values, map controls, themes, responsive layouts,
refresh, export, time zones, late responses, and recovery from failed requests.

Results and screenshots are written to the specified output folder. Any failed
scenario sets a nonzero exit code. `DOGFOOD_ONLY` optionally selects scenario
names using a regular expression; initial metadata loading always runs.
Browser viewport and touch emulation do not replace physical-device or
cross-browser testing.
