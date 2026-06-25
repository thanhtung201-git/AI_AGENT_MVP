import pandas as pd
import os
from backend.schemas.po_schema import POData

class ExcelExporter:
    """Exports POData to an Excel file using Pandas and OpenPyXL."""
    
    @staticmethod
    def export(po_data: POData, output_path: str):
        # Flatten the PO data for Excel
        # For simplicity, we create a rows for each size in the size_breakdown of each item
        rows = []
        
        base_info = {
            "PO Number": po_data.po_number,
            "Buyer": po_data.buyer,
            "Seller": po_data.seller,
            "Order Date": po_data.order_date,
            "Delivery Date": po_data.delivery_date,
            "Ship Date": po_data.ship_date,
            "Payment Terms": po_data.payment_terms,
            "Incoterm": po_data.incoterm,
            "Port of Loading": po_data.port_of_loading,
            "Port of Discharge": po_data.port_of_discharge,
            "Currency": po_data.currency,
            "Season": po_data.season,
            "Notes": po_data.notes
        }
        
        for item in po_data.items:
            item_info = {
                "Style Code": item.style_code,
                "Style Name": item.style_name,
                "Color Code": item.color_code,
                "Color Name": item.color_name,
                "Composition": item.composition,
                "Unit Price": item.unit_price,
            }
            
            if item.size_breakdown:
                for size_name, qty in item.size_breakdown.items():
                    row = {**base_info, **item_info}
                    row["Size"] = size_name
                    row["Quantity"] = qty
                    row["Total Price"] = (item.unit_price * qty) if item.unit_price else None
                    rows.append(row)
            else:
                row = {**base_info, **item_info}
                row["Size"] = "N/A"
                row["Quantity"] = item.total_quantity
                row["Total Price"] = item.total_price
                rows.append(row)
                
        df = pd.DataFrame(rows)
        
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        df.to_excel(output_path, index=False)
