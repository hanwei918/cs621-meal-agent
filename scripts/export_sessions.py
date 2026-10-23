"""Copy study sessions from Firestore (the shared demo) to user-study/sessions/ (git-ignored), then
summarise them locally with scripts/study_summary.py. Needs `pip install google-cloud-firestore` and
`gcloud auth application-default login` with the PERSONAL account that owns the demo project.

Run: .venv/bin/python scripts/export_sessions.py <project-id>
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    from google.cloud import firestore
    out = ROOT / "user-study" / "sessions"
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for d in firestore.Client(project=sys.argv[1]).collection("sessions").stream():
        (out / f"{d.id}.json").write_text(json.dumps(d.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        n += 1
    print(f"exported {n} sessions to {out.relative_to(ROOT)}")
