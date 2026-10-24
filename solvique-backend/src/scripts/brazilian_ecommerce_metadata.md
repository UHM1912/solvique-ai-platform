# DATABASE METADATA
- database: Brazilian E-Commerce
- platform: Supabase PostgreSQL 17
- schema: public
- description: Brazilian online marketplace (multi-seller e-commerce platform, Olist dataset)
- data_period: 2016-09-04 to 2018-10-17
- language_note: Column values such as product_category_name and city names are in Portuguese. State codes use Brazilian 2-letter abbreviations (e.g. SP, RJ, MG).

---

# TABLE: orders
- purpose: Central fact table. Each row represents one customer order. It is the hub that links customers, order items, payments, and reviews.
- row_count: 99440
- date_range: 2016-09-04 to 2018-10-17
- primary_key: order_id
- foreign_keys: customer_id

## RELATIONSHIPS
- related_table: customers | join_column: customer_id | related_column: customer_id | type: many-to-one | description: Each order belongs to one customer.
- related_table: order_items | join_column: order_id | related_column: order_id | type: one-to-many | description: An order can have multiple line items.
- related_table: order_payments | join_column: order_id | related_column: order_id | type: one-to-many | description: An order can have one or more payment entries.
- related_table: order_reviews | join_column: order_id | related_column: order_id | type: one-to-one | description: An order can have one customer review.

## COLUMNS
### order_id
- data_type: TEXT
- column_type: identifier
- nullable: false
- description: Unique identifier for each order (UUID-like hash). Primary key.

### customer_id
- data_type: TEXT
- column_type: identifier
- nullable: true
- description: Foreign key linking to customers.customer_id. Identifies the customer who placed this order.

### order_status
- data_type: TEXT
- column_type: categorical
- nullable: true
- description: Current lifecycle status of the order.
- column_values: created, approved, invoiced, processing, shipped, delivered, canceled, unavailable

### order_purchase_timestamp
- data_type: TIMESTAMP
- column_type: datetime
- nullable: true
- date_range: 2016-09-04 to 2018-10-17
- description: Timestamp when the customer placed the order.

### order_approved_at
- data_type: TIMESTAMP
- column_type: datetime
- nullable: true
- null_note: NULL for 160 orders (cancelled or pending payment).
- description: Timestamp when payment was approved.

### order_delivered_carrier_date
- data_type: TIMESTAMP
- column_type: datetime
- nullable: true
- null_note: NULL for 1783 orders not yet handed to carrier.
- description: Timestamp when the order was handed off to the logistics carrier.

### order_delivered_customer_date
- data_type: TIMESTAMP
- column_type: datetime
- nullable: true
- null_note: NULL for 2965 orders not yet delivered.
- description: Timestamp when the order was delivered to the customer.

### order_estimated_delivery_date
- data_type: TIMESTAMP
- column_type: datetime
- nullable: true
- description: Estimated delivery date communicated to the customer at purchase.

---

# TABLE: customers
- purpose: Stores customer location and identity data. customer_id is order-scoped (one row per order), while customer_unique_id identifies the same physical person across multiple orders.
- row_count: 99441
- unique_customers_by_unique_id: 96096
- primary_key: customer_id
- foreign_keys: none

## RELATIONSHIPS
- related_table: orders | join_column: customer_id | related_column: customer_id | type: one-to-many | description: One customer (unique_id) can have many orders.
- related_table: geolocation | join_column: customer_zip_code_prefix | related_column: geolocation_zip_code_prefix | type: many-to-many | description: Joins to geolocation to get lat/lng coordinates. Use AVG(lat)/AVG(lng) after joining to avoid row duplication.

## COLUMNS
### customer_id
- data_type: TEXT
- column_type: identifier
- nullable: false
- description: Primary key. Order-scoped customer ID — unique per order, not per person. Use customer_unique_id to count distinct real customers.

### customer_unique_id
- data_type: TEXT
- column_type: identifier
- nullable: true
- description: True unique customer identifier. Use this for repeat-customer analysis. 96096 distinct values out of 99441 rows.

### customer_zip_code_prefix
- data_type: INTEGER
- column_type: numeric
- nullable: true
- description: First 5 digits of the customer's Brazilian ZIP code (CEP). Use to join with the geolocation table.

### customer_city
- data_type: TEXT
- column_type: free_text
- nullable: true
- description: City name of the customer (in Portuguese).

