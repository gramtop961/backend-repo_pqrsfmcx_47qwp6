import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Header, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson.objectid import ObjectId
from email.message import EmailMessage
import smtplib

from database import db, create_document, get_documents
from schemas import Product, Business, InkOrder

app = FastAPI(title="Laxmi Enterprise API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- Utilities ----------

def _collection(name: str):
    return db[name]

ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "changeme")

async def verify_admin(x_admin_token: Optional[str]):
    if not x_admin_token or x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")

# ---------- Public Endpoints ----------

@app.get("/")
def root():
    return {"message": "Laxmi Enterprise Backend running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

@app.get("/products", response_model=List[Product])
def list_products(category: Optional[str] = None):
    filt = {"category": category} if category else {}
    docs = get_documents("product", filt)
    # Convert to Product-friendly dicts (remove _id)
    out = []
    for d in docs:
        d.pop("_id", None)
        out.append(Product(**d))
    return out

@app.get("/business", response_model=Optional[Business])
def get_business_details():
    docs = get_documents("business", {})
    if not docs:
        return None
    d = docs[0]
    d.pop("_id", None)
    return Business(**d)

# ---------- Email Sending ----------

def send_order_email(order: InkOrder, business: Business):
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASSWORD")
    use_tls = os.getenv("SMTP_TLS", "true").lower() in ("1", "true", "yes")

    if not smtp_host or not business.email:
        raise RuntimeError("Email is not configured. Set SMTP_* env vars and business email.")

    msg = EmailMessage()
    msg["Subject"] = f"New Ink Order: {order.color} - {order.quantity_liters} L"
    msg["From"] = smtp_user if smtp_user else business.email
    msg["To"] = business.email

    body = (
        f"New Ink Order Received\n\n"
        f"Customer: {order.customer_name}\n"
        f"Email: {order.customer_email}\n"
        f"Phone: {order.customer_phone or '-'}\n\n"
        f"Color: {order.color}\n"
        f"Quantity (L): {order.quantity_liters}\n"
        f"Delivery Address: {order.delivery_address or '-'}\n\n"
        f"Message:\n{order.message or '-'}\n"
    )
    msg.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        if use_tls:
            server.starttls()
        if smtp_user and smtp_pass:
            server.login(smtp_user, smtp_pass)
        server.send_message(msg)

@app.post("/orders/ink")
def create_ink_order(order: InkOrder, background_tasks: BackgroundTasks):
    # Store order
    create_document("inkorder", order)
    # Fetch business email
    business_docs = get_documents("business", {})
    if not business_docs:
        # Order stored, but cannot email without business configured
        return {"status": "stored", "email": "not_configured"}
    business = Business(**{k: v for k, v in business_docs[0].items() if k != "_id"})
    # Send email in background
    try:
        background_tasks.add_task(send_order_email, order, business)
    except Exception:
        # ignore email config errors here; order is stored
        pass
    return {"status": "ok"}

# ---------- Admin Endpoints ----------

class AdminProduct(Product):
    id: Optional[str] = None

@app.get("/admin/products")
def admin_list_products(x_admin_token: Optional[str] = Header(None)):
    # auth
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    docs = get_documents("product", {})
    # include _id as string
    out = []
    for d in docs:
        d["id"] = str(d.get("_id"))
        d.pop("_id", None)
        out.append(d)
    return out

@app.post("/admin/products")
def admin_create_product(product: Product, x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    inserted_id = create_document("product", product)
    return {"id": inserted_id}

@app.put("/admin/products/{product_id}")
def admin_update_product(product_id: str, product: Product, x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    res = _collection("product").update_one({"_id": ObjectId(product_id)}, {"$set": {**product.model_dump()}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"updated": True}

@app.delete("/admin/products/{product_id}")
def admin_delete_product(product_id: str, x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=400, detail="Invalid ID")
    res = _collection("product").delete_one({"_id": ObjectId(product_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Not found")
    return {"deleted": True}

@app.get("/admin/business")
def admin_get_business(x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    docs = get_documents("business", {})
    if not docs:
        return None
    d = docs[0]
    d["id"] = str(d.get("_id"))
    d.pop("_id", None)
    return d

@app.put("/admin/business")
def admin_upsert_business(business: Business, x_admin_token: Optional[str] = Header(None)):
    if x_admin_token != ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")
    docs = get_documents("business", {})
    if not docs:
        create_document("business", business)
        return {"created": True}
    _id = docs[0]["_id"]
    _collection("business").update_one({"_id": _id}, {"$set": {**business.model_dump()}})
    return {"updated": True}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
