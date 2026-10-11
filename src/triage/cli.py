"""Offline CLI: inspect committed evidence or compare candidate generation."""
import argparse
import json
from pathlib import Path
from .match import score, best_match, candidate_index


def main(argv=None):
    parser = argparse.ArgumentParser(prog="triage")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("score", help="compare two names; not a screening decision")
    p.add_argument("query")
    p.add_argument("reference")
    p = sub.add_parser("report", help="read the committed study provenance")
    p.add_argument("--evidence", type=Path,
                   default=Path(__file__).resolve().parents[2]/"evidence")
    p = sub.add_parser("blocking-audit", help="compare blocked with exhaustive retrieval")
    p.add_argument("pairs", type=Path, help="JSON list of {query, reference} known pairs")
    args = parser.parse_args(argv)
    if args.command == "score":
        out = {"score": score(args.query, args.reference),
               "interpretation": "name similarity only; identity not established"}
    elif args.command == "report":
        out = json.loads((args.evidence/"provenance.json").read_text())
        out["review_status"] = "historical blocked matcher; no universal recall ceiling"
    else:
        pairs = json.loads(args.pairs.read_text())
        rows = []
        for row in pairs:
            names = [row["reference"]]
            blocked = best_match(row["query"], names, candidate_index(names))
            full = best_match(row["query"], names)
            rows.append({**row, "blocked_score": blocked[1],
                         "exhaustive_score": full[1],
                         "lost_to_blocking": blocked[0] < 0 and full[0] >= 0})
        out = {"pairs": len(rows), "blocking_losses": sum(r["lost_to_blocking"] for r in rows),
               "rows": rows, "scope": "supplied known pairs, not production recall"}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