### customer_state
- data_type: TEXT
- column_type: categorical
- nullable: true
- description: Brazilian state code of the customer (2-letter abbreviation, e.g. SP, RJ).
- column_values: AC, AL, AM, AP, BA, CE, DF, ES, GO, MA, MG, MS, MT, PA, PB, PE, PI, PR, RJ, RN, RO, RR, RS, SC, SE, SP, TO

---

# TABLE: products
- purpose: Product catalogue. Contains physical product attributes and category. Does not store product name text or price — only name/description character lengths. Price is in order_items.
- row_count: 32951
- distinct_categories: 73
- null_category_count: 610
- primary_key: product_id
- foreign_keys: none

## RELATIONSHIPS
- related_table: order_items | join_column: product_id | related_column: product_id | type: one-to-many | description: A product can appear in many order line items.

## COLUMNS
### product_id
- data_type: TEXT
- column_type: identifier
- nullable: false
- description: Unique product identifier (UUID-like hash). Primary key.

### product_category_name
- data_type: TEXT
- column_type: categorical
- nullable: true
- null_note: 610 products have no category assigned.
- description: Product category name in Portuguese (73 distinct values).
- column_values: agro_industria_e_comercio, alimentos, alimentos_bebidas, artes, artes_e_artesanato, artigos_de_festas, artigos_de_natal, audio, automotivo, bebes, bebidas, beleza_saude, brinquedos, cama_mesa_banho, casa_conforto, casa_conforto_2, casa_construcao, cds_dvds_musicais, cine_foto, climatizacao, consoles_games, construcao_ferramentas_construcao, construcao_ferramentas_ferramentas, construcao_ferramentas_iluminacao, construcao_ferramentas_jardim, construcao_ferramentas_seguranca, cool_stuff, dvds_blu_ray, eletrodomesticos, eletrodomesticos_2, eletronicos, eletroportateis, esporte_lazer, fashion_bolsas_e_acessorios, fashion_calcados, fashion_esporte, fashion_roupa_feminina, fashion_roupa_infanto_juvenil, fashion_roupa_masculina, fashion_underwear_e_moda_praia, ferramentas_jardim, flores, fraldas_higiene, industria_comercio_e_negocios, informatica_acessorios, instrumentos_musicais, la_cuisine, livros_importados, livros_interesse_geral, livros_tecnicos, malas_acessorios, market_place, moveis_colchao_e_estofado, moveis_cozinha_area_de_servico_jantar_e_jardim, moveis_decoracao, moveis_escritorio, moveis_quarto, moveis_sala, musica, papelaria, pc_gamer, pcs, perfumaria, pet_shop, portateis_casa_forno_e_cafe, portateis_cozinha_e_preparadores_de_alimentos, relogios_presentes, seguros_e_servicos, sinalizacao_e_seguranca, tablets_impressao_imagem, telefonia, telefonia_fixa, utilidades_domesticas

### product_name_length
- data_type: INTEGER
- column_type: numeric
- nullable: true
- description: Character count of the product listing name.

### product_description_length
- data_type: INTEGER
- column_type: numeric
- nullable: true
- description: Character count of the product description text.

### product_photos_qty
- data_type: INTEGER
- column_type: numeric
- nullable: true
- value_range: 1 to 20
- description: Number of photos in the product listing.

### product_weight_g
- data_type: INTEGER
- column_type: numeric
- nullable: true
- value_range: 0 to 40425 grams
- description: Product weight in grams.

### product_length_cm
- data_type: INTEGER
- column_type: numeric
- nullable: true
- description: Product length in centimetres.

### product_height_cm
- data_type: INTEGER
- column_type: numeric
- nullable: true
- description: Product height in centimetres.

### product_width_cm
- data_type: INTEGER
- column_type: numeric
- nullable: true
- description: Product width in centimetres.

---

# TABLE: sellers
- purpose: Marketplace sellers who list and fulfil products. Each seller has a location. Majority of sellers are based in São Paulo (SP).
- row_count: 3095
- distinct_states: 23
- distinct_cities: 611
- primary_key: seller_id
- foreign_keys: none

## RELATIONSHIPS
- related_table: order_items | join_column: seller_id | related_column: seller_id | type: one-to-many | description: A seller can fulfil many order line items.
- related_table: geolocation | join_column: seller_zip_code_prefix | related_column: geolocation_zip_code_prefix | type: many-to-many | description: Joins to geolocation to get lat/lng coordinates. Use AVG(lat)/AVG(lng) after joining to avoid row duplication.

