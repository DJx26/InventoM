import pandas as pd
import os
from datetime import datetime, date
import streamlit as st

class DataManager:
    API_VERSION = 3
    def __init__(self):
        self.api_version = self.API_VERSION
         # Always anchor data directory to the project folder, not current working directory
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(base_dir, "data")
        self.transactions_file = os.path.join(self.data_dir, "transactions.csv")
        self.stock_file = os.path.join(self.data_dir, "current_stock.csv")
        self.templates_file = os.path.join(self.data_dir, "templates.csv")
        self._initialize_data_files()

    def _initialize_data_files(self):
        """Create data directory and initialize CSV files if they don't exist."""
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

        # Initialize transactions file
        if not os.path.exists(self.transactions_file):
            transactions_df = pd.DataFrame(columns=[
                'id', 'category', 'subcategory', 'transaction_type', 
                'quantity', 'date', 'supplier', 'notes', 'created_at'
            ])
            transactions_df.to_csv(self.transactions_file, index=False)

        # Initialize stock file
        if not os.path.exists(self.stock_file):
            stock_df = pd.DataFrame(columns=[
                'category', 'subcategory', 'remaining_qty', 'last_updated', 'supplier'
            ])
            stock_df.to_csv(self.stock_file, index=False)

        # Initialize templates file
        if not os.path.exists(self.templates_file):
            templates_df = pd.DataFrame(columns=[
                'id', 'template_name', 'category', 'subcategory', 'supplier', 'created_at'
            ])
            templates_df.to_csv(self.templates_file, index=False)

    def add_transaction(self, category, subcategory, transaction_type, quantity, transaction_date, supplier="", notes=""):
        """Add a new transaction and update stock levels."""
        try:
            # Load existing transactions
            transactions_df = pd.read_csv(self.transactions_file)

            # Generate new transaction ID
            new_id = len(transactions_df) + 1

            # Create new transaction record
            # Normalize inputs
            category = str(category).strip()
            subcategory = str(subcategory).strip()
            transaction_type = str(transaction_type).strip().title()
            quantity = float(quantity)
            new_transaction = {
                'id': new_id,
                'category': category,
                'subcategory': subcategory,
                'transaction_type': transaction_type,
                'quantity': quantity,
                'date': transaction_date.strftime('%Y-%m-%d') if isinstance(transaction_date, (datetime, date)) else str(transaction_date),
                'supplier': supplier,
                'notes': notes,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # Add transaction to dataframe
            new_transaction_df = pd.DataFrame([new_transaction])
            transactions_df = pd.concat([transactions_df, new_transaction_df], ignore_index=True)

            # Save transactions
            transactions_df.to_csv(self.transactions_file, index=False)

            # Update stock levels
            self._update_stock_levels(category, subcategory, transaction_type, quantity, supplier)

            return True

        except Exception as e:
            st.error(f"Error adding transaction: {str(e)}")
            return False

    def _update_stock_levels(self, category, subcategory, transaction_type, quantity, supplier=""):
        """Update current stock levels based on transaction."""
        try:
            # Load current stock
            stock_df = pd.read_csv(self.stock_file)
            # Ensure numeric type for remaining_qty
            if 'remaining_qty' in stock_df.columns:
                stock_df['remaining_qty'] = pd.to_numeric(stock_df['remaining_qty'], errors='coerce').fillna(0)

            # Find existing stock record
            category = str(category).strip()
            subcategory = str(subcategory).strip()
            transaction_type = str(transaction_type).strip().title()
            mask = (stock_df['category'] == category) & (stock_df['subcategory'] == subcategory)
            existing_record = stock_df[mask]

            # Compute current and new qty safely
            current_qty = float(existing_record.iloc[0]['remaining_qty']) if not existing_record.empty else 0.0
            delta = float(quantity)
            if transaction_type == "Stock In":
                new_qty = current_qty + delta
            else:  # Stock Out
                new_qty = max(0.0, current_qty - delta)

            if not existing_record.empty:
                # Update existing record
                stock_df.loc[mask, 'remaining_qty'] = new_qty
                stock_df.loc[mask, 'last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                if supplier:  # Update supplier if provided
                    stock_df.loc[mask, 'supplier'] = supplier
            else:
                # Create new stock record
                new_stock_record = {
                    'category': category,
                    'subcategory': subcategory,
                    'remaining_qty': new_qty,
                    'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'supplier': supplier
                }
                new_stock_df = pd.DataFrame([new_stock_record])
                stock_df = pd.concat([stock_df, new_stock_df], ignore_index=True)

            # Save updated stock
            stock_df.to_csv(self.stock_file, index=False)

        except Exception as e:
            st.error(f"Error updating stock levels: {str(e)}")

    def get_current_stock(self, category):
        """Get current stock levels for a specific category."""
        try:
            stock_df = pd.read_csv(self.stock_file)
            category_stock = stock_df[stock_df['category'] == category].copy()
            # Ensure numeric type before filtering
            if 'remaining_qty' in category_stock.columns:
                category_stock['remaining_qty'] = pd.to_numeric(category_stock['remaining_qty'], errors='coerce').fillna(0)

            # Filter out zero quantities
            category_stock = category_stock[category_stock['remaining_qty'] > 0]

            # Sort by subcategory
            if not category_stock.empty:
                category_stock = category_stock.sort_values('subcategory')

            return category_stock

        except Exception as e:
            st.error(f"Error getting current stock: {str(e)}")
            return pd.DataFrame()

    def get_subcategories(self, category):
        """Get existing subcategories for a category."""
        try:
            stock_df = pd.read_csv(self.stock_file)
            transactions_df = pd.read_csv(self.transactions_file)

            # Get subcategories from both stock and transactions
            stock_subcategories = stock_df[stock_df['category'] == category]['subcategory'].unique()
            transaction_subcategories = transactions_df[transactions_df['category'] == category]['subcategory'].unique()

            # Combine and remove duplicates
            all_subcategories = list(set(list(stock_subcategories) + list(transaction_subcategories)))
            all_subcategories = [sub for sub in all_subcategories if pd.notna(sub) and sub != ""]

            return sorted(all_subcategories)

        except Exception as e:
            st.error(f"Error getting subcategories: {str(e)}")
            return []

    def delete_subcategory(self, category, subcategory, delete_transactions=False):
        """Delete a subcategory from current stock, optionally remove its transactions."""
        try:
            # Normalize inputs
            category_norm = str(category).strip().lower()
            subcategory_norm = str(subcategory).strip().lower()

            # Remove from current stock
            stock_df = pd.read_csv(self.stock_file)

            if not stock_df.empty:
                # Build normalized columns to match robustly
                stock_df['_cat_norm'] = stock_df['category'].astype(str).str.strip().str.lower()
                stock_df['_sub_norm'] = stock_df['subcategory'].astype(str).str.strip().str.lower()

                before_stock = len(stock_df)
                stock_df = stock_df[~((stock_df['_cat_norm'] == category_norm) & (stock_df['_sub_norm'] == subcategory_norm))]
                removed_stock = before_stock - len(stock_df)

                # Drop helper cols before saving
                stock_df = stock_df.drop(columns=['_cat_norm', '_sub_norm'], errors='ignore')
                stock_df.to_csv(self.stock_file, index=False)
            else:
                removed_stock = 0

            removed_txs = 0
            if delete_transactions:
                tx_df = pd.read_csv(self.transactions_file)
                if not tx_df.empty:
                    tx_df['_cat_norm'] = tx_df['category'].astype(str).str.strip().str.lower()
                    tx_df['_sub_norm'] = tx_df['subcategory'].astype(str).str.strip().str.lower()

                    before_tx = len(tx_df)
                    tx_df = tx_df[~((tx_df['_cat_norm'] == category_norm) & (tx_df['_sub_norm'] == subcategory_norm))]
                    removed_txs = before_tx - len(tx_df)

                    tx_df = tx_df.drop(columns=['_cat_norm', '_sub_norm'], errors='ignore')
                    tx_df.to_csv(self.transactions_file, index=False)

            return True, removed_stock, removed_txs
        except Exception as e:
            st.error(f"Error deleting subcategory: {str(e)}")
            return False, 0, 0

    def get_transaction_history(self, category, subcategory=None, limit=None):
        """Get transaction history for a category and optionally subcategory."""
        try:
            transactions_df = pd.read_csv(self.transactions_file)

            # Filter by category
            filtered_df = transactions_df[transactions_df['category'] == category]

            # Filter by subcategory if specified
            if subcategory:
                filtered_df = filtered_df[filtered_df['subcategory'] == subcategory]

            # Sort by date descending
            if not filtered_df.empty:
                filtered_df = filtered_df.sort_values('date', ascending=False)

                if limit:
                    filtered_df = filtered_df.head(limit)

            return filtered_df

        except Exception as e:
            st.error(f"Error getting transaction history: {str(e)}")
            return pd.DataFrame()

    def get_recent_transactions(self, limit=10):
        """Get recent transactions across all categories."""
        try:
            transactions_df = pd.read_csv(self.transactions_file)

            if not transactions_df.empty:
                # Sort by created_at or date, descending
                sort_column = 'created_at' if 'created_at' in transactions_df.columns else 'date'
                recent_transactions = transactions_df.sort_values(sort_column, ascending=False).head(limit)
                return recent_transactions
            else:
                return pd.DataFrame()

        except Exception as e:
            st.error(f"Error getting recent transactions: {str(e)}")
            return pd.DataFrame()

    def get_all_transactions(self):
        """Get all transactions."""
        try:
            transactions_df = pd.read_csv(self.transactions_file)
            return transactions_df
        except Exception as e:
            st.error(f"Error getting all transactions: {str(e)}")
            return pd.DataFrame()

    def bulk_upload(self, category, df, include_supplier=False):
        """Bulk upload transactions from Excel file."""
        try:
            # Normalize column names: strip whitespace and convert to lowercase for comparison
            df.columns = df.columns.str.strip()
            normalized_df_columns = {col.lower(): col for col in df.columns}
            
            required_columns = ['subcategory', 'transaction_type', 'quantity', 'date']
            if include_supplier:
                required_columns.append('supplier')

            # Check if required columns exist (case-insensitive, ignoring whitespace)
            missing_columns = []
            column_mapping = {}
            for req_col in required_columns:
                found = False
                for df_col_lower, df_col_original in normalized_df_columns.items():
                    if df_col_lower == req_col.lower():
                        column_mapping[req_col] = df_col_original
                        found = True
                        break
                if not found:
                    missing_columns.append(req_col)
            
            if missing_columns:
                st.error(
                    f"❌ **Missing required columns:** {', '.join(missing_columns)}\n\n"
                    f"**Found columns in your file:** {', '.join(df.columns.tolist())}\n\n"
                    f"**Required columns:** {', '.join(required_columns)}\n\n"
                    f"**Optional columns:** notes"
                )
                return 0
            
            # Rename columns to standardized names using the mapping
            df = df.rename(columns=column_mapping)

            success_count = 0

            for index, row in df.iterrows():
                try:
                    # Validate required fields
                    if pd.isna(row['subcategory']) or pd.isna(row['quantity']) or pd.isna(row['date']):
                        continue

                    # Parse date
                    transaction_date = pd.to_datetime(row['date']).date()

                    # Get values with defaults
                    subcategory = str(row['subcategory']).strip()
                    transaction_type = str(row['transaction_type']).strip().title()
                    quantity = float(row['quantity'])
                    supplier = str(row.get('supplier', '')).strip() if include_supplier else ""
                    notes = str(row.get('notes', '')).strip()

                    # Validate transaction type
                    if transaction_type not in ['Stock In', 'Stock Out']:
                        continue

                    # Add transaction
                    if self.add_transaction(
                        category=category,
                        subcategory=subcategory,
                        transaction_type=transaction_type,
                        quantity=quantity,
                        transaction_date=transaction_date,
                        supplier=supplier,
                        notes=notes
                    ):
                        success_count += 1

                except Exception as row_error:
                    st.warning(f"Error processing row {index + 1}: {str(row_error)}")
                    continue

            return success_count

        except Exception as e:
            st.error(f"Error in bulk upload: {str(e)}")
            return 0

    def save_template(self, template_name, category, subcategory, supplier=""):
        """Save a product template for quick entry."""
        try:
            templates_df = pd.read_csv(self.templates_file)

            # Check if template name already exists for this category
            existing = templates_df[
                (templates_df['template_name'] == template_name) & 
                (templates_df['category'] == category)
            ]

            if len(existing) > 0:
                st.error(f"Template '{template_name}' already exists for {category}.")
                return False

            # Generate new template ID
            new_id = len(templates_df) + 1

            # Create new template record
            new_template = {
                'id': new_id,
                'template_name': template_name,
                'category': category,
                'subcategory': subcategory,
                'supplier': supplier,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            # Add template to dataframe
            new_template_df = pd.DataFrame([new_template])
            templates_df = pd.concat([templates_df, new_template_df], ignore_index=True)

            # Save templates
            templates_df.to_csv(self.templates_file, index=False)

            return True

        except Exception as e:
            st.error(f"Error saving template: {str(e)}")
            return False

    def get_templates(self, category):
        """Get templates for a specific category."""
        try:
            templates_df = pd.read_csv(self.templates_file)
            category_templates = templates_df[templates_df['category'] == category]
            return category_templates
        except Exception as e:
            st.error(f"Error getting templates: {str(e)}")
            return pd.DataFrame()

    def get_template_by_name(self, category, template_name):
        """Get a specific template by name and category."""
        try:
            templates_df = pd.read_csv(self.templates_file)
            template = templates_df[
                (templates_df['category'] == category) & 
                (templates_df['template_name'] == template_name)
            ]
            if len(template) > 0:
                return template.iloc[0].to_dict()
            return None
        except Exception as e:
            st.error(f"Error getting template: {str(e)}")
            return None

    def delete_template(self, category, template_name):
        """Delete a template."""
        try:
            templates_df = pd.read_csv(self.templates_file)
            templates_df = templates_df[
                ~((templates_df['category'] == category) & 
                  (templates_df['template_name'] == template_name))
            ]
            templates_df.to_csv(self.templates_file, index=False)
            return True
        except Exception as e:
            st.error(f"Error deleting template: {str(e)}")
            return False
