# Copyright (c) 2026, mohammed-du and contributors
# For license information, please see license.txt

"""Full retail master-data seed: branches, warehouses, item groups, items, prices, customers, POS devices."""

import frappe
from frappe.utils import flt, getdate, now_datetime

# ---------------------------------------------------------------------------
# Catalog definition
# ---------------------------------------------------------------------------

BRANCHES = [
	{
		"branch_code": "BR1",
		"branch_name": "Riyadh Main Store",
		"warehouse_name": "Stores - Riyadh",
		"manager_name": "Ahmed Al-Riyadh",
		"phone": "+966-11-234-5678",
		"address": "King Fahd Road, Riyadh",
	},
	{
		"branch_code": "BR2",
		"branch_name": "Jeddah Corniche Store",
		"warehouse_name": "Stores - Jeddah",
		"manager_name": "Khalid Al-Jeddah",
		"phone": "+966-12-345-6789",
		"address": "Corniche Road, Jeddah",
	},
	{
		"branch_code": "BR3",
		"branch_name": "Dammam Industrial Store",
		"warehouse_name": "Stores - Dammam",
		"manager_name": "Fatima Al-Dammam",
		"phone": "+966-13-456-7890",
		"address": "King Saud Street, Dammam",
	},
]

ITEM_GROUP_TREE = {
	"Retail": {
		"Groceries": {},
		"Beverages": {},
		"Dairy": {},
		"Bakery": {},
		"Household": {},
	},
}

ITEMS = [
	# Groceries
	{"code": "RET-RICE-5KG", "name": "Basmati Rice 5kg", "group": "Groceries", "rate": 45.00, "barcode": "6281001001001", "uom": "Nos"},
	{"code": "RET-SUGAR-1KG", "name": "White Sugar 1kg", "group": "Groceries", "rate": 5.50, "barcode": "6281001001002", "uom": "Nos"},
	{"code": "RET-OIL-1L", "name": "Sunflower Oil 1L", "group": "Groceries", "rate": 18.00, "barcode": "6281001001003", "uom": "Nos"},
	{"code": "RET-PASTA-500G", "name": "Penne Pasta 500g", "group": "Groceries", "rate": 8.75, "barcode": "6281001001004", "uom": "Nos"},
	{"code": "RET-LENTILS-1KG", "name": "Red Lentils 1kg", "group": "Groceries", "rate": 12.00, "barcode": "6281001001005", "uom": "Nos"},
	# Beverages
	{"code": "RET-COLA-330", "name": "Cola Can 330ml", "group": "Beverages", "rate": 2.50, "barcode": "6281002002001", "uom": "Nos"},
	{"code": "RET-WATER-600", "name": "Mineral Water 600ml", "group": "Beverages", "rate": 1.50, "barcode": "6281002002002", "uom": "Nos"},
	{"code": "RET-JUICE-1L", "name": "Orange Juice 1L", "group": "Beverages", "rate": 9.00, "barcode": "6281002002003", "uom": "Nos"},
	{"code": "RET-TEA-100", "name": "Black Tea 100 bags", "group": "Beverages", "rate": 15.00, "barcode": "6281002002004", "uom": "Nos"},
	# Dairy
	{"code": "RET-MILK-1L", "name": "Fresh Milk 1L", "group": "Dairy", "rate": 6.50, "barcode": "6281003003001", "uom": "Nos"},
	{"code": "RET-YOGURT-500", "name": "Plain Yogurt 500g", "group": "Dairy", "rate": 4.25, "barcode": "6281003003002", "uom": "Nos"},
	{"code": "RET-CHEESE-200", "name": "Cheddar Cheese 200g", "group": "Dairy", "rate": 11.00, "barcode": "6281003003003", "uom": "Nos"},
	{"code": "RET-BUTTER-200", "name": "Salted Butter 200g", "group": "Dairy", "rate": 8.00, "barcode": "6281003003004", "uom": "Nos"},
	# Bakery
	{"code": "RET-BREAD-WHITE", "name": "White Bread Loaf", "group": "Bakery", "rate": 3.50, "barcode": "6281004004001", "uom": "Nos"},
	{"code": "RET-CROISSANT-6", "name": "Croissant Pack x6", "group": "Bakery", "rate": 14.00, "barcode": "6281004004002", "uom": "Nos"},
	{"code": "RET-MUFFIN-4", "name": "Chocolate Muffin x4", "group": "Bakery", "rate": 12.00, "barcode": "6281004004003", "uom": "Nos"},
	# Household
	{"code": "RET-SOAP-DISH", "name": "Dish Soap 750ml", "group": "Household", "rate": 7.50, "barcode": "6281005005001", "uom": "Nos"},
	{"code": "RET-TISSUE-BOX", "name": "Facial Tissue Box", "group": "Household", "rate": 5.00, "barcode": "6281005005002", "uom": "Nos"},
	{"code": "RET-DETERGENT-2L", "name": "Laundry Detergent 2L", "group": "Household", "rate": 28.00, "barcode": "6281005005003", "uom": "Nos"},
	{"code": "RET-TRASH-BAG", "name": "Trash Bags 30pc", "group": "Household", "rate": 10.00, "barcode": "6281005005004", "uom": "Nos"},
]

