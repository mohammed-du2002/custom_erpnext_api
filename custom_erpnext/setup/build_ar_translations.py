"""Build and sync custom_erpnext Arabic (Saudi) translation CSV."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from custom_erpnext.setup.arabic_translations_data import SAUDI_AR_TRANSLATIONS

APP_ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS_DIR = APP_ROOT / "translations"
AR_CSV = TRANSLATIONS_DIR / "ar.csv"


def _collect_labels_from_json(base: Path) -> set[str]:
	labels: set[str] = set()

	def collect(obj):
		if isinstance(obj, dict):
			label = obj.get("label")
			if label:
				labels.add(label)
			options = obj.get("options")
			if isinstance(options, str) and "\n" in options:
				for opt in options.split("\n"):
					if opt.strip():
						labels.add(opt.strip())
			for value in obj.values():
				collect(value)
		elif isinstance(obj, list):
			for item in obj:
				collect(item)

	for path in base.rglob("*.json"):
		try:
			data = json.loads(path.read_text(encoding="utf-8"))
		except (json.JSONDecodeError, OSError):
			continue
		collect(data)
		if data.get("doctype") in ("DocType", "Report") and isinstance(data.get("name"), str):
			labels.add(data["name"])

	return labels


def _read_existing_csv() -> dict[str, str]:
	if not AR_CSV.exists():
		return {}
	existing: dict[str, str] = {}
	with AR_CSV.open(encoding="utf-8") as handle:
		for row in csv.reader(handle):
			if len(row) >= 2 and row[0]:
				existing[row[0]] = row[1]
	return existing


def build_ar_translations() -> dict[str, int]:
	"""Merge JSON labels, hand-curated translations, and existing CSV."""
	custom_root = APP_ROOT / "custom_erpnext"
	all_labels = _collect_labels_from_json(custom_root)
	existing = _read_existing_csv()

	merged = dict(existing)
	for label in sorted(all_labels):
		if label in SAUDI_AR_TRANSLATIONS:
			merged[label] = SAUDI_AR_TRANSLATIONS[label]
		elif label not in merged:
			merged[label] = label  # fallback: keep English until translated

	for source, target in SAUDI_AR_TRANSLATIONS.items():
		merged[source] = target

	TRANSLATIONS_DIR.mkdir(parents=True, exist_ok=True)
	with AR_CSV.open("w", encoding="utf-8", newline="") as handle:
		writer = csv.writer(handle)
		for source in sorted(merged):
			writer.writerow([source, merged[source], ""])

	added = len(merged) - len(existing)
	return {"total": len(merged), "added_or_updated": max(0, added)}


def sync_ar_translations():
	"""Bench entrypoint: rebuild ar.csv from DocType labels."""
	stats = build_ar_translations()
	print(f"Arabic translations synced: {stats['total']} entries ({stats['added_or_updated']} new/updated).")
	return stats
