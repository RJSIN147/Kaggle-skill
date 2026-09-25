# Writeup competitions

There is no prediction file and no kx submission path: the writeup is judged against the
competition's evaluation criteria and submitted **by hand on the website**.

- `kx submit --writeup` fetches the competition pages (untrusted text in
  `research/cache/pages/`) and drafts `writeup/CHECKLIST.md`: one checkbox per evaluation
  criterion (you restate them from the Evaluation page in your own words), the evidence
  from the ledger (experiments with verdict links), and pre-submission checks (length
  limits, public links, the deadline).
- Keep running experiments and `kx strategy` for any analysis the writeup reports, so every
  claim traces to a recorded result.
- Tell the user plainly: they submit the writeup themselves; kx cannot.
