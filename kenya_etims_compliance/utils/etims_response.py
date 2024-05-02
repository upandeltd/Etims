# Copyright (c) 2023, Upande Ltd and Contributors
# See license.txt

import frappe

@frappe.whitelist(allow_guest=True)
def selectInitOsdcInfo():
    
    return {"resultCd":"000",
            "resultMsg":"It is succeeded",
            "resultDt":"20200226143124", 
            "data":{
                "info":{
                    "tin":"A123456789Z",
                    "taxprNm":"Taxpayer1130",
                    "bsnsActv":"business",
                    "bhfId":"00",
                    "bhfNm":"Headquater",
                    "bhfOpenDt":"20200226",
                    "prvncNm":"NAIROBICITY",
                    "dstrtNm":"WESTLANDS",
                    "sctrNm":"WON",
                    "locDesc":"WestlandsTowers",
                    "hqYn":"Y",
                    "mgrNm":"manage1130_00",
                    "mgrTelNo":"0789001130",
                    "mgrEmail":"manage113000@test.com",
                    "dvcId":"9999911300000001",
                    "sdcId":"KRACU0300000222",
                    "mrcNo":"WIS01000150",
                    "cmcKey":"F7EAB71D774C40B5A954F8FF2B9408B10D6CBFA336FB429AB666"
                    }
                }
            }
    
@frappe.whitelist(allow_guest=True)
def selectCustomer():
    
    return {"resultCd":"000",
            "resultMsg":"It is succeeded",
            "resultDt":"20200226192053",
            "data":{
                "custList":[{
                    "tin":"A123456789Z",
                    "taxprNm":"TAXPAYER1",
                    "taxprSttsCd":"A",
                    "prvncNm":"NAIROBICITY",
                    "dstrtNm":"WESTLANDS",
                    "sctrNm":"WON",
                    "locDesc":" Westlands Towers"
                    }]
                }
            }

@frappe.whitelist(allow_guest=True)
def selectImportItemList():
    return {
        "resultCd":"000",
        "resultMsg":"It is succeeded",
        "resultDt":"20200226194118",
        "data":{
            "itemList":[
                {
                    "taskCd":"12778189",
                    "dclDe":"01042023",
                    "itemSeq":1,
                    "dclNo":"C3460-2019- TZDN",
                    "hsCd":"20055200000",
                    "itemNm":"Trousers Large",
                    "imptItemsttsCd":"2",
                    "orgnNatCd":"BR",
                    "exptNatCd":"BR",
                    "pkg":2922,
                    "pkgUnitCd":"",
                    "qty":19946,
                    "qtyUnitCd":"KGM",
                    "totWt":19945.57,
                    "netWt":19945.57,
                    "spplrNm":"ODERICH CONSERVA QUALIDADE\nBRASIL",
                    "agntNm":"BN METRO Ltd",
                    "invcFcurAmt":296865.6,
                    "invcFcurCd":"USD",
                    "invcFcurExcrt":100.79
                    },
                    {
                    "taskCd":"22398999",
                    "dclDe":"01022023",
                    "itemSeq":1,
                    "dclNo":"C3460-2019- TZDL",
                    "hsCd":"20055900000",
                    "itemNm":"Carpet Small",
                    "imptItemsttsCd":"2",
                    "orgnNatCd":"BR",
                    "exptNatCd":"BR",
                    "pkg":3500,
                    "pkgUnitCd":"",
                    "qty":19946,
                    "qtyUnitCd":"KGM",
                    "totWt":19945.57,
                    "netWt":19945.57,
                    "spplrNm":"ODERICH CONSERVA QUALIDADE\nBRASIL",
                    "agntNm":"BN METRO Ltd",
                    "invcFcurAmt":296865.6,
                    "invcFcurCd":"USD",
                    "invcFcurExcrt":150.79
                    }
                ]
            }
        }
    
    
