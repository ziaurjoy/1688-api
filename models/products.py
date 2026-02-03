# from pydantic import BaseModel, HttpUrl
# from typing import Optional


# class PriceModel(BaseModel):
#     currency: str
#     amount: str
#     unit: str
#     overseas: Optional[str] = None


# class ProductModel(BaseModel):
#     offer_id: str
#     title: str
#     url: HttpUrl
#     image: HttpUrl
#     price: PriceModel
#     rating: str
#     sold: str
#     promotion: Optional[str] = None
#     moq: str
#     seller_icon: HttpUrl
#     is_ad: bool




from pydantic import BaseModel, HttpUrl, RootModel
from typing import List, Dict, Optional



class ReviewSummary(BaseModel):
    rating: str
    total_reviews: int
    positive_rate: str


class ProductReviews(BaseModel):
    summary: ReviewSummary


class ProductAttributes(RootModel[Dict[str, str]]):
    pass


class ProductPacking(BaseModel):
    color: str
    size: Optional[str]
    weight_g: Optional[float]

class ProductDescription(BaseModel):
    images: List[str]
    html: Optional[str]
    price_desc: Dict[str, List[str]]

class CartSKU(BaseModel):
    size: str
    price: str
    stock: str


class ProductCart(BaseModel):
    price_range: str
    min_order: str
    services: List[str]
    shipping_from: str
    skus: List[CartSKU]


class ProductTitle(BaseModel):
    title: str
    rating: str
    reviews: str
    total_sales: str


class ProductTitleAndCart(BaseModel):
    productTitle: ProductTitle
    cart: ProductCart


class VariantSize(BaseModel):
    size_name: str
    price: str
    stock: str


class ProductVariant(BaseModel):
    color_name: str
    image: str
    active: bool
    sizes: List[VariantSize]


class ProductDetails(BaseModel):
    url: HttpUrl
    extract_product_reviews: ProductReviews
    extract_product_attributes: ProductAttributes
    extract_product_packing: List[ProductPacking]
    extract_product_description: ProductDescription
    extract_product_title_and_cart: ProductTitleAndCart
    extract_product_variants: List[ProductVariant]


class Product(BaseModel):
    category: str
    subcategory: str
    item: str
    details: ProductDetails
