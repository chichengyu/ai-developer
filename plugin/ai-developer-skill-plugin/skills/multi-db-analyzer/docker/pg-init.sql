-- PostgreSQL test database initialization for multi-db-analyzer
-- Usage: docker compose -f docker/docker-compose.yml up -d postgres-test

CREATE TABLE IF NOT EXISTS "user" (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    email VARCHAR(100) DEFAULT NULL,
    phone VARCHAR(20) DEFAULT NULL,
    age INT DEFAULT NULL,
    status SMALLINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "order" (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    order_no VARCHAR(32) NOT NULL,
    total_amount DECIMAL(12,2) NOT NULL,
    status SMALLINT DEFAULT 0,
    payment_method VARCHAR(20) DEFAULT NULL,
    paid_at TIMESTAMP DEFAULT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_order_user FOREIGN KEY (user_id) REFERENCES "user"(id)
);

CREATE TABLE IF NOT EXISTS "order_item" (
    id BIGSERIAL PRIMARY KEY,
    order_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    product_name VARCHAR(200) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    quantity INT NOT NULL DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_item_order FOREIGN KEY (order_id) REFERENCES "order"(id)
);

CREATE TABLE IF NOT EXISTS "product" (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    category_id BIGINT DEFAULT NULL,
    price DECIMAL(10,2) NOT NULL,
    stock INT DEFAULT 0,
    description TEXT,
    status SMALLINT DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS "category" (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    parent_id BIGINT DEFAULT NULL,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO "user" (username, email, phone, age, status) VALUES
('admin', 'admin@example.com', '13800138000', 30, 1),
('testuser', 'test@example.com', NULL, 25, 1),
('guest', NULL, NULL, NULL, 0);

INSERT INTO "category" (id, name, parent_id, sort_order) VALUES
(1, 'Electronics', NULL, 1), (2, 'Clothing', NULL, 2),
(3, 'Phones', 1, 1), (4, 'Computers', 1, 2);

INSERT INTO "product" (name, category_id, price, stock, description, status) VALUES
('iPhone 15', 3, 6999.00, 100, 'Latest smartphone', 1),
('MacBook Pro', 4, 12999.00, 50, 'High-performance laptop', 1),
('T-Shirt', 2, 99.00, 500, 'Cotton crew neck', 1);

INSERT INTO "order" (user_id, order_no, total_amount, status, payment_method) VALUES
(1, 'ORD20260716001', 6999.00, 1, 'wechat'),
(1, 'ORD20260716002', 13098.00, 3, 'alipay'),
(2, 'ORD20260716003', 99.00, 0, NULL);

INSERT INTO "order_item" (order_id, product_id, product_name, price, quantity) VALUES
(1, 1, 'iPhone 15', 6999.00, 1),
(2, 2, 'MacBook Pro', 12999.00, 1),
(2, 3, 'T-Shirt', 99.00, 1),
(3, 3, 'T-Shirt', 99.00, 1);
