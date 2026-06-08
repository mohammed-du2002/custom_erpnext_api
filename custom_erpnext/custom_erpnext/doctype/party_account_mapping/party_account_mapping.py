# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class PartyAccountMapping(Document):
	def validate(self):
		self.validate_account_company()
		self.validate_branch_company()
		self.validate_unique_mapping()

	def validate_account_company(self):
		if not self.account:
			return

		account_company = frappe.db.get_value("Account", self.account, "company")
		if account_company and account_company != self.company:
			frappe.throw(
				_("Account {0} does not belong to Company {1}").format(
					frappe.bold(self.account), frappe.bold(self.company)
				)
			)

	def validate_branch_company(self):
		if not self.branch:
			return

		branch_company = frappe.db.get_value("Company Branch", self.branch, "company")
		if branch_company and branch_company != self.company:
			frappe.throw(
				_("Branch {0} does not belong to Company {1}").format(
					frappe.bold(self.branch), frappe.bold(self.company)
				)
			)

	def validate_unique_mapping(self):
		existing = frappe.db.get_value(
			"Party Account Mapping",
			{
				"party_type": self.party_type,
				"party": self.party,
				"company": self.company,
				"branch": self.branch or None,
				"name": ["!=", self.name],
			},
			"name",
		)
		if existing:
			frappe.throw(
				_("A Party Account Mapping already exists for {0} {1} in Company {2}").format(
					self.party_type, frappe.bold(self.party), frappe.bold(self.company)
				)
			)
