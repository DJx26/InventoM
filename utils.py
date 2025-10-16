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
    
# ---- Paper sizing utilities ----
def parse_size_string(size_text):
    """Parse a size string like '30x40', '30 x 40', '30*40', '30×40'.

    Returns (width, height) as floats if parseable; otherwise (None, None).
    The function is tolerant of additional text (e.g., 'A4 210x297 80gsm').
    Units are assumed to be consistent across all sizes (no conversion).
    """
    if not isinstance(size_text, str):
        return None, None

    text = size_text.strip().lower()
    # Replace common separators with 'x'
    for sep in ['×', '*', 'x', 'X']:
        text = text.replace(sep, 'x')

    # Find the first pair of numbers around an 'x'
    # Extract all numbers (allow decimals)
    import re
    # Match patterns like 30x40, 210 x 297, possibly within other text
    match = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", text)
    if not match:
        return None, None
    try:
        w = float(match.group(1))
        h = float(match.group(2))
        return w, h
    except ValueError:
        return None, None

def compute_fit_for_sheet(stock_width, stock_height, req_width, req_height):
    """Compute best piece fit of a requested rectangle into a stock sheet.

    Considers both orientations and returns the best of the two by:
    - maximizing pieces per sheet
    - then minimizing waste area when counts tie

    Returns a dict with:
    {
      'best_count', 'best_layout', 'rows', 'cols', 'waste_area', 'utilization'
    }
    or None if no piece can fit even once.
    """
    if min(stock_width, stock_height) <= 0 or min(req_width, req_height) <= 0:
        return None

    import math
    stock_area = stock_width * stock_height
    piece_area = req_width * req_height

    # Orientation A: as-is
    cols_a = int(stock_width // req_width)
    rows_a = int(stock_height // req_height)
    count_a = max(0, cols_a * rows_a)
    waste_a = stock_area - (count_a * piece_area)

    # Orientation B: rotated 90 deg
    cols_b = int(stock_width // req_height)
    rows_b = int(stock_height // req_width)
    count_b = max(0, cols_b * rows_b)
    waste_b = stock_area - (count_b * piece_area)

    candidates = []
    if count_a > 0:
        utilization_a = 0.0 if stock_area <= 0 else (count_a * piece_area) / stock_area
        candidates.append({
            'best_count': count_a,
            'best_layout': 'normal',
            'rows': rows_a,
            'cols': cols_a,
            'waste_area': max(0.0, waste_a),
            'utilization': utilization_a
        })
    if count_b > 0:
        utilization_b = 0.0 if stock_area <= 0 else (count_b * piece_area) / stock_area
        candidates.append({
            'best_count': count_b,
            'best_layout': 'rotated',
            'rows': rows_b,
            'cols': cols_b,
            'waste_area': max(0.0, waste_b),
            'utilization': utilization_b
        })

    if not candidates:
        return None

    # Sort: highest count desc, then lowest waste asc
    candidates.sort(key=lambda c: (-c['best_count'], c['waste_area']))
    return candidates[0]

def evaluate_paper_fit_options(custom_w, custom_h, stock_rows_df):
    """Evaluate fit options of a custom size against available Paper stock rows.

    custom_w, custom_h: floats for requested piece size (assumed same units)
    stock_rows_df: DataFrame from get_current_stock('Paper') with columns
                   'subcategory' and 'remaining_qty' at minimum.

    Returns a list of dicts per stock row with parsed sizes and best fit info.
    """
    results = []
    if stock_rows_df is None or stock_rows_df.empty:
        return results

    for _, row in stock_rows_df.iterrows():
        sub = str(row.get('subcategory', ''))
        qty = float(row.get('remaining_qty', 0)) if 'remaining_qty' in row else 0.0
        sw, sh = parse_size_string(sub)
        if sw is None or sh is None:
            continue
        fit = compute_fit_for_sheet(sw, sh, custom_w, custom_h)
        if fit is None:
            continue
        result = {
            'subcategory': sub,
            'stock_width': sw,
            'stock_height': sh,
            'remaining_qty': qty,
            'pieces_per_sheet': fit['best_count'],
            'rows': fit['rows'],
            'cols': fit['cols'],
            'orientation': fit['best_layout'],
            'waste_area': fit['waste_area'],
            'utilization': fit['utilization'],
            'total_pieces_possible': fit['best_count'] * qty
        }
        results.append(result)

    # Sort by highest pieces per sheet desc, then lowest waste area asc, then highest utilization
    results.sort(key=lambda r: (-r['pieces_per_sheet'], r['waste_area'], -r['utilization']))
    return results
