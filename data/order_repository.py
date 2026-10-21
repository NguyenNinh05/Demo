"""Data Layer - OrderRepository (orders, order_item, payment, customer)."""


class OrderRepository:

    def __init__(self, db):
        self.db = db

    def find_order(self, order_id):
        return self.db.query_one(
            "SELECT * FROM orders WHERE upper(order_id) = upper(%(id)s)", {"id": str(order_id)})

    def orders_of_customer(self, customer_id):
        return self.db.query(
            "SELECT * FROM orders WHERE customer_id = %(c)s ORDER BY order_date DESC",
            {"c": customer_id})

    def latest_order(self, customer_id):
        orders = self.orders_of_customer(customer_id)
        return orders[0] if orders else None

    def items_of(self, order_id):
        return self.db.query("""
            SELECT i.product_id, i.quantity, i.unit_price, p.name, p.color, p.image_path
            FROM order_item i JOIN product p USING (product_id)
            WHERE i.order_id = %(id)s ORDER BY i.order_item_id""", {"id": order_id})

    def payments_of(self, order_id):
        return self.db.query(
            "SELECT payment_method, payment_date, amount, status FROM payment "
            "WHERE order_id = %(id)s", {"id": order_id})

    def customer(self, customer_id):
        return self.db.query_one(
            "SELECT customer_id, full_name, email FROM customer WHERE customer_id = %(c)s",
            {"c": customer_id})