CUSTOMERS = [
	{"name": "Walk-in Customer", "branch": None, "type": "Individual", "mobile": None},
	{"name": "Ahmed Al-Riyadh", "branch": "BR1", "type": "Individual", "mobile": "0501111111"},
	{"name": "Sara Retail BR1", "branch": "BR1", "type": "Individual", "mobile": "0501112222"},
	{"name": "Khalid Al-Jeddah", "branch": "BR2", "type": "Individual", "mobile": "0502221111"},
	{"name": "Noura Trading BR2", "branch": "BR2", "type": "Company", "mobile": "0502223333"},
	{"name": "Fatima Al-Dammam", "branch": "BR3", "type": "Individual", "mobile": "0503331111"},
	{"name": "Eastern Corp BR3", "branch": "BR3", "type": "Company", "mobile": "0503334444"},
]

POS_DEVICES = [
	{"device_id": "POS-BR1-01", "device_name": "Riyadh Counter 1", "branch": "BR1", "device_type": "Desktop"},
	{"device_id": "POS-BR1-02", "device_name": "Riyadh Counter 2", "branch": "BR1", "device_type": "Tablet"},
	{"device_id": "POS-BR2-01", "device_name": "Jeddah Counter 1", "branch": "BR2", "device_type": "Desktop"},
	{"device_id": "POS-BR2-02", "device_name": "Jeddah Mobile POS", "branch": "BR2", "device_type": "Mobile"},
	{"device_id": "POS-BR3-01", "device_name": "Dammam Counter 1", "branch": "BR3", "device_type": "Desktop"},
]

# One cashier per branch — password: Retail@1234
RETAIL_CASHIERS = [
	{
		"email": "cashier.br1@retail.local",
		"first_name": "Cashier",
		"last_name": "Riyadh",
		"branch": "BR1",
		"pos_device": "POS-BR1-01",
		"max_discount_percent": 10,
		"roles": ["Sales User", "Stock User"],
	},
	{
		"email": "cashier.br2@retail.local",
		"first_name": "Cashier",
		"last_name": "Jeddah",
		"branch": "BR2",
		"pos_device": "POS-BR2-01",
		"max_discount_percent": 10,
		"roles": ["Sales User", "Stock User"],
	},
	{
		"email": "cashier.br3@retail.local",
		"first_name": "Cashier",
		"last_name": "Dammam",
		"branch": "BR3",
		"pos_device": "POS-BR3-01",
		"max_discount_percent": 10,
		"roles": ["Sales User", "Stock User"],
	},
	{
		"email": "manager.retail@retail.local",
		"first_name": "Retail",
		"last_name": "Manager",
		"branch": "BR1",
		"pos_device": None,
		"max_discount_percent": 30,
		"is_branch_manager": 1,
		"approval_authority": 1,
		"roles": ["Sales Manager", "Stock Manager", "Purchase Manager"],
		"extra_branches": ["BR2", "BR3"],
	},
]

# Default opening qty per item per branch warehouse
OPENING_STOCK_QTY = 100


