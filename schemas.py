from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List

class Product(BaseModel):
    title: str = Field(..., description="Product title")
    description: Optional[str] = Field(None, description="Product description")
    price: float = Field(..., ge=0, description="Price in rupees")
    category: str = Field(..., description="Product category (e.g., home, ink)")
    in_stock: bool = Field(True, description="Whether product is in stock")
    image_url: Optional[str] = Field(None, description="Image URL")

class Business(BaseModel):
    name: str = Field(..., description="Business name")
    email: EmailStr = Field(..., description="Primary business email")
    phone: Optional[str] = Field(None, description="Contact phone number")
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

class InkOrder(BaseModel):
    customer_name: str = Field(...)
    customer_email: EmailStr
    customer_phone: Optional[str] = None
    color: str = Field(..., description="Ink color: Red or Blue")
    quantity_liters: float = Field(..., gt=0)
    message: Optional[str] = None
    delivery_address: Optional[str] = None

class AdminAuth(BaseModel):
    token: str
