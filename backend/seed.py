"""Seed the Super Sale database with a realistic demo catalogue and sales history.

Run from the backend directory:

    python seed.py              # add demo data, keeping anything already there
    python seed.py --reset      # wipe products/sales/customers first

The script simulates ~45 days of trading so the dashboard charts, the 14-day
demand forecast and the monthly report all have something meaningful to show.
"""

from __future__ import annotations

import argparse
import asyncio
import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from motor.motor_asyncio import AsyncIOMotorClient

from app.config import get_settings
from app.database import ensure_default_users, ensure_indexes, ensure_store
from app.money import effective_price, q2

random.seed(20261002)

# Six months of trading. The IPF demand model needs enough windows to
# train on; 45 days left only a handful of usable anchors.
HISTORY_DAYS = 180

CATALOGUE = [
    # name, brand, barcode, category, buying, market, selling, discount,
    # shelf, warehouse, threshold, emoji
    #
    # A real Sri Lankan supermarket range: the same item is stocked under
    # several brands (milk powder in Anchor, Highland and Ratthi; cream
    # crackers in Maliban and Munchee), which is why `brand` is its own
    # field rather than part of the name. Barcodes use 479, Sri Lanka's GS1
    # country prefix. Prices are LKR at Colombo shelf levels, with margins
    # that follow the trade: staples thin, FMCG and fresh produce wider.
    ("Full Cream Milk Powder 400g", "Anchor", "4790000000001", "Dairy", 1380.00, 1620.00, 1560.00, 0.0, 95, 240, 50, "milk"),
    ("Full Cream Milk Powder 400g", "Highland", "4790000000002", "Dairy", 1320.00, 1550.00, 1490.00, 0.0, 80, 200, 45, "milk"),
    ("Full Cream Milk Powder 400g", "Ratthi", "4790000000003", "Dairy", 1270.00, 1500.00, 1440.00, 5.0, 60, 150, 40, "milk"),
    ("Full Cream Milk Powder 1kg", "Anchor", "4790000000004", "Dairy", 3250.00, 3780.00, 3650.00, 0.0, 40, 110, 25, "milk"),
    ("Full Cream Milk Powder 1kg", "Highland", "4790000000005", "Dairy", 3120.00, 3640.00, 3510.00, 0.0, 35, 95, 25, "milk"),
    ("Fresh Milk 1L", "Ambewela", "4790000000006", "Dairy", 430.00, 510.00, 490.00, 0.0, 70, 160, 40, "milk"),
    ("Fresh Milk 1L", "Highland", "4790000000007", "Dairy", 420.00, 500.00, 480.00, 0.0, 65, 150, 40, "milk"),
    ("Fresh Milk 1L", "Pelwatte", "4790000000008", "Dairy", 405.00, 485.00, 465.00, 10.0, 50, 120, 35, "milk"),
    ("Set Yoghurt (4 cups)", "Ambewela", "4790000000009", "Dairy", 260.00, 340.00, 320.00, 0.0, 55, 110, 30, "milk"),
    ("Set Yoghurt (4 cups)", "Highland", "4790000000010", "Dairy", 250.00, 330.00, 310.00, 0.0, 50, 100, 30, "milk"),
    ("Curd 500ml", "Pelwatte", "4790000000011", "Dairy", 290.00, 380.00, 360.00, 0.0, 40, 80, 25, "milk"),
    ("Butter 227g", "Anchor", "4790000000012", "Dairy", 980.00, 1240.00, 1180.00, 0.0, 30, 70, 20, "cheese"),
    ("Processed Cheese 200g", "Happy Cow", "4790000000013", "Dairy", 820.00, 1030.00, 980.00, 0.0, 28, 65, 20, "cheese"),
    ("Keeri Samba Rice 5kg", "Araliya", "4790000000014", "Rice & Grains", 2450.00, 2780.00, 2680.00, 0.0, 45, 140, 35, "rice"),
    ("Nadu Rice 5kg", "Araliya", "4790000000015", "Rice & Grains", 1750.00, 2000.00, 1920.00, 0.0, 60, 180, 45, "rice"),
    ("Nadu Rice 5kg", "Nipuna", "4790000000016", "Rice & Grains", 1700.00, 1950.00, 1870.00, 0.0, 55, 170, 45, "rice"),
    ("White Raw Rice 5kg", "CIC Golden Crop", "4790000000017", "Rice & Grains", 1820.00, 2080.00, 2000.00, 5.0, 40, 120, 35, "rice"),
    ("Red Raw Rice 5kg", "Harischandra", "4790000000018", "Rice & Grains", 1880.00, 2150.00, 2060.00, 0.0, 30, 90, 25, "rice"),
    ("Basmati Rice 1kg", "Keells", "4790000000019", "Rice & Grains", 780.00, 920.00, 880.00, 0.0, 35, 85, 25, "rice"),
    ("Mysore Dhal 1kg", "CIC", "4790000000020", "Rice & Grains", 620.00, 730.00, 700.00, 0.0, 70, 160, 40, "rice"),
    ("Chickpeas 500g", "Raigam", "4790000000021", "Rice & Grains", 310.00, 380.00, 360.00, 0.0, 60, 130, 35, "rice"),
    ("Wheat Flour 1kg", "Prima", "4790000000022", "Food Cupboard", 250.00, 290.00, 275.00, 0.0, 110, 280, 60, "flour"),
    ("Wheat Flour 1kg", "Pillsbury", "4790000000023", "Food Cupboard", 265.00, 310.00, 295.00, 0.0, 80, 200, 50, "flour"),
    ("White Sugar 1kg", "Lanka Sugar", "4790000000024", "Food Cupboard", 265.00, 305.00, 290.00, 0.0, 120, 300, 65, "sugar"),
    ("Coconut Oil 1L", "Marina", "4790000000025", "Food Cupboard", 1120.00, 1340.00, 1280.00, 0.0, 45, 110, 30, "oil"),
    ("Sunflower Oil 1L", "Happy Cook", "4790000000026", "Food Cupboard", 950.00, 1130.00, 1080.00, 0.0, 50, 120, 30, "oil"),
    ("Instant Noodles Chicken 80g", "Prima Kottumee", "4790000000027", "Food Cupboard", 95.00, 130.00, 120.00, 0.0, 220, 500, 90, "flour"),
    ("Instant Noodles Chicken 70g", "Maggi", "4790000000028", "Food Cupboard", 105.00, 140.00, 130.00, 0.0, 200, 460, 90, "flour"),
    ("Soya Meat Chicken 90g", "Raigam", "4790000000029", "Food Cupboard", 110.00, 150.00, 140.00, 0.0, 160, 380, 70, "flour"),
    ("Tomato Sauce 400g", "MD", "4790000000030", "Food Cupboard", 480.00, 610.00, 580.00, 0.0, 60, 140, 35, "sugar"),
    ("Chilli Sauce 400g", "Larich", "4790000000031", "Food Cupboard", 450.00, 570.00, 540.00, 0.0, 55, 130, 35, "sugar"),
    ("Mixed Fruit Jam 500g", "MD", "4790000000032", "Food Cupboard", 720.00, 900.00, 860.00, 0.0, 40, 95, 25, "sugar"),
    ("Chilli Powder 100g", "Ruhunu", "4790000000033", "Food Cupboard", 180.00, 235.00, 220.00, 0.0, 90, 210, 50, "sugar"),
    ("Curry Powder 100g", "Larich", "4790000000034", "Food Cupboard", 190.00, 250.00, 235.00, 0.0, 85, 200, 50, "sugar"),
    ("Canned Mackerel 425g", "Jeewa", "4790000000035", "Food Cupboard", 780.00, 970.00, 920.00, 0.0, 48, 120, 30, "meat"),
    ("Papadam 100g", "Harischandra", "4790000000036", "Food Cupboard", 160.00, 215.00, 200.00, 0.0, 70, 160, 40, "flour"),
    ("Ceylon Black Tea 400g", "Dilmah", "4790000000037", "Tea & Coffee", 1180.00, 1490.00, 1420.00, 0.0, 42, 100, 25, "tea"),
    ("Ceylon Black Tea 400g", "Zesta", "4790000000038", "Tea & Coffee", 1050.00, 1330.00, 1270.00, 10.0, 38, 95, 25, "tea"),
    ("BOPF Tea 200g", "Watawala", "4790000000039", "Tea & Coffee", 560.00, 710.00, 680.00, 0.0, 65, 150, 35, "tea"),
    ("Green Tea Bags (25)", "Mlesna", "4790000000040", "Tea & Coffee", 620.00, 800.00, 760.00, 0.0, 30, 70, 20, "tea"),
    ("Instant Coffee 100g", "Nescafe", "4790000000041", "Tea & Coffee", 1380.00, 1730.00, 1650.00, 0.0, 26, 60, 20, "coffee"),
    ("Cream Soda 1.5L", "Elephant House", "4790000000042", "Beverages", 370.00, 470.00, 450.00, 0.0, 95, 240, 55, "drink"),
    ("Necto 1.5L", "Elephant House", "4790000000043", "Beverages", 370.00, 470.00, 450.00, 0.0, 85, 220, 55, "drink"),
    ("Coca-Cola 1.5L", "Coca-Cola", "4790000000044", "Beverages", 390.00, 490.00, 470.00, 0.0, 100, 260, 60, "drink"),
    ("Sprite 1.5L", "Coca-Cola", "4790000000045", "Beverages", 390.00, 490.00, 470.00, 0.0, 80, 210, 55, "drink"),
    ("Orange Cordial 750ml", "MD", "4790000000046", "Beverages", 620.00, 790.00, 750.00, 0.0, 45, 110, 30, "drink"),
    ("Malted Drink 400g", "Nestomalt", "4790000000047", "Beverages", 1250.00, 1550.00, 1480.00, 0.0, 32, 80, 22, "drink"),
    ("Chocolate Malt 400g", "Milo", "4790000000048", "Beverages", 1320.00, 1630.00, 1560.00, 5.0, 30, 75, 22, "drink"),
    ("Drinking Water 5L", "Keells", "4790000000049", "Beverages", 235.00, 310.00, 290.00, 0.0, 75, 190, 45, "drink"),
    ("Cream Cracker 190g", "Maliban", "4790000000050", "Snacks", 280.00, 360.00, 340.00, 0.0, 120, 290, 60, "snack"),
    ("Cream Cracker 190g", "Munchee", "4790000000051", "Snacks", 275.00, 355.00, 335.00, 0.0, 115, 280, 60, "snack"),
    ("Marie Biscuit 400g", "Munchee", "4790000000052", "Snacks", 480.00, 610.00, 580.00, 0.0, 70, 170, 40, "snack"),
    ("Chocolate Bar 100g", "Kandos", "4790000000053", "Snacks", 365.00, 465.00, 440.00, 5.0, 95, 230, 50, "snack"),
    ("Chocolate Bar 85g", "Ritzbury", "4790000000054", "Snacks", 320.00, 410.00, 390.00, 0.0, 90, 220, 50, "snack"),
    ("Potato Chips 150g", "Lays", "4790000000055", "Snacks", 390.00, 500.00, 480.00, 0.0, 110, 260, 55, "snack"),
    ("Murukku 150g", "Keells", "4790000000056", "Snacks", 230.00, 305.00, 290.00, 0.0, 80, 180, 45, "snack"),
    ("Chicken Breast 1kg", "Crysbro", "4790000000057", "Meat & Fresh", 1360.00, 1750.00, 1680.00, 0.0, 22, 45, 18, "meat"),
    ("Chicken Drumsticks 1kg", "Bairaha", "4790000000058", "Meat & Fresh", 1180.00, 1520.00, 1460.00, 0.0, 20, 40, 18, "meat"),
    ("Chicken Sausages 400g", "Elephant House", "4790000000059", "Meat & Fresh", 780.00, 1010.00, 960.00, 0.0, 30, 65, 20, "meat"),
    ("Farm Eggs (10)", "Crysbro", "4790000000060", "Meat & Fresh", 500.00, 630.00, 600.00, 0.0, 48, 95, 30, "eggs"),
    ("Ambul Banana 1kg", None, "4790000000061", "Meat & Fresh", 240.00, 350.00, 320.00, 0.0, 50, 55, 25, "fruit"),
    ("Tomato 1kg", None, "4790000000062", "Meat & Fresh", 280.00, 420.00, 380.00, 0.0, 35, 45, 22, "veg"),
    ("Big Onion 1kg", None, "4790000000063", "Meat & Fresh", 320.00, 450.00, 420.00, 0.0, 60, 120, 35, "veg"),
    ("Potato 1kg", None, "4790000000064", "Meat & Fresh", 350.00, 480.00, 450.00, 0.0, 65, 130, 35, "veg"),
    ("Carrot 1kg", None, "4790000000065", "Meat & Fresh", 420.00, 580.00, 540.00, 0.0, 30, 50, 22, "veg"),
    ("Laundry Powder 1kg", "Sunlight", "4790000000066", "Household", 740.00, 930.00, 890.00, 0.0, 55, 135, 35, "soap"),
    ("Laundry Powder 1kg", "Rin", "4790000000067", "Household", 700.00, 890.00, 850.00, 0.0, 50, 125, 35, "soap"),
    ("Laundry Liquid 1L", "Surf Excel", "4790000000068", "Household", 1050.00, 1340.00, 1280.00, 10.0, 30, 75, 22, "soap"),
    ("Dishwash Liquid 750ml", "Vim", "4790000000069", "Household", 430.00, 560.00, 530.00, 15.0, 60, 145, 35, "soap"),
    ("Dishwash Bar 125g", "Sunlight", "4790000000070", "Household", 110.00, 150.00, 140.00, 0.0, 150, 340, 70, "soap"),
    ("Toilet Tissue (4 rolls)", "Keells", "4790000000071", "Household", 580.00, 760.00, 720.00, 0.0, 65, 155, 40, "home"),
    ("Garbage Bags (30)", "Keells", "4790000000072", "Household", 435.00, 570.00, 540.00, 0.0, 55, 130, 35, "home"),
    ("LED Bulb 9W", "Orange Electric", "4790000000073", "Household", 410.00, 550.00, 520.00, 0.0, 34, 80, 20, "home"),
    ("Mosquito Coil (10)", "Mortein", "4790000000074", "Household", 260.00, 350.00, 330.00, 0.0, 70, 165, 40, "home"),
    ("Bath Soap 100g", "Lifebuoy", "4790000000075", "Personal Care", 170.00, 225.00, 210.00, 0.0, 140, 320, 65, "care"),
    ("Bath Soap 100g", "Lux", "4790000000076", "Personal Care", 180.00, 235.00, 220.00, 0.0, 130, 300, 65, "care"),
    ("Baby Soap 100g", "Baby Cheramy", "4790000000077", "Personal Care", 210.00, 275.00, 260.00, 0.0, 70, 160, 40, "care"),
    ("Toothpaste 120g", "Signal", "4790000000078", "Personal Care", 470.00, 610.00, 580.00, 0.0, 60, 145, 35, "care"),
    ("Herbal Toothpaste 120g", "Sudanta", "4790000000079", "Personal Care", 440.00, 575.00, 545.00, 0.0, 45, 110, 30, "care"),
    ("Shampoo 180ml", "Sunsilk", "4790000000080", "Personal Care", 620.00, 800.00, 760.00, 10.0, 55, 130, 35, "care"),
    ("Shampoo 180ml", "Clinic", "4790000000081", "Personal Care", 640.00, 820.00, 780.00, 0.0, 50, 120, 32, "care"),
    ("Herbal Hair Oil 100ml", "Kumarika", "4790000000082", "Personal Care", 480.00, 620.00, 590.00, 0.0, 48, 115, 30, "care"),
]

