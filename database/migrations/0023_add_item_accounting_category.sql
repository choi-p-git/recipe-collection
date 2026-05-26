ALTER TABLE item
ADD COLUMN item_category TEXT NOT NULL DEFAULT 'grocery'
CHECK (item_category IN ('meat', 'grocery', 'frozen', 'beverages', 'dairy', 'bakery', 'produce'));

CREATE INDEX IF NOT EXISTS idx_item_category
ON item(item_category);
