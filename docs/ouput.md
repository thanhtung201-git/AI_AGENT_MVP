# Output

## Purpose

After processing a Purchase Order, the AI Agent generates structured outputs that can be used by downstream business systems and human reviewers.

```text
Purchase Order
      │
      ▼
AI Agent
      │
      ▼
Structured JSON
      │
      ├────────► GO
      │
      ├────────► Trimlist
      │
      ├────────► Validation Report
      │
      └────────► Excel (Optional Export)
```

---

## Output Types

| Output            | Purpose                                                              |
| ----------------- | -------------------------------------------------------------------- |
| JSON              | Standardized business data extracted from the Purchase Order         |
| GO                | Data used to create a Garment Order                                  |
| Trimlist          | Data used to generate the Trimlist                                   |
| Validation Report | Review extracted data and highlight missing or low-confidence fields |
| Excel (Optional)  | Export structured data for reporting or manual processing            |

---

## Output Description

### JSON

The primary output of the AI Agent.

Contains all extracted Purchase Order information in a standardized format.

Example:

```json
{
  "header": {
    "po_number": "PO-001",
    "buyer": "ABC Fashion"
  },
  "items": [
    {
      "style": "TS-1001",
      "color": "Black",
      "qty": 1200
    }
  ],
  "shipping": {
    "delivery_date": "2026-08-15"
  },
  "notes": {
    "remark": "Pack by color"
  }
}
```

---

### GO

Structured data prepared for creating a Garment Order (GO) in the internal system.

---

### Trimlist

Structured data prepared for generating the Trimlist used by the production team.

---

### Validation Report

Provides quality checks for the extraction result, including:

* Missing required fields
* Invalid values
* Low-confidence predictions
* Fields requiring manual review

---

### Excel (Optional)

Exports the standardized data into an Excel file for users who need manual review, reporting, or integration with existing workflows.

---

## Initial Scope

Version 1 of the system will generate:

* ✅ JSON
* ✅ GO Data
* ✅ Trimlist Data
* ✅ Validation Report

Excel export can be added as an optional feature if required.
