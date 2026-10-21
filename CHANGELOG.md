# Teacher testing and privacy update — 20 October 2026

Hatua is an offline, evidence-linked learner review prototype. This update makes its synthetic-data demonstration easier for a teacher to try and makes its data handling more explicit.

## Changes

- A guided 10–15 minute teacher test, example scenarios, progress checklist and downloadable feedback. The standalone HTML needs no account, Python or network after download.
- An embedded privacy notice and PRIVACY.md covering local storage, typed teacher names, exports, audit logs, plain-text files, deletion, hosting and prerequisites for a real-school pilot.
- Synthetic-only packaging from a fresh temporary workspace, plus an optional manually triggered GitHub Pages workflow. Existing working data and audit logs are not copied into the package.
- No external fonts; the standalone page's Content Security Policy blocks external assets and application connections.
- Browser storage scoped to the embedded dataset, visible storage-failure notices, malformed-storage handling and a clear-data control. In-progress edits survive navigation within the page.
- Separate family-message approval and download, with prepared messages locked after teacher edits so they cannot silently undo a teacher's changes. Changed patterns require fresh teacher review.
- Conflicting assessment terms are excluded from pattern calculations, break consecutive runs, and remain inspectable. The former E16 failure is resolved.
- Literal loopback-only Ollama endpoints, no proxy use or redirects; approval imports require source hashes and explicit family-sharing approval.
- Live class search, keyboard navigation between tabs, source-record access for every record contributing to a term, and browser decisions visible in History.
- Regression checks and a GitHub Actions check workflow.

## Verification

- 21/21 existing evaluations passed, using the rules planner and scripted stand-in models.
- 28/28 Python regression tests passed.
- 16/16 UI DOM integration checks passed against the generated standalone page.
- Python compilation and Git whitespace checks passed.
- No new live Ollama/Qwen run and no real-browser visual, screen-reader or device testing were performed. No real teacher or school validation has been claimed.

## Remaining limits

This remains a synthetic-data prototype. Typed names are not authentication; local files and browser storage are unencrypted; there is no automatic retention schedule. Phrase/citation checks cannot establish semantic correctness. A real-school pilot needs identified responsibility, appropriate privacy and security arrangements, and review with teachers and guardians. The browser demo cannot send messages or import school records.

Source changes are on the local branch improve/teacher-testing-privacy. GitHub publication and a public Pages link depend on account authorization and repository settings; this update does not itself establish a deployed URL.
