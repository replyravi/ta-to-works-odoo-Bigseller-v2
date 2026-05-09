#!/usr/bin/env bash
# Switch vct_bigseller to use Odoo 16 compatible views (tree, attrs syntax).
# Run this before starting a local Odoo 16 server.
set -e
MANIFEST="$(dirname "$0")/../__manifest__.py"

sed -i '' "s|'views_v18/bigseller_sale_wizard.xml'|'views/bigseller_sale_wizard.xml'|g" "$MANIFEST"
sed -i '' "s|'views_v18/sale_order_view.xml'|'views/sale_order_view.xml'|g" "$MANIFEST"
sed -i '' "s|'views_v18/res_config_settings_view.xml'|'views/res_config_settings_view.xml'|g" "$MANIFEST"
sed -i '' "s|'version': '18.0|'version': '16.0|g" "$MANIFEST"

echo "vct_bigseller switched to Odoo 16 mode (views/). Restart Odoo with -u vct_bigseller."
