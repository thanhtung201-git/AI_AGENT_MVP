# Input

## Purpose

The Purchase Order Extraction AI Agent accepts Purchase Orders from multiple input sources. Although the first version focuses on file uploads, the system is designed to support additional data sources in the future.

| Input Source        | Supported |
| ------------------- | --------- |
| PDF                 | ✅         |
| Scanned PDF         | ✅         |
| Excel (.xlsx, .xls) | ✅         |
| Word (.docx)        | ✅         |
| Email Attachment    | Future    |
| SharePoint          | Future    |

## Description

### PDF

* Native PDF exported from ERP or customer systems.
* Text can be extracted directly.

### Scanned PDF

* Image-based PDF.
* Requires OCR before information extraction.

### Excel

* Purchase Orders provided as spreadsheets.
* Data can be read directly from worksheets.

### Word

* Purchase Orders created in Microsoft Word.
* Text and tables need to be parsed.

### Email Attachment (Future)

* Automatically monitor a mailbox.
* Download Purchase Order attachments.
* Send documents to the AI Agent for processing.

### SharePoint (Future)

* Monitor a SharePoint folder.
* Detect newly uploaded Purchase Orders.
* Automatically process new files.

## Initial Scope

Version 1 of the system will support:

* ✅ PDF
* ✅ Scanned PDF
* ✅ Excel
* ✅ Word

Email and SharePoint integration will be considered in future releases.