## COLUMNS
### seller_id
- data_type: TEXT
- column_type: identifier
- nullable: false
- description: Unique seller identifier (UUID-like hash). Primary key.

### seller_zip_code_prefix
- data_type: INTEGER
- column_type: numeric
- nullable: true
- description: First 5 digits of the seller's Brazilian ZIP code (CEP). Use to join with the geolocation table.

### seller_city
- data_type: TEXT
- column_type: free_text
- nullable: true
- description: City where the seller is located (in Portuguese, 611 distinct cities).

### seller_state
- data_type: TEXT
- column_type: categorical
- nullable: true
- description: Brazilian state code of the seller (2-letter abbreviation, 23 distinct states).
- column_values: AC, AM, BA, CE, DF, ES, GO, MA, MG, MS, MT, PA, PB, PE, PI, PR, RJ, RN, RO, RS, SC, SE, SP

---

# TABLE: order_items
- purpose: Line-item bridge table. Each row is one product within one order. This is the key table for joining orders to products and sellers, and the source of item-level pricing and freight costs.
- row_count: 98665
- currency: BRL (Brazilian Reais)
- price_range_brl: 0.85 to 6735.00
- avg_price_brl: 125.97
- freight_range_brl: 0.00 to 409.68
- primary_key: order_id, order_item_id
- foreign_keys: order_id, product_id, seller_id

## RELATIONSHIPS
- related_table: orders | join_column: order_id | related_column: order_id | type: many-to-one | description: Multiple items belong to one order.
- related_table: products | join_column: product_id | related_column: product_id | type: many-to-one | description: Each line item references one product.
- related_table: sellers | join_column: seller_id | related_column: seller_id | type: many-to-one | description: Each line item is fulfilled by one seller.

## COLUMNS
### order_id
- data_type: TEXT
- column_type: identifier
- nullable: false
- description: Composite primary key (part 1). Foreign key to orders.order_id.

### order_item_id
- data_type: INTEGER
- column_type: numeric
- nullable: false
- description: Composite primary key (part 2). Sequential item number within the order (1, 2, 3…). Together with order_id forms the unique key.

### product_id
- data_type: TEXT
- column_type: identifier
- nullable: true
- description: Foreign key to products.product_id — the product purchased.

### seller_id
- data_type: TEXT
- column_type: identifier
- nullable: true
- description: Foreign key to sellers.seller_id — the seller fulfilling this item.

### shipping_limit_date
- data_type: TEXT
- column_type: datetime_text
- nullable: true
- description: Deadline for the seller to ship this item (stored as text timestamp).

### price
- data_type: NUMERIC
- column_type: numeric
- nullable: true
- value_range: 0.85 to 6735.00 BRL
- description: Unit price of the item in Brazilian Reais (BRL). Average 125.97 BRL.

### freight_value
- data_type: NUMERIC
- column_type: numeric
- nullable: true
- value_range: 0.00 to 409.68 BRL
- description: Shipping/freight cost for this item in Brazilian Reais (BRL).

---

# TABLE: order_payments
- purpose: Records how each order was paid. An order can have multiple payment rows (e.g. part credit card and part voucher), each with a sequential number. SUM(payment_value) GROUP BY order_id gives total amount paid.
- row_count: 99440
- currency: BRL (Brazilian Reais)
- payment_value_range_brl: 0.00 to 13664.08
- max_installments: 24
- max_payment_sequential: 27
- primary_key: order_id, payment_sequential
- foreign_keys: order_id

## RELATIONSHIPS
- related_table: orders | join_column: order_id | related_column: order_id | type: many-to-one | description: Multiple payment rows can belong to one order.

## COLUMNS
### order_id
- data_type: TEXT
- column_type: identifier
- nullable: false
- description: Composite primary key (part 1). Foreign key to orders.order_id.

### payment_sequential
- data_type: INTEGER
- column_type: numeric
- nullable: false
- value_range: 1 to 27
- description: Composite primary key (part 2). Payment sequence number within the order. 1 = primary payment. Multiple rows indicate split payments.

### payment_type
- data_type: TEXT
- column_type: categorical
- nullable: true
- description: Payment method. boleto is a Brazilian bank-slip payment. credit_card is most common.
- column_values: credit_card, boleto, voucher, debit_card, not_defined

