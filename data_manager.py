# FIXED & HARDENED VERSION (schema-safe, Arrow-safe)
# Key fixes:
# 1. Enforce numeric schema for `id` on READ and WRITE
# 2. Fix UnboundLocalError by initializing variables
# 3. Fix recalculate_stock() bug (used undefined stock_df)
# 4. Prevent mixed dtypes before Streamlit/Arrow

import pandas as pd
import os
from datetime import datetime, date
import streamlit as st
from sheets_manager import SheetsManager
import gspread

def clear_transaction_cache():
    st.cache_data.clear()


class DataManager:
    API_VERSION = 5

    def __init__(self):
        self.api_version = self.API_VERSION
        self.sheets_manager = SheetsManager()
        self._use_sheets = None

        self.transactions_sheet = "Transactions"
        self.stock_sheet = "Current Stock"
        self.templates_sheet = "Templates"

        self.transactions_headers = [
            'id', 'category', 'subcategory', 'transaction_type',
            'quantity', 'date', 'supplier', 'notes', 'created_at'
        ]
        self.stock_headers = [
            'category', 'subcategory', 'remaining_qty', 'last_updated', 'supplier'
        ]
        self.templates_headers = [
            'id', 'template_name', 'category', 'subcategory', 'supplier', 'created_at'
        ]

        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.data_dir = os.path.join(base_dir, "data")
        self.transactions_file = os.path.join(self.data_dir, "transactions.csv")
        self.stock_file = os.path.join(self.data_dir, "current_stock.csv")
        self.templates_file = os.path.join(self.data_dir, "templates.csv")

        self._initialize_data_files()

    # ------------------ helpers ------------------
    def _get_use_sheets(self):
        if self._use_sheets is None:
            try:
                self._use_sheets = self.sheets_manager.is_configured()
            except Exception:
                self._use_sheets = False
        return self._use_sheets

    def _normalize_ids(self, df: pd.DataFrame) -> pd.DataFrame:
        if 'id' in df.columns:
            df['id'] = pd.to_numeric(df['id'], errors='coerce').astype('Int64')
        return df

    def _initialize_data_files(self):
        if not self._get_use_sheets():
            os.makedirs(self.data_dir, exist_ok=True)
            if not os.path.exists(self.transactions_file):
                pd.DataFrame(columns=self.transactions_headers).to_csv(self.transactions_file, index=False)
            if not os.path.exists(self.stock_file):
                pd.DataFrame(columns=self.stock_headers).to_csv(self.stock_file, index=False)
            if not os.path.exists(self.templates_file):
                pd.DataFrame(columns=self.templates_headers).to_csv(self.templates_file, index=False)

    # ------------------ READ / WRITE ------------------
    @st.cache_data(ttl=600)
    def _read_transactions(self) -> pd.DataFrame:
        if self._get_use_sheets():
            df = self.sheets_manager.read_dataframe(self.transactions_sheet, self.transactions_headers)
        else:
            df = pd.read_csv(self.transactions_file)
        return self._normalize_ids(df)

    def _write_transactions(self, df: pd.DataFrame) -> bool:
        df = self._normalize_ids(df)
        if self._get_use_sheets():
            ok = self.sheets_manager.write_dataframe(self.transactions_sheet, df, self.transactions_headers)
        else:
            df.to_csv(self.transactions_file, index=False)
            ok = True
        if ok:
            st.cache_data.clear()
        return ok

    @st.cache_data(ttl=600)
    def _read_stock(self) -> pd.DataFrame:
        if self._get_use_sheets():
            df = self.sheets_manager.read_dataframe(self.stock_sheet, self.stock_headers)
        else:
            df = pd.read_csv(self.stock_file)
        if 'remaining_qty' in df.columns:
            df['remaining_qty'] = pd.to_numeric(df['remaining_qty'], errors='coerce').fillna(0)
        return df

    def _write_stock(self, df: pd.DataFrame) -> bool:
        if self._get_use_sheets():
            ok = self.sheets_manager.write_dataframe(self.stock_sheet, df, self.stock_headers)
        else:
            df.to_csv(self.stock_file, index=False)
            ok = True
        if ok:
            st.cache_data.clear()
        return ok

    # ------------------ CORE LOGIC ------------------
    def add_transaction(self, category, subcategory, transaction_type,
                        quantity, transaction_date, supplier="", notes=""):
        transactions_df = None
        try:
            transactions_df = self._read_transactions()

            # generate ID safely
            if not transactions_df.empty and transactions_df['id'].notna().any():
                new_id = int(transactions_df['id'].max()) + 1
            else:
                new_id = 1

            new_tx = {
                'id': new_id,
                'category': str(category).strip(),
                'subcategory': str(subcategory).strip(),
                'transaction_type': str(transaction_type).strip().title(),
                'quantity': float(quantity),
                'date': transaction_date.strftime('%Y-%m-%d') if isinstance(transaction_date, (datetime, date)) else str(transaction_date),
                'supplier': supplier,
                'notes': notes,
                'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }

            transactions_df = pd.concat([transactions_df, pd.DataFrame([new_tx])], ignore_index=True)

            if not self._write_transactions(transactions_df):
                raise RuntimeError("Failed to save transactions")

            if not self._update_stock_levels(category, subcategory, transaction_type, quantity, supplier):
                raise RuntimeError("Failed to update stock")

            return True
        except Exception as e:
            st.error(f"Error adding transaction: {e}")
            return False

    def _update_stock_levels(self, category, subcategory, transaction_type, quantity, supplier=""):
        try:
            stock_df = self._read_stock()

            mask = (
                (stock_df['category'] == str(category).strip()) &
                (stock_df['subcategory'] == str(subcategory).strip())
            )
            existing = stock_df[mask]

            current = float(existing.iloc[0]['remaining_qty']) if not existing.empty else 0.0
            delta = float(quantity)
            new_qty = current + delta if transaction_type == 'Stock In' else max(0.0, current - delta)

            if not existing.empty:
                stock_df.loc[mask, 'remaining_qty'] = new_qty
                stock_df.loc[mask, 'last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            else:
                stock_df = pd.concat([
                    stock_df,
                    pd.DataFrame([{
                        'category': category,
                        'subcategory': subcategory,
                        'remaining_qty': new_qty,
                        'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'supplier': supplier
                    }])
                ], ignore_index=True)

            return self._write_stock(stock_df)
        except Exception as e:
            st.error(f"Error updating stock levels: {e}")
            return False

    def recalculate_stock(self) -> bool:
        try:
            tx = self._read_transactions()
            if tx.empty:
                return self._write_stock(pd.DataFrame(columns=self.stock_headers))

            tx['quantity'] = pd.to_numeric(tx['quantity'], errors='coerce').fillna(0)
            tx['transaction_type'] = tx['transaction_type'].astype(str).str.title()
            tx['delta'] = tx.apply(lambda r: r['quantity'] if r['transaction_type'] == 'Stock In' else -r['quantity'], axis=1)

            grouped = tx.groupby(['category', 'subcategory'], as_index=False)['delta'].sum()
            grouped['remaining_qty'] = grouped['delta'].clip(lower=0)
            grouped['last_updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            grouped['supplier'] = ""

            stock_df = grouped[['category', 'subcategory', 'remaining_qty', 'last_updated', 'supplier']]
            return self._write_stock(stock_df)
        except Exception as e:
            st.error(f"Error recalculating stock: {e}")
            return False
