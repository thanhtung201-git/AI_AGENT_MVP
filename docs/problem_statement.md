# Problem Statement

# Purchase Order Extraction AI Agent

## Current Situation

The merchandising team currently processes Purchase Orders (POs) manually.

For every new PO, employees must:

1. Open the Purchase Order file (PDF, Excel, or Image).
2. Read customer information.
3. Extract style information.
4. Read color and size breakdown.
5. Extract quantity information.
6. Read trim and packaging requirements.
7. Manually enter the extracted data into internal systems.
8. Create GO (Garment Order).
9. Create Trimlist.

This workflow is repetitive, time-consuming, and highly dependent on human effort.

## Problems

The current manual process introduces several challenges:

* Manual data entry is slow.
* Human errors frequently occur.
* Different PO formats require different handling methods.
* Large Purchase Orders take a significant amount of time to process.
* Employees spend more time reading documents than performing value-added tasks.
* The extracted data is not standardized across customers.

## Solution

Develop an AI Agent that automatically reads Purchase Orders from multiple formats and extracts structured information.

The AI Agent will:

* Read PDF, Excel, and image-based Purchase Orders.
* Understand different customer templates.
* Extract all required business fields.
* Convert the extracted information into a standardized JSON format.
* Generate data for GO creation.
* Generate data for Trimlist creation.
* Provide confidence scores for extracted fields.
* Allow human review before exporting the final result.

## Expected Benefits

* Reduce manual processing time.
* Minimize human errors.
* Standardize extracted data.
* Support multiple customer PO templates.
* Increase productivity for the merchandising team.
* Build a scalable foundation for future automation workflows.
