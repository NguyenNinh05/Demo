-- SnapShop - PostgreSQL schema (follows the ERD; Order is renamed orders,
-- duplicated foreign-key columns removed, product gets gender/material/pattern).

CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- unaccent() is not IMMUTABLE, so it cannot be used in an index or a
-- generated column; this wrapper fixes the dictionary and can be.
CREATE OR REPLACE FUNCTION f_unaccent(text) RETURNS text
    LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
    AS $$ SELECT lower(public.unaccent('public.unaccent'::regdictionary, replace($1, 'đ', 'd'))) $$;

DROP TABLE IF EXISTS payment, order_item, orders, customer, product, category CASCADE;

CREATE TABLE category (
    category_id  varchar(20)  PRIMARY KEY,
    parent_id    varchar(20)  REFERENCES category(category_id),
    name         varchar(255) NOT NULL,
    description  varchar(255)
);

CREATE TABLE product (
    product_id     integer      PRIMARY KEY,
    category_id    varchar(20)  NOT NULL REFERENCES category(category_id),
    name           varchar(255) NOT NULL,
    brand          varchar(100) NOT NULL,
    gender         varchar(10)  NOT NULL CHECK (gender IN ('nam', 'nu', 'unisex')),
    price          bigint       NOT NULL CHECK (price >= 0),
    stock          integer      NOT NULL DEFAULT 0 CHECK (stock >= 0),
    color          varchar(50),
    color_detail   varchar(50),
    material       varchar(50),
    pattern        varchar(50),
    description    varchar(255),
    description_en text,
    image_path     varchar(500) NOT NULL,
    popularity     numeric(4,3) NOT NULL DEFAULT 0.5,
    occasions      text[]       NOT NULL DEFAULT '{}',   -- labelled by tools/label_occasions.py
    source_url     varchar(500),
    created_at     timestamp    NOT NULL DEFAULT now(),
    -- text used by keyword / fuzzy search (no accents, lower case)
    search_doc     text GENERATED ALWAYS AS (
        f_unaccent(name || ' ' || brand || ' ' || coalesce(color, '') || ' ' ||
                   coalesce(material, '') || ' ' || coalesce(pattern, '') || ' ' ||
                   coalesce(description, ''))
    ) STORED
);

CREATE INDEX product_category_idx ON product (category_id);
CREATE INDEX product_price_idx    ON product (price);
CREATE INDEX product_filter_idx   ON product (gender, color);
CREATE INDEX product_trgm_idx     ON product USING gin (search_doc gin_trgm_ops);
CREATE INDEX product_occasion_idx ON product USING gin (occasions);

CREATE TABLE customer (
    customer_id  varchar(20)  PRIMARY KEY,
    full_name    varchar(255) NOT NULL,
    email        varchar(255) NOT NULL UNIQUE,
    phone        varchar(20),
    address      varchar(500),
    created_at   timestamp    NOT NULL DEFAULT now()
);

CREATE TABLE orders (
    order_id         varchar(20)  PRIMARY KEY,
    customer_id      varchar(20)  NOT NULL REFERENCES customer(customer_id),
    order_date       timestamp    NOT NULL,
    total_amount     bigint       NOT NULL,
    status           varchar(50)  NOT NULL,
    shipping_address varchar(500)
);

CREATE INDEX orders_customer_idx ON orders (customer_id, order_date DESC);

CREATE TABLE order_item (
    order_item_id  serial      PRIMARY KEY,
    order_id       varchar(20) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    product_id     integer     NOT NULL REFERENCES product(product_id),
    quantity       integer     NOT NULL CHECK (quantity > 0),
    unit_price     bigint      NOT NULL
);

CREATE TABLE payment (
    payment_id      varchar(20) PRIMARY KEY,
    order_id        varchar(20) NOT NULL REFERENCES orders(order_id) ON DELETE CASCADE,
    payment_method  varchar(50) NOT NULL,
    payment_date    timestamp,
    amount          bigint      NOT NULL,
    status          varchar(50) NOT NULL
);
