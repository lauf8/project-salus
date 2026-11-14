from alembic import op


revision = 'e8cd3456f708'
down_revision = 'd7bc2345e6f7'
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE food_products (
	id SERIAL NOT NULL,
	name VARCHAR NOT NULL,
	category VARCHAR NOT NULL,
	is_plain_water BOOLEAN NOT NULL,
	preservation_method VARCHAR NOT NULL,
	physical_form VARCHAR NOT NULL,
	reference_quantity NUMERIC(20, 6) NOT NULL,
	reference_unit VARCHAR NOT NULL,
	reference_basis VARCHAR NOT NULL,
	unit_equivalences JSON NOT NULL,
	energy_kcal NUMERIC(20, 6),
	protein_g NUMERIC(20, 6),
	carbohydrate_g NUMERIC(20, 6),
	fat_g NUMERIC(20, 6),
	fiber_g NUMERIC(20, 6),
	sodium_mg NUMERIC(20, 6),
	preparation_method VARCHAR NOT NULL,
	preparation_water_ml NUMERIC(20, 6),
	is_active BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_food_products_basis CHECK (reference_basis IN ('stored', 'prepared')),
	CONSTRAINT ck_food_products_unit CHECK (reference_unit IN ('g', 'ml', 'serving', 'package', 'piece')),
	CONSTRAINT ck_food_products_preservation CHECK (preservation_method IN ('fresh', 'dehydrated', 'freeze_dried', 'thermostabilized', 'natural_form', 'other')),
	CONSTRAINT ck_food_products_form CHECK (physical_form IN ('solid', 'paste', 'powder', 'liquid')),
	CONSTRAINT ck_food_products_preparation CHECK (preparation_method IN ('ready_to_consume', 'rehydrate', 'heat', 'rehydrate_and_heat')),
	CONSTRAINT ck_food_products_nutrients CHECK (energy_kcal >= 0 AND protein_g >= 0 AND carbohydrate_g >= 0 AND fat_g >= 0 AND fiber_g >= 0 AND sodium_mg >= 0 AND preparation_water_ml >= 0),
	CONSTRAINT ck_food_products_category CHECK (category IN ('food', 'beverage')),
	CONSTRAINT ck_food_products_water CHECK (NOT is_plain_water OR category = 'beverage'),
	CONSTRAINT ck_food_products_reference CHECK (reference_quantity > 0)
)""")
    op.execute('CREATE INDEX ix_food_products_name ON food_products (name)')
    op.execute("""CREATE TABLE mission_food_lots (
	id SERIAL NOT NULL,
	mission_id INTEGER NOT NULL,
	food_product_id INTEGER NOT NULL,
	lot_code VARCHAR NOT NULL,
	expiration_date DATE NOT NULL,
	initial_quantity NUMERIC(20, 6) NOT NULL,
	remaining_quantity NUMERIC(20, 6) NOT NULL,
	stock_unit VARCHAR NOT NULL,
	stock_basis VARCHAR NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_mission_food_lots_basis CHECK (stock_basis IN ('stored', 'prepared')),
	CONSTRAINT uq_mission_food_lots_code UNIQUE (mission_id, food_product_id, lot_code),
	CONSTRAINT uq_mission_food_lots_product UNIQUE (id, food_product_id),
	CONSTRAINT ck_mission_food_lots_balance CHECK (initial_quantity > 0 AND remaining_quantity >= 0 AND remaining_quantity <= initial_quantity),
	FOREIGN KEY(mission_id) REFERENCES missions (id),
	FOREIGN KEY(food_product_id) REFERENCES food_products (id)
)""")
    op.execute('CREATE INDEX ix_mission_food_lots_food_product_id ON mission_food_lots (food_product_id)')
    op.execute('CREATE INDEX ix_mission_food_lots_mission_id ON mission_food_lots (mission_id)')
    op.execute("""CREATE TABLE meal_logs (
	id SERIAL NOT NULL,
	mission_id INTEGER NOT NULL,
	mission_member_id INTEGER NOT NULL,
	consumed_at TIMESTAMP WITH TIME ZONE NOT NULL,
	meal_type VARCHAR NOT NULL,
	notes VARCHAR,
	recorded_by_user_id INTEGER NOT NULL,
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
	revision INTEGER NOT NULL,
	is_deleted BOOLEAN NOT NULL,
	client_request_id VARCHAR,
	submission_hash VARCHAR,
	PRIMARY KEY (id),
	CONSTRAINT fk_meal_logs_member_mission FOREIGN KEY(mission_member_id, mission_id) REFERENCES mission_members (id, mission_id),
	CONSTRAINT uq_meal_logs_request UNIQUE (mission_id, client_request_id),
	CONSTRAINT ck_meal_logs_type CHECK (meal_type IN ('breakfast', 'lunch', 'dinner', 'snack', 'hydration')),
	CONSTRAINT ck_meal_logs_revision CHECK (revision > 0),
	FOREIGN KEY(mission_id) REFERENCES missions (id),
	FOREIGN KEY(recorded_by_user_id) REFERENCES users (id)
)""")
    op.execute('CREATE INDEX ix_meal_logs_mission_id ON meal_logs (mission_id)')
    op.execute('CREATE INDEX ix_meal_logs_mission_member_id ON meal_logs (mission_member_id)')
    op.execute("""CREATE TABLE meal_log_items (
	id SERIAL NOT NULL,
	meal_log_id INTEGER NOT NULL,
	food_product_id INTEGER NOT NULL,
	lot_id INTEGER NOT NULL,
	consumed_quantity NUMERIC(20, 6) NOT NULL,
	consumed_unit VARCHAR NOT NULL,
	consumed_basis VARCHAR NOT NULL,
	stock_quantity_used NUMERIC(20, 6) NOT NULL,
	preparation_water_used_ml NUMERIC(20, 6),
	preparation_water_lot_id INTEGER,
	product_snapshot JSON NOT NULL,
	nutrients JSON NOT NULL,
	beverage_volume_ml NUMERIC(20, 6),
	plain_water_volume_ml NUMERIC(20, 6),
	revision INTEGER NOT NULL,
	is_active BOOLEAN NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT fk_meal_log_items_lot_product FOREIGN KEY(lot_id, food_product_id) REFERENCES mission_food_lots (id, food_product_id),
	CONSTRAINT ck_meal_log_items_quantities CHECK (consumed_quantity > 0 AND stock_quantity_used > 0),
	CONSTRAINT ck_meal_log_items_preparation_water CHECK (preparation_water_used_ml IS NULL OR preparation_water_used_ml >= 0),
	FOREIGN KEY(meal_log_id) REFERENCES meal_logs (id),
	FOREIGN KEY(food_product_id) REFERENCES food_products (id),
	FOREIGN KEY(preparation_water_lot_id) REFERENCES mission_food_lots (id)
)""")
    op.execute('CREATE INDEX ix_meal_log_items_lot_id ON meal_log_items (lot_id)')
    op.execute('CREATE INDEX ix_meal_log_items_meal_log_id ON meal_log_items (meal_log_id)')
    op.execute("""CREATE TABLE food_stock_movements (
	id SERIAL NOT NULL,
	lot_id INTEGER NOT NULL,
	meal_log_item_id INTEGER,
	quantity NUMERIC(20, 6) NOT NULL,
	stock_unit VARCHAR NOT NULL,
	movement_type VARCHAR NOT NULL,
	purpose VARCHAR NOT NULL,
	reverses_movement_id INTEGER,
	recorded_by_user_id INTEGER NOT NULL,
	recorded_at TIMESTAMP WITH TIME ZONE NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_food_stock_movements_reversal UNIQUE (reverses_movement_id),
	CONSTRAINT ck_food_stock_movements_quantity CHECK ((movement_type = 'consumption' AND quantity < 0) OR (movement_type IN ('initial', 'reversal') AND quantity > 0)),
	CONSTRAINT ck_food_stock_movements_type CHECK (movement_type IN ('initial', 'consumption', 'reversal')),
	FOREIGN KEY(lot_id) REFERENCES mission_food_lots (id),
	FOREIGN KEY(meal_log_item_id) REFERENCES meal_log_items (id),
	FOREIGN KEY(reverses_movement_id) REFERENCES food_stock_movements (id),
	FOREIGN KEY(recorded_by_user_id) REFERENCES users (id)
)""")
    op.execute('CREATE INDEX ix_food_stock_movements_lot_id ON food_stock_movements (lot_id)')
    op.execute('CREATE INDEX ix_food_stock_movements_meal_log_item_id ON food_stock_movements (meal_log_item_id)')
    op.execute("INSERT INTO food_products (name, category, is_plain_water, preservation_method, physical_form, reference_quantity, reference_unit, reference_basis, unit_equivalences, energy_kcal, protein_g, carbohydrate_g, fat_g, fiber_g, sodium_mg, preparation_method, is_active) VALUES ('Water', 'beverage', true, 'natural_form', 'liquid', 100, 'ml', 'stored', '[]', 0, 0, 0, 0, 0, 0, 'ready_to_consume', true)")


def downgrade():
    op.drop_table('food_stock_movements')
    op.drop_table('meal_log_items')
    op.drop_table('meal_logs')
    op.drop_table('mission_food_lots')
    op.drop_table('food_products')