### payment_installments
- data_type: INTEGER
- column_type: numeric
- nullable: true
- value_range: 0 to 24
- description: Number of installments. 1 = paid in full. Greater than 1 = buy-now-pay-later installment plan (common in Brazil).

### payment_value
- data_type: NUMERIC
- column_type: numeric
- nullable: true
- value_range: 0.00 to 13664.08 BRL
- description: Amount paid in this payment entry in Brazilian Reais (BRL).

---

# TABLE: order_reviews
- purpose: Customer satisfaction reviews submitted after delivery. Each order receives at most one review. review_score is a 1 to 5 star integer rating. Comment fields are often NULL — many customers only leave a score.
- row_count: 99223
- null_comment_title_count: 87655
- null_comment_message_count: 58247
- review_language: Portuguese
- primary_key: review_id, order_id
- foreign_keys: order_id

## RELATIONSHIPS
- related_table: orders | join_column: order_id | related_column: order_id | type: many-to-one | description: Each review is associated with one order.

## COLUMNS
### review_id
- data_type: TEXT
- column_type: identifier
- nullable: false
- description: Composite primary key (part 1). Unique review identifier.

### order_id
- data_type: TEXT
- column_type: identifier
- nullable: false
- description: Composite primary key (part 2). Foreign key to orders.order_id.

### review_score
- data_type: INTEGER
- column_type: categorical
- nullable: true
- description: Star rating given by the customer. 1 = worst, 5 = best.
- column_values: 1, 2, 3, 4, 5

### review_comment_title
- data_type: TEXT
- column_type: free_text
- nullable: true
- null_note: NULL for 87655 out of 99223 rows (88% of reviews have no title).
- description: Optional short title of the review (in Portuguese).

### review_comment_message
- data_type: TEXT
- column_type: free_text
- nullable: true
- null_note: NULL for 58247 out of 99223 rows (59% of reviews have no message).
- description: Optional detailed review text (in Portuguese).

### review_creation_date
- data_type: TIMESTAMP
- column_type: datetime
- nullable: true
- description: Timestamp when the customer submitted the review.

### review_answer_timestamp
- data_type: TIMESTAMP
- column_type: datetime
- nullable: true
- description: Timestamp when the review survey was answered or acknowledged.

---

# TABLE: geolocation
- purpose: Lookup table mapping Brazilian ZIP code prefixes (first 5 digits of CEP) to geographic coordinates and city/state. Has no primary key — multiple lat/lng points exist per zip prefix. Always use AVG(lat)/AVG(lng) when joining to avoid row duplication.
- row_count: 1000163
- no_primary_key: true
- join_note: Always use AVG(geolocation_lat) and AVG(geolocation_lng) after joining to avoid row multiplication.
- primary_key: none
- foreign_keys: none

## RELATIONSHIPS
- related_table: customers | join_column: geolocation_zip_code_prefix | related_column: customer_zip_code_prefix | type: one-to-many | description: Maps customer ZIP codes to coordinates.
- related_table: sellers | join_column: geolocation_zip_code_prefix | related_column: seller_zip_code_prefix | type: one-to-many | description: Maps seller ZIP codes to coordinates.

## COLUMNS
### geolocation_zip_code_prefix
- data_type: INTEGER
- column_type: numeric
- nullable: true
- description: First 5 digits of a Brazilian ZIP code (CEP). Not unique — multiple coordinate rows can exist per prefix. Join key to customers.customer_zip_code_prefix and sellers.seller_zip_code_prefix.

### geolocation_lat
- data_type: NUMERIC
- column_type: numeric
- nullable: true
- description: Latitude coordinate. Use AVG() when joining to deduplicate.

### geolocation_lng
- data_type: NUMERIC
- column_type: numeric
- nullable: true
- description: Longitude coordinate. Use AVG() when joining to deduplicate.

### geolocation_city
- data_type: TEXT
- column_type: free_text
- nullable: true
- description: City name corresponding to the ZIP prefix (in Portuguese).

### geolocation_state
- data_type: TEXT
- column_type: categorical
- nullable: true
- description: Brazilian state code (2-letter abbreviation) for this ZIP prefix.
- column_values: AC, AL, AM, AP, BA, CE, DF, ES, GO, MA, MG, MS, MT, PA, PB, PE, PI, PR, RJ, RN, RO, RR, RS, SC, SE, SP, TO
