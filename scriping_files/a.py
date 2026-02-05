
# Ensure project root is on sys.path so `from database import db` works when running
# this script from inside `scriping_files` (or other subfolders).
try:
    from database import db
except ModuleNotFoundError:
    import os, sys
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)
    from database import db

from fastapi.encoders import jsonable_encoder

data = {'offer_id': '847461182224', 'title': '2025 new 2.5K HD 15.6 inch N95 laptop ultra-thin business office game', 'url': 'https://detail.1688.com/offer/847461182224.html', 'image': 'https://cbu01.alicdn.com/img/ibank/O1CN01CAT30O1Tj2IKc7bDU_!!2211417592417-0-cib.jpg_460x460q100.jpg_.webp', 'price': {'currency': '¥', 'amount': '2310', 'unit': '.0', 'overseas': '$339.59'}, 'rating': '4.8', 'sold': '200+ sold', 'promotion': '元宝可抵1%', 'moq': None, 'seller_icon': 'https://gw.alicdn.com/imgextra/i1/O1CN01mMViSE1ZX1etkFsve_!!6000000003203-2-tps-416-56.png', 'is_ad': False}

result = db.products.insert_one(jsonable_encoder(data))