@frappe.whitelist()
def create_full_retail_test_data(company=None, with_opening_stock=True):
	"""Seed complete retail master data. Idempotent — skips existing records."""
	company = company or _get_company()
	price_list = _get_selling_price_list()

	result = {
		"company": company,
		"price_list": price_list,
		"item_groups": [],
		"branches": [],
		"warehouses": [],
		"items": [],
		"item_prices": [],
		"customers": [],
		"pos_devices": [],
		"pos_profiles": [],
		"opening_stock": [],
		"cashiers": [],
	}

	result["item_groups"] = _ensure_item_groups()
	result["branches"], result["warehouses"] = _ensure_branches_and_warehouses(company)
	result["items"], result["item_prices"] = _ensure_items_and_prices(price_list)
	result["customers"] = _ensure_customers()
	result["pos_profiles"] = _ensure_pos_profiles(company)
	result["pos_devices"] = _ensure_pos_devices()

	if with_opening_stock:
		result["opening_stock"] = _ensure_opening_stock(company)

	result["cashiers"] = _ensure_retail_cashiers()
	_sync_branch_naming_series()
	frappe.db.commit()
	return result


def _get_company():
	company = frappe.db.get_single_value("Global Defaults", "default_company")
	if company:
		return company
	companies = frappe.get_all("Company", pluck="name", limit=1)
	if not companies:
		frappe.throw("No Company found. Create a Company before running retail test data setup.")
	return companies[0]


def _get_selling_price_list():
	return (
		frappe.db.get_value("Price List", {"selling": 1, "enabled": 1}, "name")
		or "Standard Selling"
	)


def _ensure_item_groups():
	created = []

	def _create_group(name, parent=None, is_group=0):
		if frappe.db.exists("Item Group", name):
			return name
		doc = frappe.get_doc(
			{
				"doctype": "Item Group",
				"item_group_name": name,
				"parent_item_group": parent or "All Item Groups",
				"is_group": is_group,
			}
		)
		doc.insert(ignore_permissions=True)
		created.append(name)
		return name

	for root, children in ITEM_GROUP_TREE.items():
		_create_group(root, is_group=1)
		for child in children:
			_create_group(child, parent=root, is_group=0)

	return created


def _ensure_branches_and_warehouses(company):
	branches = []
	warehouses = []
	cost_center = frappe.db.get_value(
		"Cost Center", {"company": company, "is_group": 0}, "name", order_by="creation asc"
	)

	for branch_def in BRANCHES:
		code = branch_def["branch_code"]
		branches.append(code)

		if not frappe.db.exists("Company Branch", code):
			doc = frappe.get_doc(
				{
					"doctype": "Company Branch",
					"branch_code": code,
					"branch_name": branch_def["branch_name"],
					"company": company,
					"cost_center": cost_center,
					"is_active": 1,
					"manager_name": branch_def.get("manager_name"),
					"phone": branch_def.get("phone"),
					"address": branch_def.get("address"),
				}
			)
			doc.insert(ignore_permissions=True)

		wh_name = branch_def["warehouse_name"]
		warehouse = frappe.db.get_value("Warehouse", {"warehouse_name": wh_name, "company": company})
		if not warehouse:
			parent = frappe.db.get_value("Warehouse", {"company": company, "is_group": 1}, "name")
			if not parent:
				parent = frappe.db.get_value("Warehouse", {"company": company}, "name", order_by="lft asc")
			wh_doc = frappe.get_doc(
				{
					"doctype": "Warehouse",
					"warehouse_name": wh_name,
					"company": company,
					"parent_warehouse": parent,
					"is_group": 0,
				}
			)
			wh_doc.insert(ignore_permissions=True)
			warehouse = wh_doc.name

		frappe.db.set_value("Company Branch", code, "warehouse", warehouse, update_modified=False)
		frappe.db.set_value("Warehouse", warehouse, "branch", code, update_modified=False)
		warehouses.append(warehouse)

	return branches, warehouses


