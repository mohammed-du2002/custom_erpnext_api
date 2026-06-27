"""Enable Saudi Arabic (ar) as the site default language."""

from __future__ import annotations

import frappe


def setup_arabic_language(set_default: bool = True, set_user_language: bool = False):
	"""Enable Arabic language and optionally set it as the site default.

	Args:
		set_default: Set System Settings language to Arabic.
		set_user_language: Set language=ar for all enabled users (except Guest).
	"""
	_ensure_arabic_language_enabled()

	if set_default:
		frappe.db.set_single_value("System Settings", "language", "ar")
		print("System default language set to Arabic (ar).")

	if set_user_language:
		users = frappe.get_all("User", filters={"enabled": 1, "name": ["!=", "Guest"]}, pluck="name")
		for user in users:
			frappe.db.set_value("User", user, "language", "ar")
		print(f"User language set to Arabic for {len(users)} users.")

	frappe.db.commit()
	frappe.clear_cache()
	print("Arabic language setup complete. Clear browser cache and reload the desk.")


def _ensure_arabic_language_enabled():
	if not frappe.db.exists("Language", "ar"):
		doc = frappe.get_doc(
			{
				"doctype": "Language",
				"language_code": "ar",
				"language_name": "Arabic",
				"enabled": 1,
			}
		)
		doc.insert(ignore_permissions=True)
		print("Created and enabled Language: Arabic (ar).")
		return

	frappe.db.set_value("Language", "ar", "enabled", 1)
	print("Arabic language (ar) is enabled.")