RETURN_REASONS = [
    "Damaged packaging",
    "Customer changed their mind",
    "Wrong item picked",
    "Expired before use",
    "Duplicate purchase",
    "Faulty product",
]

CUSTOMERS = [
    # 50 Sri Lankan shoppers with local mobile numbers (+94 7X).
    ("Darshana Hemachandra", "+94701000000"),
    ("Kamal Gunarathne", "+94711073219"),
    ("Kasun Perera", "+94721146438"),
    ("Tharindu Wijesinghe", "+94741219657"),
    ("Nuwan Jayasinghe", "+94751292876"),
    ("Lahiru Fernando", "+94761366095"),
    ("Sandun Karunaratne", "+94771439314"),
    ("Isuru Bandara", "+94781512533"),
    ("Chamod Weerasinghe", "+94701585752"),
    ("Pasindu Gunawardena", "+94711658971"),
    ("Kavindu Rajapaksha", "+94721732190"),
    ("Sachintha Samarasinghe", "+94741805409"),
    ("Malith Senanayake", "+94751878628"),
    ("Gihan Rathnayake", "+94761951847"),
    ("Supun Herath", "+94772025066"),
    ("Shehan Wickramasinghe", "+94782098285"),
    ("Dinuka Abeysekara", "+94702171504"),
    ("Ravindu Amarasinghe", "+94712244723"),
    ("Chathura Ekanayake", "+94722317942"),
    ("Pramod Dissanayake", "+94742391161"),
    ("Sahan Jayawardena", "+94752464380"),
    ("Tharushan Alwis", "+94762537599"),
    ("Akila Weerakoon", "+94772610818"),
    ("Rukshan Maduranga", "+94782684037"),
    ("Dimuthu Peiris", "+94702757256"),
    ("Tharushi Perera", "+94712830475"),
    ("Sachini Wijeratne", "+94722903694"),
    ("Hansika Gunathilaka", "+94742976913"),
    ("Dinithi Jayawardena", "+94753050132"),
    ("Kavindi Ranasinghe", "+94763123351"),
    ("Senuri Wickramasinghe", "+94773196570"),
    ("Rashmi Fernando", "+94783269789"),
    ("Nethmi Samarasinghe", "+94703343008"),
    ("Himashi Gunawardena", "+94713416227"),
    ("Hasini Bandara", "+94723489446"),
    ("Dewmini Karunaratne", "+94743562665"),
    ("Sanduni Rajapaksha", "+94753635884"),
    ("Dilki Herath", "+94763709103"),
    ("Piumi Ekanayake", "+94773782322"),
    ("Shashikala Weerasinghe", "+94783855541"),
    ("Imashi Rathnayake", "+94703928760"),
    ("Naduni Abeysekara", "+94714001979"),
    ("Upeksha Jayasinghe", "+94724075198"),
    ("Bhagya Senanayake", "+94744148417"),
    ("Chamodi Dissanayake", "+94754221636"),
    ("Oshadi Amarasinghe", "+94764294855"),
    ("Methuli Perera", "+94774368074"),
    ("Thilini Wijesinghe", "+94784441293"),
    ("Yashoda Gunarathne", "+94704514512"),
    ("Heshani Ranasinghe", "+94714587731"),
]


