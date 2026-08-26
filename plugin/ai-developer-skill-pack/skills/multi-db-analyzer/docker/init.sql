-- ============================================================
 -- multi-db-analyzer 测试数据库初始化脚本
-- 用法: docker compose -f docker/docker-compose.yml up -d
-- ============================================================

CREATE DATABASE IF NOT EXISTS testdb DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE testdb;

-- 用户表
CREATE TABLE `user` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '用户ID',
    `username` VARCHAR(50) NOT NULL COMMENT '用户名',
    `email` VARCHAR(100) DEFAULT NULL COMMENT '邮箱',
    `phone` VARCHAR(20) DEFAULT NULL COMMENT '手机号',
    `age` INT DEFAULT NULL COMMENT '年龄',
    `status` TINYINT DEFAULT 1 COMMENT '状态: 1=正常 0=禁用',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',
    INDEX idx_user_email (`email`),
    INDEX idx_user_status (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='用户表';

-- 订单表
CREATE TABLE `order` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '订单ID',
    `user_id` BIGINT NOT NULL COMMENT '用户ID',
    `order_no` VARCHAR(32) NOT NULL COMMENT '订单号',
    `total_amount` DECIMAL(12,2) NOT NULL COMMENT '总金额',
    `status` TINYINT DEFAULT 0 COMMENT '状态: 0=待支付 1=已支付 2=已发货 3=已完成 4=已取消',
    `payment_method` VARCHAR(20) DEFAULT NULL COMMENT '支付方式',
    `paid_at` DATETIME DEFAULT NULL COMMENT '支付时间',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_order_user (`user_id`),
    INDEX idx_order_status (`status`),
    INDEX idx_order_no (`order_no`),
    CONSTRAINT fk_order_user FOREIGN KEY (`user_id`) REFERENCES `user`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单表';

-- 订单明细表
CREATE TABLE `order_item` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '明细ID',
    `order_id` BIGINT NOT NULL COMMENT '订单ID',
    `product_id` BIGINT NOT NULL COMMENT '商品ID',
    `product_name` VARCHAR(200) NOT NULL COMMENT '商品名称',
    `price` DECIMAL(10,2) NOT NULL COMMENT '单价',
    `quantity` INT NOT NULL DEFAULT 1 COMMENT '数量',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_item_order (`order_id`),
    INDEX idx_item_product (`product_id`),
    CONSTRAINT fk_item_order FOREIGN KEY (`order_id`) REFERENCES `order`(`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='订单明细表';

-- 商品表
CREATE TABLE `product` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '商品ID',
    `name` VARCHAR(200) NOT NULL COMMENT '商品名称',
    `category_id` BIGINT DEFAULT NULL COMMENT '分类ID',
    `price` DECIMAL(10,2) NOT NULL COMMENT '价格',
    `stock` INT DEFAULT 0 COMMENT '库存',
    `description` TEXT COMMENT '商品描述',
    `status` TINYINT DEFAULT 1 COMMENT '状态: 1=上架 0=下架',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_product_category (`category_id`),
    INDEX idx_product_status (`status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='商品表';

-- 分类表
CREATE TABLE `category` (
    `id` BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '分类ID',
    `name` VARCHAR(100) NOT NULL COMMENT '分类名称',
    `parent_id` BIGINT DEFAULT NULL COMMENT '父分类ID',
    `sort_order` INT DEFAULT 0 COMMENT '排序',
    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_category_parent (`parent_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='分类表';

-- 插入测试数据
INSERT INTO `user` (`username`, `email`, `phone`, `age`, `status`) VALUES
('admin', 'admin@example.com', '13800138000', 30, 1),
('testuser', 'test@example.com', NULL, 25, 1),
('guest', NULL, NULL, NULL, 0);

INSERT INTO `category` (`id`, `name`, `parent_id`, `sort_order`) VALUES
(1, '电子产品', NULL, 1),
(2, '服装', NULL, 2),
(3, '手机', 1, 1),
(4, '电脑', 1, 2);

INSERT INTO `product` (`name`, `category_id`, `price`, `stock`, `description`, `status`) VALUES
('iPhone 15', 3, 6999.00, 100, '最新款智能手机', 1),
('MacBook Pro', 4, 12999.00, 50, '高性能笔记本电脑', 1),
('T恤', 2, 99.00, 500, '纯棉圆领T恤', 1);

INSERT INTO `order` (`user_id`, `order_no`, `total_amount`, `status`, `payment_method`) VALUES
(1, 'ORD20260716001', 6999.00, 1, 'wechat'),
(1, 'ORD20260716002', 13098.00, 3, 'alipay'),
(2, 'ORD20260716003', 99.00, 0, NULL);

INSERT INTO `order_item` (`order_id`, `product_id`, `product_name`, `price`, `quantity`) VALUES
(1, 1, 'iPhone 15', 6999.00, 1),
(2, 2, 'MacBook Pro', 12999.00, 1),
(2, 3, 'T恤', 99.00, 1),
(3, 3, 'T恤', 99.00, 1);
