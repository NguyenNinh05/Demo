# SnapShop - ERD (sinh tự động từ PostgreSQL)

```mermaid
erDiagram
    category {
        varchar(20) category_id PK
        varchar(20) parent_id FK
        varchar(255) name
        varchar(255) description  "nullable"
    }
    customer {
        varchar(20) customer_id PK
        varchar(255) full_name
        varchar(255) email
        varchar(20) phone  "nullable"
        varchar(500) address  "nullable"
        timestamp created_at
    }
    order_item {
        integer order_item_id PK
        varchar(20) order_id FK
        integer product_id FK
        integer quantity
        bigint unit_price
    }
    orders {
        varchar(20) order_id PK
        varchar(20) customer_id FK
        timestamp order_date
        bigint total_amount
        varchar(50) status
        varchar(500) shipping_address  "nullable"
    }
    payment {
        varchar(20) payment_id PK
        varchar(20) order_id FK
        varchar(50) payment_method
        timestamp payment_date  "nullable"
        bigint amount
        varchar(50) status
    }
    product {
        integer product_id PK
        varchar(20) category_id FK
        varchar(255) name
        varchar(100) brand
        varchar(10) gender
        bigint price
        integer stock
        varchar(50) color  "nullable"
        varchar(50) color_detail  "nullable"
        varchar(50) material  "nullable"
        varchar(50) pattern  "nullable"
        varchar(255) description  "nullable"
        text description_en  "nullable"
        varchar(500) image_path
        numeric(4,3) popularity
        varchar(500) source_url  "nullable"
        timestamp created_at
        text search_doc  "nullable"
    }
    category |o--o{ category : "parent_id"
    orders ||--o{ order_item : "order_id"
    product ||--o{ order_item : "product_id"
    customer ||--o{ orders : "customer_id"
    orders ||--o{ payment : "order_id"
    category ||--o{ product : "category_id"
```
