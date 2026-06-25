# Canonical Schema

## Purpose

The Canonical Schema defines the standardized data structure used throughout the Purchase Order Extraction AI Agent.

Regardless of the original Purchase Order format, all extracted data must be normalized into this schema before validation and downstream processing.

---

## MVP JSON Schema

```json
{
  "po_number": "",
  "buyer": "",
  "orders": [
    {
      "style": "",
      "color": "",
      "sizes": {},
      "total_qty": 0,
      "unit_price": null,
      "delivery_date": ""
    }
  ],
  "notes": ""
}
```

---

## Header

| Field     | Type   | Required |
| --------- | ------ | -------- |
| po_number | string | Yes      |
| buyer     | string | Yes      |
| po_date   | string | No       |
| currency  | string | No       |

---

## Orders

| Field         | Type    | Required |
| ------------- | ------- | -------- |
| style         | string  | Yes      |
| color         | string  | Yes      |
| sizes         | object  | No       |
| total_qty     | integer | Yes      |
| unit_price    | number  | No       |
| delivery_date | string  | Yes      |

---

## Notes

| Field | Type   | Required |
| ----- | ------ | -------- |
| notes | string | No       |

---

## Mapping Rules

Different customers may use different field names for the same business concept.

| Buyer Field       | Canonical Field |
| ----------------- | --------------- |
| PO No             | po_number       |
| Purchase Order No | po_number       |
| Buyer             | buyer           |
| Customer          | buyer           |
| Colour            | color           |
| Shade             | color           |
| Qty               | total_qty       |
| Order Qty         | total_qty       |
| Delivery          | delivery_date   |
| Delivery Date     | delivery_date   |

---

## Design Principles

* Keep the schema simple for the MVP.
* Use consistent field names across all customer templates.
* Allow multiple order items in a single Purchase Order.
* Support flexible size breakdown through the `sizes` object.
* Make optional fields nullable when information is unavailable.
* Ensure the schema can be extended without breaking existing integrations.

---

## Future Extensions

The following fields may be added in future versions:

* Vendor
* Factory
* Brand
* Season
* Country of Origin
* Incoterms
* Shipment Method
* Packaging Details
* Purchase Order Status
* Confidence Score

```
```