@frappe.whitelist(allow_guest=True) 
def selectStockMoveList():
    return {"resultCd":"000",
            "resultMsg":"It is succeeded",
            "resultDt":"20200226200723",
            "data":{
                "stockList":[
                    {
                        "custTin":"P051304671B",
                        "custBhfId":"00",
                        "sarNo":199,
                        "ocrnDt":"20200120",
                        "totItemCnt":1,
                        "totTaxblAmt":1800000,
                        "totTaxAmt":274576.27,
                        "totAmt":1800000,
                        "remark":"",
                        "itemList":[
                            {
                                "itemSeq":1,
                                "itemCd":"KR2BZCAX0000001",
                                "itemClsCd":"1110162100",
                                "itemNm":"Grocery_Item#3",
                                "bcd":"8801234567051",
                                "pkgUnitCd":"BZ",
                                "pkg":0,
                                "qtyUnitCd":"CA",
                                "qty":450,
                                "itemExprDt":"20200226200723",
                                "prc":4000,
                                "splyAmt":1800000,
                                "totDcAmt":0,
                                "taxblAmt":1800000,
                                "taxTyCd":"B",
                                "taxAmt":274576.27,
                                "totAmt":1800000
                            }
                        ]
                    },
                    {
                        "custTin":"P051304671B",
                        "custBhfId":"01",
                        "sarNo":89,
                        "ocrnDt":"20200110",
                        "totItemCnt":1,
                        "totTaxblAmt":660000,
                        "totTaxAmt":100677.97,
                        "totAmt":660000,
                        "remark":"",
                        "itemList":[
                            {
                                "itemSeq":1,
                                "itemCd":"KR2AMXCRX0000001",
                                "itemClsCd":"1110151600",
                                "itemNm":"sample_nudle#1",
                                "bcd":"8801234567001",
                                "pkgUnitCd":"AM",
                                "pkg":0,
                                "qtyUnitCd":"CR",
                                "qty":600,
                                "itemExprDt":"",
                                "prc":1100,
                                "splyAmt":660000,
                                "totDcAmt":0,
                                "taxblAmt":660000,
                                "taxTyCd":"B",
                                "taxAmt":100677.97,
                                "totAmt":660000
                            }
                        ]
                    }
                ]
            }}
    
@frappe.whitelist(allow_guest=True) 
def selectTrnsPurchaseSalesList():
    return {"resultCd":"000",
            "resultMsg":"It is succeeded",
            "resultDt":"20200226195420",
            "data":{
                "saleList":[
                    {
                        "spplrTin":"A123456789Z",
                        "spplrNm":"Taxpayer1111",
                        "spplrBhfId":"00",
                        "spplrInvcNo":729,
                        "rcptTyCd":"S",
                        "pmtTyCd":"01",
                        "cfmDt":"2020-01-27 21:03:00",
                        "salesDt":"20200127",
                        "stockRlsDt":"2020-01-27 21:03:00",
                        "totItemCnt":2,
                        "taxblAmtA":0,
                        "taxblAmtB":10500,
                        "taxblAmtC":0,
                        "taxblAmtD":0,
                        "taxblAmtE":0,
                        "taxRtA":0,
                        "taxRtB":18,
                        "taxRtC":0,
                        "taxRtD":0,
                        "taxRtE":0,
                        "taxAmtA":0,
                        "taxAmtB":1602,
                        "taxAmtC":0,
                        "taxAmtD":0,
                        "taxAmtE":0,
                        "totTaxblAmt":10500,
                        "totTaxAmt":1602,
                        "totAmt":10500,
                        "remark": "",
                        "itemList":[
                            {
                                "itemSeq":1,
                                "itemCd":"ZR1NTXU0000001",
                                "itemClsCd":"5059690800",
                                "itemNm":"Zesta Mustard",
                                "bcd":"",
                                "pkgUnitCd":"NT",
                                "pkg":4,
                                "qtyUnitCd":"U",
                                "qty":2,
                                "prc":1740,
                                "splyAmt":7000,
                                "dcRt":0,
                                "dcAmt":0,
                                "taxTyCd":"B",
                                "taxblAmt":0,
                                "taxAmt":1068,
                                "totAmt":3480
                            }, 
                            {
                                "itemSeq":2,
                                "itemCd":"KE1NTXU0000002",
                                "itemClsCd":"5022110801",
                                "itemNm":"Peanut Butter",
                                "bcd":"",
                                "pkgUnitCd":"NT",
                                "pkg":4,
                                "qtyUnitCd":"U",
                                "qty":3,
                                "prc":3500,
                                "splyAmt":3500,
                                "dcRt":0,
                                "dcAmt":0,
                                "taxTyCd":"B",
                                "taxblAmt":3500,
                                "taxAmt":534,
                                "totAmt":3500
                            }
                        ]
                    }
                ]
            }
        }