def _display_name(product: dict) -> str:
    """Brand plus name, as it should read on a receipt."""
    return " ".join(part for part in (product.get("brand"), product.get("name", "")) if part)


def _draw_basket(products: list[dict]) -> list[dict]:
    """Pick the items for one shopper's basket.

    A real grocery run is mostly a few cheap staples, not a uniform sample of
    the catalogue — so basket sizes skew small and expensive lines are drawn
    far less often than everyday ones. Without this the simulated average
    basket drifts up to several times what a Colombo supermarket actually sees.
    """
    size = random.choices((1, 2, 3, 4, 5), weights=(26, 30, 22, 15, 7))[0]
    # Weight inversely to shelf price: a Rs 210 soap is reached for much more
    # often than a Rs 3,900 bag of basmati.
    weights = [1000 / (float(product["selling_price"]) + 150) for product in products]

    basket: list[dict] = []
    pool = list(products)
    pool_weights = list(weights)
    for _ in range(min(size, len(pool))):
        chosen = random.choices(pool, weights=pool_weights)[0]
        index = pool.index(chosen)
        pool.pop(index)
        pool_weights.pop(index)
        basket.append(chosen)
    return basket


async def main(reset: bool) -> None:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongo_uri, tz_aware=True)
    db = client[settings.db_name]

    if reset:
        await db.products.delete_many({})
        await db.sales.delete_many({})
        await db.customers.delete_many({})
        await db.stock_audits.delete_many({})
        await db.counters.delete_many({})
        print("Cleared products, sales, customers, audits and counters")

    await ensure_indexes(db)
    await ensure_store(db)
    await ensure_default_users(db)
    await db.stores.update_one(
        {"_id": settings.store_id},
        {
            "$set": {
                "name": "Super Sale",
                "address": "221 Galle Road, Colombo 03, Sri Lanka",
                "tax_id": "12234556789",
                "currency": "LKR",
                "tax_rate": 18.0,
                "default_discount": 0.0,
                "shelf_capacity_max": 3000,
                "warehouse_capacity_max": 8000,
                "loyalty_spend_per_point": 100.0,
            }
        },
    )

    now = datetime.now(timezone.utc)
    product_ids: dict[str, dict] = {}
    for (
        name, brand, barcode, category, buying, market, selling, discount, shelf, warehouse, threshold, image,
    ) in CATALOGUE:
        document = {
            "barcode": barcode,
            "name": name,
            "brand": brand,
            "category": category,
            "buying_price": q2(buying),
            "market_price": q2(market),
            "selling_price": q2(selling),
            "discount_percentage": q2(discount),
            "stock_shelf": shelf,
            "stock_warehouse": warehouse,
            "reorder_threshold": threshold,
            "image_url": f"emoji:{image}",
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        await db.products.update_one({"barcode": barcode}, {"$set": document}, upsert=True)
        stored = await db.products.find_one({"barcode": barcode})
        product_ids[barcode] = stored

    print(f"Upserted {len(CATALOGUE)} products")

    customer_docs = []
    for name, phone in CUSTOMERS:
        await db.customers.update_one(
            {"phone": phone},
            {
                "$set": {"name": name, "phone": phone, "email": None},
                "$setOnInsert": {
                    "total_visits": 0,
                    "total_spend": 0.0,
                    "credit_due": 0.0,
                    "loyalty_points": 0,
                    "last_visit": None,
                    "created_at": now,
                },
            },
            upsert=True,
        )
        customer_docs.append(await db.customers.find_one({"phone": phone}))

    print(f"Upserted {len(CUSTOMERS)} customers")

    # ---------------------------------------------------------------- sales
    store = await db.stores.find_one({"_id": settings.store_id}) or {}
    tax_rate = Decimal(str(store.get("tax_rate", 0.0)))
    spend_per_point = Decimal(str(store.get("loyalty_spend_per_point", 10.0)))
    products = list(product_ids.values())

    sold_units: dict[str, int] = {}
    customer_totals: dict[str, dict] = {}
    sales_batch = []
    receipt_sequence = 0

    local_midnight = datetime.now().astimezone().replace(hour=0, minute=0, second=0, microsecond=0)

    for days_ago in range(HISTORY_DAYS, -1, -1):
        day = local_midnight - timedelta(days=days_ago)
        # Weekends are busier than weekdays.
        base = 26 if day.weekday() >= 5 else 16
        transactions = random.randint(base, base + 10)

        for _ in range(transactions):
            timestamp = (day + timedelta(hours=random.randint(8, 20), minutes=random.randint(0, 59))).astimezone(
                timezone.utc
            )
            basket = _draw_basket(products)
            lines = []
            subtotal = Decimal("0")
            discount_total = Decimal("0")
            net_profit = Decimal("0")

            for product in basket:
                quantity = random.choices((1, 2, 3), weights=(74, 20, 6))[0]
                selling = q2(product["selling_price"])
                buying = q2(product["buying_price"])
                discount = q2(product["discount_percentage"])
                effective = effective_price(selling, discount)

                gross_line = Decimal(str(selling)) * quantity
                line_total = Decimal(str(effective)) * quantity
                line_profit = (Decimal(str(effective)) - Decimal(str(buying))) * quantity

                subtotal += gross_line
                discount_total += gross_line - line_total
                net_profit += line_profit
                sold_units[str(product["_id"])] = sold_units.get(str(product["_id"]), 0) + quantity

                lines.append(
                    {
                        "product_id": product["_id"],
                        "barcode": product["barcode"],
                        "name": _display_name(product),
                        "quantity": quantity,
                        "unit_buying_price": buying,
                        "unit_selling_price": selling,
                        "discount_percentage": discount,
                        "line_total": q2(line_total),
                        "line_profit": q2(line_profit),
                    }
                )

            taxable = subtotal - discount_total
            tax_amount = taxable * tax_rate / Decimal("100")
            grand_total = q2(taxable + tax_amount)

            customer = random.choice(customer_docs) if random.random() < 0.55 else None
            loyalty_points = int(Decimal(str(grand_total)) // spend_per_point) if customer else 0
            if customer:
                totals = customer_totals.setdefault(
                    str(customer["_id"]), {"visits": 0, "spend": Decimal("0"), "points": 0, "last": timestamp}
                )
                totals["visits"] += 1
                totals["spend"] += Decimal(str(grand_total))
                totals["points"] += loyalty_points
                totals["last"] = max(totals["last"], timestamp)

            payment_method = random.choices(["CASH", "CARD", "SPLIT"], weights=[62, 33, 5])[0]
            breakdown = None
            if payment_method == "SPLIT":
                cash_part = q2(Decimal(str(grand_total)) / 2)
                breakdown = {"cash": cash_part, "card": q2(Decimal(str(grand_total)) - Decimal(str(cash_part)))}

            receipt_sequence += 1
            sales_batch.append(
                {
                    "receipt_number": f"REC-{timestamp.year}-{receipt_sequence:05d}",
                    "cashier_id": "cashier",
                    "customer_id": customer["_id"] if customer else None,
                    "customer_name": customer["name"] if customer else None,
                    "items": lines,
                    "subtotal": q2(subtotal),
                    "discount_total": q2(discount_total),
                    "tax_amount": q2(tax_amount),
                    "grand_total": grand_total,
                    "net_profit": q2(net_profit),
                    "payment_method": payment_method,
                    "payment_breakdown": breakdown,
                    "amount_tendered": None,
                    "change_due": None,
                    "loyalty_points_earned": loyalty_points,
                    "timestamp": timestamp,
                    "type": "SALE",
                    "returned": {},
                }
            )

    if sales_batch:
        await db.sales.insert_many(sales_batch)
        await db.counters.update_one(
            {"_id": f"receipt:{datetime.now().year}"},
            {"$set": {"value": receipt_sequence}},
            upsert=True,
        )
    print(f"Inserted {len(sales_batch)} sales across {HISTORY_DAYS} days")

    # ------------------------------------------------------------- returns
    # A small share of baskets come back. Refunds are negative documents in the
    # same ledger, so every report nets them out without extra handling.
    returns_batch = []
    return_sequence = 0
    refundable = [sale for sale in sales_batch if sale["items"]]
    for sale in random.sample(refundable, max(1, len(refundable) // 45)):
        item = random.choice(sale["items"])
        quantity = random.randint(1, item["quantity"])
        selling = Decimal(str(item["unit_selling_price"]))
        buying = Decimal(str(item["unit_buying_price"]))
        effective = Decimal(str(effective_price(item["unit_selling_price"], item["discount_percentage"])))

        gross_line = selling * quantity
        line_total = effective * quantity
        line_profit = (effective - buying) * quantity
        discount_line = gross_line - line_total

        taxable = gross_line - discount_line
        tax_amount = taxable * tax_rate / Decimal("100")
        refund_total = q2(taxable + tax_amount)

        # Customers come back a day or two later, never in the future.
        when = min(sale["timestamp"] + timedelta(days=random.randint(1, 3)), now)
        return_sequence += 1
        loyalty_reversed = (
            int(Decimal(str(refund_total)) // spend_per_point) if sale.get("customer_id") else 0
        )

        returns_batch.append(
            {
                "receipt_number": f"RET-{when.year}-{return_sequence:05d}",
                "type": "RETURN",
                "original_sale_id": sale["_id"],
                "original_receipt_number": sale["receipt_number"],
                "cashier_id": "owner",
                "customer_id": sale.get("customer_id"),
                "customer_name": sale.get("customer_name"),
                "items": [
                    {
                        "product_id": item["product_id"],
                        "barcode": item["barcode"],
                        "name": item["name"],
                        "quantity": -quantity,
                        "unit_buying_price": item["unit_buying_price"],
                        "unit_selling_price": item["unit_selling_price"],
                        "discount_percentage": item["discount_percentage"],
                        "line_total": q2(-line_total),
                        "line_profit": q2(-line_profit),
                    }
                ],
                "subtotal": q2(-gross_line),
                "discount_total": q2(-discount_line),
                "tax_amount": q2(-tax_amount),
                "grand_total": q2(-refund_total),
                "net_profit": q2(-line_profit),
                "payment_method": random.choice(["CASH", "CARD"]),
                "payment_breakdown": None,
                "amount_tendered": None,
                "change_due": None,
                "loyalty_points_earned": -loyalty_reversed,
                "reason": random.choice(RETURN_REASONS),
                "restocked": random.random() < 0.7,
                "timestamp": when,
            }
        )
        await db.sales.update_one(
            {"_id": sale["_id"]},
            {"$inc": {"returned." + str(item["product_id"]): quantity}},
        )
        if sale.get("customer_id"):
            totals = customer_totals.get(str(sale["customer_id"]))
            if totals:
                totals["spend"] -= Decimal(str(refund_total))
                totals["points"] = max(0, totals["points"] - loyalty_reversed)

    if returns_batch:
        await db.sales.insert_many(returns_batch)
        await db.counters.update_one(
            {"_id": f"return:{datetime.now().year}"},
            {"$set": {"value": return_sequence}},
            upsert=True,
        )
    print(f"Inserted {len(returns_batch)} returns")

    # Make stock levels consistent with the simulated trading above, and leave a
    # handful of products genuinely low so the restock alerts are not empty.
    for product in products:
        sold = sold_units.get(str(product["_id"]), 0)
        remaining_shelf = max(0, product["stock_shelf"] - sold % max(1, product["stock_shelf"]))
        await db.products.update_one(
            {"_id": product["_id"]},
            {"$set": {"stock_shelf": remaining_shelf, "updated_at": now}},
        )

    low_stock_picks = random.sample(products, 4)
    for product in low_stock_picks:
        await db.products.update_one(
            {"_id": product["_id"]},
            {
                "$set": {
                    "stock_shelf": random.randint(0, 4),
                    "stock_warehouse": random.randint(0, 6),
                    "updated_at": now,
                }
            },
        )
    print(f"Marked {len(low_stock_picks)} products as low/out of stock")

    for customer_id, totals in customer_totals.items():
        await db.customers.update_one(
            {"_id": customer_docs[0]["_id"].__class__(customer_id)},
            {
                "$set": {
                    "total_visits": totals["visits"],
                    "total_spend": q2(max(Decimal("0"), totals["spend"])),
                    "loyalty_points": totals["points"],
                    "last_visit": totals["last"],
                }
            },
        )
    print(f"Updated spend history for {len(customer_totals)} customers")

    print("\nSeed complete. Sign in with owner / owner123 or cashier / cashier123")
    client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the Super Sale database")
    parser.add_argument("--reset", action="store_true", help="delete existing demo data first")
    arguments = parser.parse_args()
    asyncio.run(main(arguments.reset))
