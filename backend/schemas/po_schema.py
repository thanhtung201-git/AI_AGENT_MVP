from typing import List, Optional, Dict
from pydantic import BaseModel, Field

class POItem(BaseModel):
    """Schema representing a single item/style in the Purchase Order."""
    style_code: Optional[str] = Field(None, description="Buyer's style code")
    style_name: Optional[str] = Field(None, description="Style name/description")
    color_code: Optional[str] = Field(None, description="Color code")
    color_name: Optional[str] = Field(None, description="Full color name")
    composition: Optional[str] = Field(None, description="Fabric composition")
    size_breakdown: Optional[Dict[str, int]] = Field(None, description="Quantities per size. Key: size name, Value: quantity")
    total_quantity: Optional[int] = Field(None, description="Total quantity of this item")
    unit_price: Optional[float] = Field(None, description="Unit price without currency")
    total_price: Optional[float] = Field(None, description="Total price (unit_price * total_quantity)")

class POData(BaseModel):
    """Schema representing the complete extracted Purchase Order data."""
    po_number: Optional[str] = Field(None, description="Purchase Order Number")
    buyer: Optional[str] = Field(None, description="Buyer Company Name")
    seller: Optional[str] = Field(None, description="Seller Company Name")
    order_date: Optional[str] = Field(None, description="Order Date (YYYY-MM-DD)")
    delivery_date: Optional[str] = Field(None, description="Delivery Date (YYYY-MM-DD)")
    ship_date: Optional[str] = Field(None, description="Ship Date (YYYY-MM-DD)")
    payment_terms: Optional[str] = Field(None, description="Payment Terms")
    incoterm: Optional[str] = Field(None, description="Incoterm (e.g., FOB, CIF)")
    port_of_loading: Optional[str] = Field(None, description="Port of Loading")
    port_of_discharge: Optional[str] = Field(None, description="Port of Discharge")
    currency: Optional[str] = Field(None, description="Currency (e.g., USD, EUR)")
    season: Optional[str] = Field(None, description="Season")
    
    items: List[POItem] = Field(default_factory=list, description="List of items in the PO")
    
    total_quantity_all: Optional[int] = Field(None, description="Total quantity across all items")
    total_amount: Optional[float] = Field(None, description="Total monetary amount across all items")
    factory: Optional[str] = Field(None, description="Factory / Vendor name")
    style_name: Optional[str] = Field(None, description="Style / Product name")
    notes: Optional[str] = Field(None, description="Special notes or special instructions")
