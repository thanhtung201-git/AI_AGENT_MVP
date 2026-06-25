# Input Output Analysis

## Data Flow Diagram

```text
                User
                  │
            Upload PO
                  │
                  ▼
          Reader Module
                  │
            Raw Text
                  │
                  ▼
       Extraction Module
                  │
            Raw JSON
                  │
                  ▼
       Normalizer Module
                  │
         Canonical JSON
                  │
                  ▼
       Validation Module
                  │
        Validated JSON
                  │
                  ▼
    Excel Generator Module
                  │
            Excel Output
```

---

## Module 1 - Reader

### Responsibility

Read Purchase Order documents from different file formats and convert them into plain text.

### Input

* PDF
* Scanned PDF
* Excel
* Word

### Output

* Raw Text

---

## Module 2 - Extractor

### Responsibility

Extract business information from the raw text using AI.

### Input

* Raw Text

### Output

* Raw JSON

Example:

```json
{
  "po_number": "...",
  "buyer": "...",
  "style": "...",
  "qty": "..."
}
```

---

## Module 3 - Normalizer

### Responsibility

Transform the extracted JSON into a standardized business schema.

### Input

* Raw JSON

### Output

* Canonical JSON

Example:

```json
{
  "header": {
    "po_number": "...",
    "buyer": "..."
  },
  "items": [
    {
      "style": "...",
      "color": "...",
      "qty": 1000
    }
  ]
}
```

---

## Module 4 - Validator

### Responsibility

Validate the normalized data before it is used by downstream systems.

### Input

* Canonical JSON

### Output

* Validated JSON

Validation includes:

* Required fields
* Data types
* Missing values
* Business rules
* Confidence checks

---

## Module 5 - Excel Generator

### Responsibility

Generate business deliverables from the validated data.

### Input

* Validated JSON

### Output

* Excel
* GO Data
* Trimlist Data

---

## Summary

| Module          | Input                         | Output                        |
| --------------- | ----------------------------- | ----------------------------- |
| Reader          | PDF, Scanned PDF, Excel, Word | Raw Text                      |
| Extractor       | Raw Text                      | Raw JSON                      |
| Normalizer      | Raw JSON                      | Canonical JSON                |
| Validator       | Canonical JSON                | Validated JSON                |
| Excel Generator | Validated JSON                | Excel, GO Data, Trimlist Data |
