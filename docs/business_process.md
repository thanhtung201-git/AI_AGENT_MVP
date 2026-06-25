# Business Process

# Purchase Order Extraction AI Agent

## Current Business Process (As-Is)

The current Purchase Order processing workflow is performed manually by the merchandising team.

```text
Customer
    │
    ▼
Send Purchase Order
(PDF / Excel / Image)
    │
    ▼
Merchandiser opens the file
    │
    ▼
Read customer information
    │
    ▼
Read style information
    │
    ▼
Read color & size breakdown
    │
    ▼
Read quantity information
    │
    ▼
Read trim & packing requirements
    │
    ▼
Manually input data into ERP
    │
    ▼
Create GO
(Garment Order)
    │
    ▼
Create Trimlist
    │
    ▼
Review & Correct Errors
```

### Pain Points

* Manual reading consumes a significant amount of time.
* Repetitive data entry increases the risk of human error.
* Different customer PO templates require different handling.
* Large Purchase Orders are difficult to process efficiently.
* The process depends heavily on experienced merchandisers.

---

# Future Business Process (To-Be)

After implementing the AI Agent, the workflow becomes largely automated.

```text
Customer
    │
    ▼
Upload Purchase Order
    │
    ▼
AI Agent
    │
    ▼
Read PO
    │
    ▼
Extract Required Information
    │
    ▼
Standardize Output
(JSON)
    │
    ▼
Generate GO Data
    │
    ▼
Generate Trimlist Data
    │
    ▼
Human Review
    │
    ▼
Export to ERP
```

---

## AI Agent Responsibilities

The AI Agent is responsible for:

* Reading Purchase Orders in multiple formats.
* Understanding different customer layouts.
* Extracting structured business information.
* Validating extracted data.
* Producing standardized JSON output.
* Preparing data for GO creation.
* Preparing data for Trimlist creation.

---

## Human Responsibilities

The merchandiser will focus on:

* Reviewing AI-generated results.
* Correcting uncertain fields when necessary.
* Approving the final output.
* Exporting validated data to downstream systems.

---

## Expected Business Improvements

| Current Process            | AI-assisted Process              |
| -------------------------- | -------------------------------- |
| Manual document reading    | Automatic document understanding |
| Manual data entry          | Automatic data extraction        |
| High error rate            | Reduced human errors             |
| Slow processing            | Faster turnaround time           |
| Template-specific workflow | Multi-template support           |
| Repetitive work            | Human review only                |
