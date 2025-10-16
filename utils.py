from datetime import datetime, date
import pandas as pd

def format_date(date_input):
    """Format date input to string."""
    if isinstance(date_input, (datetime, date)):
        return date_input.strftime('%Y-%m-%d')
    return str(date_input)

def validate_quantity(quantity):
    """Validate quantity input."""
    try:
        qty = float(quantity)
        return qty >= 0, qty
    except (ValueError, TypeError):
        return False, 0

def parse_excel_date(date_value):
    """Parse various date formats from Excel."""
    if pd.isna(date_value):
        return None
    
    if isinstance(date_value, (datetime, date)):
        return date_value.date() if isinstance(date_value, datetime) else date_value
    
    try:
        # Try parsing as string
        parsed_date = pd.to_datetime(str(date_value))
        return parsed_date.date()
    except:
        return None

def format_quantity(quantity):
    """Format quantity for display."""
    try:
        return f"{float(quantity):,.0f}"
    except (ValueError, TypeError):
        return "0"

def validate_excel_columns(df, required_columns):
    """Validate that DataFrame has required columns."""
    missing_columns = [col for col in required_columns if col not in df.columns]
    return len(missing_columns) == 0, missing_columns

def clean_string_input(input_str):
    """Clean and validate string input."""
    if pd.isna(input_str):
        return ""
    return str(input_str).strip()

def get_transaction_summary(transactions_df):
    """Get summary statistics from transactions dataframe."""
    if transactions_df.empty:
        return {
            'total_transactions': 0,
            'total_stock_in': 0,
            'total_stock_out': 0,
            'net_change': 0
        }
    
    stock_in_qty = transactions_df[transactions_df['transaction_type'] == 'Stock In']['quantity'].sum()
    stock_out_qty = transactions_df[transactions_df['transaction_type'] == 'Stock Out']['quantity'].sum()
    
    return {
        'total_transactions': len(transactions_df),
        'total_stock_in': stock_in_qty,
        'total_stock_out': stock_out_qty,
        'net_change': stock_in_qty - stock_out_qty
    }

def filter_transactions_by_date(df, start_date, end_date):
    """Filter transactions by date range."""
    if df.empty:
        return df
    
    df_copy = df.copy()
    df_copy['date'] = pd.to_datetime(df_copy['date'])
    
    return df_copy[
        (df_copy['date'] >= pd.to_datetime(start_date)) &
        (df_copy['date'] <= pd.to_datetime(end_date))
    ]

def get_low_stock_items(stock_df, threshold=10):
    """Get items with stock below threshold."""
    if stock_df.empty:
        return stock_df
    
    return stock_df[stock_df['remaining_qty'] <= threshold]
    