def _ensure_items_and_prices(price_list):
	items_created = []
	prices_created = []
	retail_group = "Retail" if frappe.db.exists("Item Group", "Retail") else None

	for row in ITEMS:
		code = row["code"]
		if not frappe.db.exists("Item", code):
			doc = frappe.get_doc(
				{
					"doctype": "Item",
					"item_code": code,
					"item_name": row["name"],
					"item_group": row["group"],
					"stock_uom": row.get("uom", "Nos"),
					"is_stock_item": 1,
					"include_item_in_manufacturing": 0,
					"item_type": "Stock Item",
					"main_group": retail_group,
					"sub_group": row["group"],
					"max_discount": 15,
					"barcode_symbology": "EAN-13",
				}
			)
			doc.insert(ignore_permissions=True)
			items_created.append(code)

			if row.get("barcode"):
				barcode_doc = frappe.get_doc(
					{
						"doctype": "Item Barcode",
						"barcode": row["barcode"],
						"barcode_type": "EAN",
						"parent": code,
						"parentfield": "barcodes",
						"parenttype": "Item",
					}
				)
				barcode_doc.insert(ignore_permissions=True)
		else:
			items_created.append(code)

		if not frappe.db.exists("Item Price", {"item_code": code, "price_list": price_list}):
			frappe.get_doc(
				{
					"doctype": "Item Price",
					"item_code": code,
					"price_list": price_list,
					"price_list_rate": flt(row["rate"]),
					"currency": frappe.db.get_value("Price List", price_list, "currency") or "SAR",
				}
			).insert(ignore_permissions=True)
			prices_created.append(code)

	return items_created, prices_created


def _ensure_customers():
	customer_group = frappe.db.get_value("Customer Group", {"is_group": 0}, "name") or "Individual"
	territory = frappe.db.get_value("Territory", {"is_group": 0}, "name") or "Saudi Arabia"
	created = []

	for row in CUSTOMERS:
		name = row["name"]
		if frappe.db.exists("Customer", name):
			created.append(name)
			continue

		doc = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": name,
				"customer_type": row.get("type", "Individual"),
				"customer_group": customer_group,
				"territory": territory,
				"mobile_no": row.get("mobile"),
				"branch": row.get("branch"),
			}
		)
		doc.insert(ignore_permissions=True)
		created.append(name)

	return created


def _ensure_pos_profiles(company):
	created = []
	mop = frappe.db.get_value("Mode of Payment", {"type": "Cash"}, "name") or "Cash"
	price_list = _get_selling_price_list()
	warehouse_field = "warehouse"

	for branch_def in BRANCHES:
		code = branch_def["branch_code"]
		profile_name = f"POS Profile - {code}"
		if frappe.db.exists("POS Profile", profile_name):
			created.append(profile_name)
			continue

		warehouse = frappe.db.get_value("Company Branch", code, "warehouse")
		doc = frappe.get_doc(
			{
				"doctype": "POS Profile",
				"name": profile_name,
				"company": company,
				"branch": code,
				"warehouse": warehouse,
				"selling_price_list": price_list,
				"currency": frappe.db.get_value("Company", company, "default_currency") or "SAR",
				"write_off_account": frappe.db.get_value(
					"Account", {"company": company, "account_type": "Expenses Included In Valuation"}, "name"
				),
				"write_off_cost_center": frappe.db.get_value("Cost Center", {"company": company}, "name"),
			}
		)
		doc.append("payments", {"mode_of_payment": mop, "default": 1})
		doc.insert(ignore_permissions=True)
		created.append(profile_name)

	return created


def _ensure_pos_devices():
	created = []
	for row in POS_DEVICES:
		device_id = row["device_id"]
		if frappe.db.exists("POS Device", device_id):
			created.append(device_id)
			continue

		branch = row["branch"]
		warehouse = frappe.db.get_value("Company Branch", branch, "warehouse")
		profile = f"POS Profile - {branch}" if frappe.db.exists("POS Profile", f"POS Profile - {branch}") else None

		doc = frappe.get_doc(
			{
				"doctype": "POS Device",
				"device_id": device_id,
				"device_name": row["device_name"],
				"branch": branch,
				"warehouse": warehouse,
				"pos_profile": profile,
				"device_type": row.get("device_type", "Desktop"),
				"is_active": 1,
				"is_online": 0,
				"registration_date": getdate(),
			}
		)
		doc.insert(ignore_permissions=True)
		created.append(device_id)

	return created


