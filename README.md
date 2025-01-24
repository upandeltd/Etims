<div align="center"> 
<h1>eTIMS</h1>
</div>
eTIMS (electronic Tax Invoice Management System) is a module that integrates seamlessly with Frappe and ERPNext, providing taxpayers with a simple, convenient, and flexible solution for electronic invoicing while streamlining tax invoicing, inventory management, and sales processes. 

This integration helps businesses streamline tax invoicing while ensuring compliance with the electronic Tax Invoice Management System (eTIMS). It automates tax reporting, reduces errors, and simplifies daily operations such as inventory, sales, purchases, and stock transfers. All transactions are seamlessly reported to eTIMS for accurate and efficient record-keeping. 

For more information on ERPNext setup, visit:
- [Frappe Framework Introduction](https://frappeframework.com/docs/user/en/introduction) 
- [ERPNext Documentation](https://docs.erpnext.com/) 

## Key Features:

- **Tax Compliance**: Ensures adherence to local tax regulations through seamless integration with eTIMS. 
- **User-Friendly Interface**: Provides an intuitive workspace for efficient navigation and operations. 
- **Seamless Sales and Purchase Management**: Facilitates easy management of transactions with automated data exchange. 
- **Automation and Compliance**: Streamlines tax reporting and compliance tasks through automated processes. 
- **Tax Branch and User Information Management**: Enables efficient handling of tax branch details and user registrations. 
- **Sensitive Tax Data Management**: Ensures secure management of critical tax-related data. 
- **Seamless Communication Between ERPNext and eTIMS**: Enables real-time synchronization of data between the two systems. 

<br>  

<div align="center"><h1>Documentation</h1></div>

## Installation 

#### PyQRCode 1.2.1  
```python3 -m pip install pyqrcode```  

#### Get Kenya Etims Compliance  
```bench get-app https://github.com/upandeltd/Etims```  

#### Install app in site
```bench --site <site-name> install-app kenya_etims_compliance```  

<br> 

## Getting Started 
### eTIMS Compliance Workspace 
After logging in with the required permissions for eTIMS integration, users will be redirected to the eTIMS Compliance Workspace, where resources for integration can be accessed. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-16-55.png) 

### Company PIN Setup 
1. Access the company doctype via the Accounting workspace or search using the awesome-bar. 
2. Create or edit existing companies and set the company KRA PIN in the “Tax ID” field. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2016-22-36.png) 
---

## Details of ERPNext and eTIMS Integration 

### Device Initialization 
1. Navigate to "Add TIS Device Initialization." 
2. Select the company, and its PIN will auto-populate. 
3. Add details like the Tax Branch Office, device serial, and environment (e.g., "Sandbox" or "Production"). 
4. Click "Initialize Device" to complete the process.  

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-23-35.png) 

Additional settings:
- Configure warehouses for sales, stock, and purchases.
- Update the last invoice numbers if prior transactions exist in the eTIMS portal.

ERPNext sends the KRA details, and eTIMS responds with authenticated OSCU device information, which is stored in ERPNext. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-26-07.png) 

### Basic Data Management 
#### Get Code List 
1. Navigate to the "eTIMS Code Information" section in the eTIMS Compliance workspace. 
2. Input the start date for the search and click "Search Code." 
3. View the retrieved codes using the "View Search Response" button. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-29-04.png) 
#### Item Classification Search
1. Access "eTIMS Item Information" in the eTIMS Compliance workspace. 
2. Enter the desired date and time, then click "Search Item Classification." 
3. View retrieved data by clicking "View Response." 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-31-07.png) 

#### Get PIN Information
1. Navigate to "eTIMS Customer Search" in the eTIMS workspace. 
2. Enter the customer PIN and click "Search Customer." 
3. The customer information will appear in a table below. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-31-07.png) 


#### Search Branch Information 
1. Access the "eTIMS Branch Information" page in the eTIMS Compliance workspace. 
2. Enter the company PIN, date, and time to search. 
3. Branch information will be retrieved and displayed. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2016-34-31.png) 

#### Get Notices 
1. Navigate to "eTIMS Notice Search" under the eTIMS Code Information page. 
2. Input the search dates and click "Search Notice." 
3. Notices will populate in a table below. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2016-35-43.png)  
---

## Branch Information Management 

### Save Branch Customer 
1. Navigate to "Customer" in the Accounts workspace. 
2. Click "Add Customer" and fill in the required details. 
3. Click "Register Customer" to submit data to the eTIMS server. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2016-39-30.png) 

### Save Branch User 
1. Navigate to "eTIMS Branch User" in the eTIMS workspace. 
2. Click "Add eTIMS Branch User" and fill in the required fields. 
3. Click "Register User" to submit data to the eTIMS server. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2016-40-53.png) 

### Send Insurance Details 
1. Access "Insurance" in the eTIMS Compliance workspace. 
2. Click "Add New eTIMS Insurance," fill in the details, and save. 
3. Click "Update Branch Insurance Info" to update the eTIMS server.  

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2016-42-08.png) 
---

## Item Management 

### Item Registration 
1. Navigate to "Item" in the Stock workspace. 
2. Click "Add Item" and populate the necessary details (e.g., item name, unit price, tax template). 
3. Check "Update Item to TIMS" and save. 
4. Fill in the required eTIMS information and click "Register Item."  

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-34-07.png) 

### Item Composition 
1. Navigate to the "BOM" doctype under the Item Master workspace. 
2. Create a BOM record for the item. 
3. Click "Save Item Composition" to update the eTIMS server. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2016-44-18.png) 

### Get Item Information
1. Navigate to "eTIMS Item Information." 
2. Enter the date and time for the search and click "Request Items." 
3. Retrieved items will populate in a table below. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-32-17.png) 
---

## Imported Item Management 

### Get Imported Item Information 
1. Navigate to "eTIMS Import Item Information." 
2. Enter the search date and time, then click "Search Import Items." 
3. Retrieved items will appear in the "eTIMS Import Item" section. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-47-47.png) 

### Update Imported Item Information 
1. Navigate to the imported item in the Item Master. 
2. Map updated import data to the item and click "Update Item." 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2015-49-14.png) 
---

## Sales Management 

### Send Sales Transaction Information 
1. Navigate to "Sales Invoice" in the Accounting workspace. 
2. Create and fill out a sales invoice, ensuring eTIMS data is complete. 
3. Save and submit the document to send data to the eTIMS server. 
4. A QR code is generated for compliance. 

![Image](https://test.upande.com/files/Screenshot%20from%202025-01-24%2016-03-53.png) 

### Creating Return Invoice 
1. Open a submitted sales invoice and click "Create" > "Return/Credit Note." 
2. Edit item quantities or remove items as needed and save. 

---

<br> 

This document provides a comprehensive overview of the integration process between ERPNext and eTIMS, ensuring smooth operations and compliance with tax regulations.


