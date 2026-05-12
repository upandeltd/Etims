# Copyright (c) 2024, Upande Ltd and contributors
# For license information, please see license.txt

import frappe
from frappe.tests.utils import FrappeTestCase

from kenya_etims_compliance.custom_methods.item import searchItemReq, selectItemReq
from kenya_etims_compliance.custom_methods.organization import get_org_user_info
from kenya_etims_compliance.custom_methods.purchase_invoice import (
	searchPurchaseTrnsReq,
	selectPurchaseTrnsInfoReq,
)
from kenya_etims_compliance.custom_methods.sales_invoice import searchSalesTrnsReq, selectSalesTrnsInfoReq
from kenya_etims_compliance.custom_methods.stock import searchStockMoveReq
from kenya_etims_compliance.custom_methods.stock_release import (
	get_stock_release_list,
	search_stock_release_no,
	sync_stock_release_number,
)
from kenya_etims_compliance.utils.etims_utils import eTIMS


class TestETimsAPI(FrappeTestCase):
	"""Test cases for KRA eTIMS API endpoints"""

	def setUp(self):
		"""Set up test fixtures"""
		# Ensure we're in test mode
		frappe.flags.in_test = True

	def test_handle_api_response_success(self):
		"""Test successful API response handling"""
		response_json = {"resultCd": "000", "resultMsg": "Success", "data": {"test": "data"}}
		result = eTIMS.handle_api_response(response_json)
		self.assertIn("Success", result)
		self.assertEqual(result["Success"], {"test": "data"})

	def test_handle_api_response_bad_request(self):
		"""Test 400 Bad Request error handling"""
		response_json = {"resultCd": "400", "resultMsg": "Invalid request"}
		result = eTIMS.handle_api_response(response_json)
		self.assertIn("Error", result)
		self.assertIn("Bad Request", result["Error"])

	def test_handle_api_response_unauthorized(self):
		"""Test 401 Unauthorized error handling"""
		response_json = {"resultCd": "401", "resultMsg": "Invalid credentials"}
		result = eTIMS.handle_api_response(response_json)
		self.assertIn("Error", result)
		self.assertIn("Unauthorized", result["Error"])

	def test_handle_api_response_server_error(self):
		"""Test 500 Server Error error handling"""
		response_json = {"resultCd": "500", "resultMsg": "Internal server error"}
		result = eTIMS.handle_api_response(response_json)
		self.assertIn("Error", result)
		self.assertIn("Server Error", result["Error"])

	def test_handle_api_response_unknown_error(self):
		"""Test unknown error code handling"""
		response_json = {"resultCd": "999", "resultMsg": "Unknown error"}
		result = eTIMS.handle_api_response(response_json)
		self.assertIn("Error", result)
		self.assertIn("Error 999", result["Error"])

	def test_search_item_no_params(self):
		"""Test searchItem without parameters"""
		# This is a mock test - in real scenario, you'd mock the API call
		result = eTIMS.searchItem()
		self.assertIsInstance(result, dict)

	def test_search_stock_move_no_params(self):
		"""Test searchStockMove without parameters"""
		result = eTIMS.searchStockMove()
		self.assertIsInstance(result, dict)

	def test_search_sales_trns_no_params(self):
		"""Test searchTrns for sales without parameters"""
		result = eTIMS.searchTrns(trns_type="sales")
		self.assertIsInstance(result, dict)

	def test_search_purchase_trns_no_params(self):
		"""Test searchTrns for purchase without parameters"""
		result = eTIMS.searchTrns(trns_type="purchase")
		self.assertIsInstance(result, dict)

	def test_search_trns_invalid_type(self):
		"""Test searchTrns with invalid transaction type"""
		result = eTIMS.searchTrns(trns_type="invalid")
		self.assertIn("Error", result)
		self.assertIn("Invalid transaction type", result["Error"])

	def test_stock_release_no_save(self):
		"""Test stockReleaseNoSaveReq"""
		result = eTIMS.stockReleaseNoSaveReq(12345, 0, "11")
		self.assertIsInstance(result, dict)

	def test_search_stock_release_no(self):
		"""Test searchStockReleaseNo"""
		result = eTIMS.searchStockReleaseNo()
		self.assertIsInstance(result, dict)

	def test_select_stock_release_no_list(self):
		"""Test selectStockReleaseNoList"""
		result = eTIMS.selectStockReleaseNoList()
		self.assertIsInstance(result, dict)

	def test_select_item(self):
		"""Test selectItem"""
		result = eTIMS.selectItem("TEST_ITEM_CODE")
		self.assertIsInstance(result, dict)

	def test_select_sales_trns_info(self):
		"""Test selectTrnsSalesInfo"""
		result = eTIMS.selectTrnsSalesInfo("12345")
		self.assertIsInstance(result, dict)

	def test_select_purchase_trns_info(self):
		"""Test selectTrnsPurchaseInfo"""
		result = eTIMS.selectTrnsPurchaseInfo("12345")
		self.assertIsInstance(result, dict)

	def test_select_notice_info(self):
		"""Test selectNoticeInfo"""
		result = eTIMS.selectNoticeInfo("NOTICE123")
		self.assertIsInstance(result, dict)

	def test_select_org_usr_info(self):
		"""Test selectOrgUsrInfo"""
		result = eTIMS.selectOrgUsrInfo()
		self.assertIsInstance(result, dict)


class TestETimsWhitelistedMethods(FrappeTestCase):
	"""Test cases for whitelisted wrapper methods"""

	def setUp(self):
		"""Set up test fixtures"""
		frappe.flags.in_test = True

	def test_search_item_req(self):
		"""Test searchItemReq whitelisted method"""
		result = searchItemReq()
		self.assertIsInstance(result, dict)

	def test_select_item_req(self):
		"""Test selectItemReq whitelisted method"""
		result = selectItemReq("TEST_ITEM_CODE")
		self.assertIsInstance(result, dict)

	def test_search_stock_move_req(self):
		"""Test searchStockMoveReq whitelisted method"""
		result = searchStockMoveReq()
		self.assertIsInstance(result, dict)

	def test_search_sales_trns_req(self):
		"""Test searchSalesTrnsReq whitelisted method"""
		result = searchSalesTrnsReq()
		self.assertIsInstance(result, dict)

	def test_select_sales_trns_info_req(self):
		"""Test selectSalesTrnsInfoReq whitelisted method"""
		result = selectSalesTrnsInfoReq("12345")
		self.assertIsInstance(result, dict)

	def test_search_purchase_trns_req(self):
		"""Test searchPurchaseTrnsReq whitelisted method"""
		result = searchPurchaseTrnsReq()
		self.assertIsInstance(result, dict)

	def test_select_purchase_trns_info_req(self):
		"""Test selectPurchaseTrnsInfoReq whitelisted method"""
		result = selectPurchaseTrnsInfoReq("12345")
		self.assertIsInstance(result, dict)

	def test_sync_stock_release_number(self):
		"""Test sync_stock_release_number whitelisted method"""
		result = sync_stock_release_number(12345, 0, "11")
		self.assertIsInstance(result, dict)

	def test_search_stock_release_no_req(self):
		"""Test search_stock_release_no whitelisted method"""
		result = search_stock_release_no()
		self.assertIsInstance(result, dict)

	def test_get_stock_release_list(self):
		"""Test get_stock_release_list whitelisted method"""
		result = get_stock_release_list()
		self.assertIsInstance(result, dict)

	def test_get_org_user_info(self):
		"""Test get_org_user_info whitelisted method"""
		result = get_org_user_info()
		self.assertIsInstance(result, dict)