def _ensure_opening_stock(company):
	"""Material Receipt per branch warehouse with all retail items."""
	results = []
	item_codes = [row["code"] for row in ITEMS]

	for branch_def in BRANCHES:
		code = branch_def["branch_code"]
		warehouse = frappe.db.get_value("Company Branch", code, "warehouse")
		if not warehouse:
			continue

		stock_entry_name = f"Opening Stock - {code}"
		if frappe.db.exists("Stock Entry", {"title": stock_entry_name}):
			results.append({"branch": code, "stock_entry": stock_entry_name, "skipped": True})
			continue

		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Material Receipt"
		se.company = company
		se.posting_date = getdate()
		se.set_posting_time = 1
		se.posting_time = now_datetime().strftime("%H:%M:%S")
		se.title = stock_entry_name
		se.to_warehouse = warehouse

		for item_code in item_codes:
			se.append(
				"items",
				{
					"item_code": item_code,
					"qty": OPENING_STOCK_QTY,
					"t_warehouse": warehouse,
					"basic_rate": flt(
						frappe.db.get_value(
							"Item Price",
							{"item_code": item_code, "price_list": _get_selling_price_list()},
							"price_list_rate",
						)
						or 1
					),
				},
			)

		se.flags.ignore_permissions = True
		se.insert()
		se.submit()
		results.append({"branch": code, "stock_entry": se.name, "items": len(item_codes), "qty_each": OPENING_STOCK_QTY})

	return results


def _ensure_retail_cashiers():
	"""Create one cashier per branch + a retail manager, with branch User Permissions and POS device link."""
	from custom_erpnext.services.branch_permission_service import sync_user_branch_permissions

	created = []
	for user_def in RETAIL_CASHIERS:
		email = user_def["email"]
		branch = user_def["branch"]
		extra_branches = user_def.get("extra_branches", [])

		# 1. Create User
		if not frappe.db.exists("User", email):
			u = frappe.get_doc({
				"doctype": "User",
				"email": email,
				"first_name": user_def["first_name"],
				"last_name": user_def.get("last_name", ""),
				"send_welcome_email": 0,
				"enabled": 1,
			})
			for role in user_def["roles"]:
				u.append("roles", {"role": role})
			u.insert(ignore_permissions=True)
			u.new_password = "Retail@1234"
			u.save(ignore_permissions=True)

		# 2. Set default branch on User record
		frappe.db.set_value("User", email, "branch", branch, update_modified=False)

		# 3. User Permissions — branch isolation
		branch_rows = [{"branch": branch, "is_default": 1}]
		for eb in extra_branches:
			branch_rows.append({"branch": eb, "is_default": 0})
		sync_user_branch_permissions(email, branch_rows=branch_rows)

		# 4. User Discount Profile
		if frappe.db.exists("User Discount Profile", email):
			profile = frappe.get_doc("User Discount Profile", email)
		else:
			profile = frappe.get_doc({"doctype": "User Discount Profile", "user": email})
		profile.max_discount_percent = user_def.get("max_discount_percent", 0)
		profile.is_cashier = 1 if not user_def.get("is_branch_manager") else 0
		profile.is_branch_manager = user_def.get("is_branch_manager", 0)
		profile.approval_authority = user_def.get("approval_authority", 0)
		profile.set("allowed_branches", [])
		profile.append("allowed_branches", {"branch": branch, "is_default": 1})
		for eb in extra_branches:
			profile.append("allowed_branches", {"branch": eb, "is_default": 0})
		profile.save(ignore_permissions=True)

		# 5. POS device association (POS Device has no default_user field; the link
		# is maintained from the invoice/cashier side, so we only record it here).
		pos_device = user_def.get("pos_device")

		created.append({
			"email": email,
			"password": "Retail@1234",
			"branch": branch,
			"extra_branches": extra_branches,
			"pos_device": pos_device,
		})

	return created


def _sync_branch_naming_series():
	from custom_erpnext.setup.naming_series import sync_all_branch_naming_series

	sync_all_branch_naming_series()

	# Grant middleware user access to new branches if exists
	if frappe.db.exists("User", "middleware@laravel.local"):
		from custom_erpnext.services.branch_permission_service import sync_user_branch_permissions

		branches = frappe.get_all("Company Branch", filters={"is_active": 1}, pluck="name")
		if branches:
			rows = [{"branch": b, "is_default": 1 if i == 0 else 0} for i, b in enumerate(branches)]
			sync_user_branch_permissions("middleware@laravel.local", branch_rows=rows)
