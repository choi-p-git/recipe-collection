UPDATE item
SET yield_unit = 'L'
WHERE yield_unit = 'l';

UPDATE item
SET mass_unit = 'L'
WHERE mass_unit = 'l';

UPDATE item
SET volume_unit = 'L'
WHERE volume_unit = 'l';

UPDATE item
SET nutrition_serving_mass_unit = 'L'
WHERE nutrition_serving_mass_unit = 'l';

UPDATE item
SET nutrition_serving_volume_unit = 'L'
WHERE nutrition_serving_volume_unit = 'l';

UPDATE item
SET serving_size_unit = 'L'
WHERE serving_size_unit = 'l';

UPDATE recipe_component
SET component_unit = 'L'
WHERE component_unit = 'l';

UPDATE menu_forecast
SET forecast_yield_unit = 'L'
WHERE forecast_yield_unit = 'l';
