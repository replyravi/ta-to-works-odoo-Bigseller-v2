#!/usr/bin/env bash
# Switch vct_bigseller back to Odoo 18 compatible views (list, direct invisible).
# Run this before pushing to GitHub / deploying to staging or production.
set -e
MANIFEST="$(dirname "$0")/../__manifest__.py"

sed -i '' "s|'views/bigseller_sale_wizard.xml'|'views_v18/bigseller_sale_wizard.xml'|g" "$MANIFEST"
sed -i '' "s|'views/sale_order_view.xml'|'views_v18/sale_order_view.xml'|g" "$MANIFEST"
sed -i '' "s|'views/res_config_settings_view.xml'|'views_v18/res_config_settings_view.xml'|g" "$MANIFEST"
sed -i '' "s|'version': '16.0|'version': '18.0|g" "$MANIFEST"

echo "vct_bigseller switched to Odoo 18 mode (views_v18/). Ready to push to GitHub."
