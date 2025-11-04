import streamlit as st
import pandas as pd
from datetime import datetime, date
import os
from io import BytesIO
from data_manager import DataManager
from utils import format_date, validate_quantity
try:
    from utils import parse_size_string, evaluate_paper_fit_options
except Exception:
    # Fallback definitions to avoid import errors on some deployments
    import re
    def parse_size_string(size_text):
        if not isinstance(size_text, str):
            return None, None
        text = size_text.strip().lower()
        for sep in ['×', '*', 'x', 'X']:
            text = text.replace(sep, 'x')
        match = re.search(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", text)
        if not match:
            return None, None
        try:
            return float(match.group(1)), float(match.group(2))
        except ValueError:
            return None, None

    def _compute_fit_for_sheet(stock_width, stock_height, req_width, req_height):
        if min(stock_width, stock_height) <= 0 or min(req_width, req_height) <= 0:
            return None
        stock_area = stock_width * stock_height
        piece_area = req_width * req_height
        cols_a = int(stock_width // req_width)
        rows_a = int(stock_height // req_height)
        count_a = max(0, cols_a * rows_a)
        waste_a = stock_area - (count_a * piece_area)
        cols_b = int(stock_width // req_height)
        rows_b = int(stock_height // req_width)
        count_b = max(0, cols_b * rows_b)
        waste_b = stock_area - (count_b * piece_area)
        candidates = []
        if count_a > 0:
            utilization_a = 0.0 if stock_area <= 0 else (count_a * piece_area) / stock_area
            candidates.append({'best_count': count_a,'best_layout': 'normal','rows': rows_a,'cols': cols_a,'waste_area': max(0.0, waste_a),'utilization': utilization_a})
        if count_b > 0:
            utilization_b = 0.0 if stock_area <= 0 else (count_b * piece_area) / stock_area
            candidates.append({'best_count': count_b,'best_layout': 'rotated','rows': rows_b,'cols': cols_b,'waste_area': max(0.0, waste_b),'utilization': utilization_b})
        if not candidates:
            return None
        candidates.sort(key=lambda c: (-c['best_count'], c['waste_area']))
        return candidates[0]

    def evaluate_paper_fit_options(custom_w, custom_h, stock_rows_df):
        results = []
        if stock_rows_df is None or stock_rows_df.empty:
            return results
        for _, row in stock_rows_df.iterrows():
            sub = str(row.get('subcategory', ''))
            qty = float(row.get('remaining_qty', 0)) if 'remaining_qty' in row else 0.0
            sw, sh = parse_size_string(sub)
            if sw is None or sh is None:
                continue
            fit = _compute_fit_for_sheet(sw, sh, custom_w, custom_h)
            if fit is None:
                continue
            results.append({
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
            })
        results.sort(key=lambda r: (-r['pieces_per_sheet'], r['waste_area'], -r['utilization']))
        return results
from auth import AuthManager

st.set_page_config(
    page_title="JENENDRA PRESS INVENTORY",
    page_icon="📦",
    layout="wide"
)
# Initialize session state
if 'data_manager' not in st.session_state or getattr(st.session_state.data_manager, 'api_version', 0) < getattr(DataManager, 'API_VERSION', 0):
    st.session_state.data_manager = DataManager()

if 'auth_manager' not in st.session_state:
    st.session_state.auth_manager = AuthManager()

if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

def check_sheets_status():
    """Display Google Sheets configuration status."""
    import os
    from sheets_manager import SheetsManager
    
    st.subheader("Google Sheets Connection Status")
    
    # Check credentials file
    base_dir = os.path.dirname(os.path.abspath(__file__))
    credentials_path = os.path.join(base_dir, "data", "credentials.json")
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if os.path.exists(credentials_path):
            st.success("✓")
        else:
            st.error("✗")
    with col2:
        if os.path.exists(credentials_path):
            st.write("**Credentials file found**")
        else:
            st.write("**Credentials file missing**")
            st.caption(f"Expected at: {credentials_path}")
    
    # Check spreadsheet ID (try all sources)
    spreadsheet_id = None
    source = "Not found"
    
    # Try environment variable
    spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
    if spreadsheet_id:
        source = "Environment Variable"
    else:
        # Try Streamlit secrets
        try:
            if hasattr(st, 'secrets') and 'GOOGLE_SHEETS_ID' in st.secrets:
                spreadsheet_id = st.secrets['GOOGLE_SHEETS_ID']
                source = "Streamlit Secrets"
        except:
            pass
    
    # Try config file
    if not spreadsheet_id:
        config_file = os.path.join(base_dir, "data", "config.txt")
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith('GOOGLE_SHEETS_ID='):
                            spreadsheet_id = line.split('=', 1)[1].strip().strip('"').strip("'")
                            source = "Config File"
                            break
            except:
                pass
    
    col1, col2 = st.columns([1, 3])
    with col1:
        if spreadsheet_id:
            st.success("✓")
        else:
            st.warning("⚠")
    with col2:
        if spreadsheet_id:
            st.write(f"**Spreadsheet ID configured**")
            st.caption(f"ID: {spreadsheet_id[:20]}... (from {source})")
        else:
            st.write("**Spreadsheet ID not set**")
            st.caption("Set via: Environment Variable, Streamlit Secrets, or data/config.txt")
    
    # Secrets presence diagnostics
    secrets_present = False
    secrets_mode = None
    try:
        import streamlit as _st
        if hasattr(_st, 'secrets'):
            if 'gcp_service_account' in _st.secrets:
                secrets_present = True
                secrets_mode = 'gcp_service_account'
            elif 'GOOGLE_SERVICE_ACCOUNT_JSON' in _st.secrets:
                secrets_present = True
                secrets_mode = 'GOOGLE_SERVICE_ACCOUNT_JSON'
    except Exception:
        pass

    if secrets_present:
        st.success(f"Secrets detected: {secrets_mode}")
    else:
        st.warning("No Streamlit Secrets detected for Google credentials. Add either [gcp_service_account] or GOOGLE_SERVICE_ACCOUNT_JSON.")


     # Package diagnostics (to see if pip installed gspread/google-auth)
    with st.expander("📦 Package diagnostics", expanded=False):
        import sys
        st.caption(f"Python: {sys.version}")
        missing = []
        def _pkg(name):
            try:
                mod = __import__(name)
                ver = getattr(mod, "__version__", "unknown")
                st.success(f"{name} installed (version {ver})")
            except Exception as e:
                st.error(f"{name} NOT installed: {e}")
                 missing.append(name)
        _pkg("gspread")
        _pkg("google.oauth2")
       try:
            __import__("googleapiclient")
            st.success("googleapiclient installed")
        except Exception as e:
            st.info(f"googleapiclient optional: {e}")

        # One-click installer if missing
        if missing:
            st.warning("Required packages missing. Click to install now (may take ~1 min).")
            if st.button("Install required packages", use_container_width=True):
                try:
                    import subprocess
                    pkgs = [
                        "gspread>=6.0.0",
                        "google-auth>=2.23.0",
                        "google-auth-oauthlib>=1.1.0",
                        "google-auth-httplib2>=0.1.1",
                    ]
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade"] + pkgs)
                    st.success("Packages installed. Rerunning app…")
                    st.rerun()
                except Exception as e:
                    st.error(f"Auto-install failed: {e}")

        
    # Allow setting Spreadsheet ID quickly via config file
    st.markdown("---")
    st.write("Set or update Spreadsheet ID")
    input_id = st.text_input(
        "Spreadsheet ID",
        value=spreadsheet_id or "",
        placeholder="Paste the long ID from Google Sheets URL",
    )
    if st.button("Save Spreadsheet ID", use_container_width=True):
        try:
            os.makedirs(os.path.join(base_dir, "data"), exist_ok=True)
            with open(os.path.join(base_dir, "data", "config.txt"), 'w') as f:
                f.write(f"GOOGLE_SHEETS_ID={input_id.strip()}\n")
            st.success("Spreadsheet ID saved to data/config.txt")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save Spreadsheet ID: {e}")

    # Show detected service account email (helps sharing)
    try:
        from sheets_manager import SheetsManager
        _sm = SheetsManager()
        email = _sm.get_service_account_email()
        src = _sm.get_credentials_source()
        if email:
            st.caption(f"Service account email (share your sheet with this): {email}")
        if src:
            pretty = {
                'secrets_table': 'Streamlit Secrets [gcp_service_account]',
                'secrets_json': 'Streamlit Secrets GOOGLE_SERVICE_ACCOUNT_JSON',
                'file': 'data/credentials.json'
            }.get(src, src)
            st.caption(f"Credentials source in use: {pretty}")
    except Exception:
        pass

    # Test connection
    if st.button("🔌 Test Connection", use_container_width=True):
        with st.spinner("Testing Google Sheets connection..."):
            try:
                sheets_manager = SheetsManager()
                if sheets_manager.is_configured():
                    st.success("✅ **Connection successful!**")
                    st.write(f"**Spreadsheet:** {sheets_manager.spreadsheet.title}")
                    
                    # List existing worksheets
                    try:
                        worksheets = sheets_manager.spreadsheet.worksheets()
                        worksheet_names = [ws.title for ws in worksheets]
                        st.write(f"**Worksheets found:** {len(worksheet_names)}")
                        if worksheet_names:
                            st.write(", ".join(worksheet_names))
                        else:
                            st.info("No worksheets found. They will be created automatically when you add data.")
                    except Exception as e:
                        st.warning(f"Could not list worksheets: {str(e)}")
                    
                    # Try to create/get worksheets
                    st.write("**Creating/Verifying worksheets...**")
                    test_results = []
                    for sheet_name, headers in [
                        ("Transactions", ['id', 'category', 'subcategory', 'transaction_type', 'quantity', 'date', 'supplier', 'notes', 'created_at']),
                        ("Current Stock", ['category', 'subcategory', 'remaining_qty', 'last_updated', 'supplier']),
                        ("Templates", ['id', 'template_name', 'category', 'subcategory', 'supplier', 'created_at'])
                    ]:
                        try:
                            worksheet = sheets_manager.get_or_create_worksheet(sheet_name, headers)
                            if worksheet:
                                test_results.append((sheet_name, True, "✓ Created/Found"))
                            else:
                                test_results.append((sheet_name, False, "✗ Failed"))
                        except Exception as e:
                            test_results.append((sheet_name, False, f"✗ Error: {str(e)}"))
                    
                    # Display results
                    for name, success, msg in test_results:
                        if success:
                            st.success(f"**{name}:** {msg}")
                        else:
                            st.error(f"**{name}:** {msg}")
                    
                else:
                    st.error("❌ **Connection failed**")
                    # Provide precise guidance based on what we detect
                    if secrets_present:
                        st.warning("Streamlit Secrets detected, but authorization failed. Verify JSON is valid, APIs enabled, and sheet is shared with the service account email shown above.")
                    else:
                        st.error("Credentials not available from Secrets. Add credentials to Streamlit Secrets (recommended).")
                    if not spreadsheet_id:
                        st.error("Spreadsheet ID not configured!")
                    # Show file path only as a fallback option
                    if not os.path.exists(credentials_path):
                        st.caption(f"No local credentials file at: {credentials_path}")
            except Exception as e:
                st.error(f"❌ **Error:** {str(e)}")
                import traceback
                with st.expander("Show detailed error"):
                    st.code(traceback.format_exc())

def main():

    # Check authentication
    if not st.session_state.authenticated:
        st.session_state.auth_manager.show_login_page()
        return

    # Sidebar with logout and settings
    with st.sidebar:
        st.title("⚙️ Settings")

        if st.button("🚪 Logout", use_container_width=True):
            st.session_state.auth_manager.logout()

        st.markdown("---")
        
        # Google Sheets Status Checker
        with st.expander("🔍 Google Sheets Status", expanded=False):
            check_sheets_status()
        
        st.markdown("---")

        # Global search
        st.subheader("🔍 Global Search")
        search_query = st.text_input("Search all transactions", placeholder="Search by product, supplier, notes...")

        if search_query:
            all_transactions = st.session_state.data_manager.get_all_transactions()

            if not all_transactions.empty:
                # Search across multiple fields
                search_lower = search_query.lower()
                mask = (
                    all_transactions['category'].astype(str).str.lower().str.contains(search_lower, na=False) |
                    all_transactions['subcategory'].astype(str).str.lower().str.contains(search_lower, na=False) |
                    all_transactions['notes'].astype(str).str.lower().str.contains(search_lower, na=False) |
                    all_transactions['supplier'].astype(str).str.lower().str.contains(search_lower, na=False) |
                    all_transactions['transaction_type'].astype(str).str.lower().str.contains(search_lower, na=False)
                )
                results = all_transactions[mask]

                if not results.empty:
                    st.success(f"Found {len(results)} results")

                    # Display results in expandable section
                    with st.expander(f"View {len(results)} Results", expanded=True):
                        display_results = results.copy()
                        display_results['quantity'] = display_results['quantity'].apply(lambda x: f"{x:,.0f}")
                        try:
                            display_results['date'] = pd.to_datetime(display_results['date'], errors='coerce').dt.strftime('%Y-%m-%d')
                            display_results = display_results.sort_values('date', ascending=False)
                        except (KeyError, AttributeError):
                            pass

                        st.dataframe(
                            display_results[['date', 'category', 'subcategory', 'transaction_type', 'quantity', 'supplier', 'notes']],
                            use_container_width=True,
                            hide_index=True
                        )
                else:
                    st.info("No results found")
            else:
                st.info("No transactions to search")

        st.markdown("---")

        with st.expander("🔑 Change Password"):
            st.session_state.auth_manager.show_change_password_page()

    st.title("📦 Stock Management System")
    st.markdown("---")

    # Quick access: Google Sheets Status on main page
    with st.expander("🔍 Google Sheets Status", expanded=False):
        try:
            check_sheets_status()
        except Exception as _e:
            st.info("Google Sheets diagnostics unavailable.")

    # Create tabs for different sections
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Dashboard", "📄 Paper", "🖋️ Inks", "🧪 Chemicals", "🎞️ Poly Films", "📈 Reports"
    ])

    with tab1:
        show_dashboard()

    with tab2:
        show_category_page("Paper", include_supplier=True)

    with tab3:
        show_category_page("Inks")

    with tab4:
        show_category_page("Chemicals")

    with tab5:
        show_category_page("Poly Films")

    with tab6:
        show_reports()

def show_dashboard():
    st.header("Stock Overview Dashboard")

    # Get current stock levels for all categories
    categories = ["Paper", "Inks", "Chemicals", "Poly Films"]

    # Create columns for dashboard metrics
    col1, col2, col3, col4 = st.columns(4)

    for i, category in enumerate(categories):
        current_stock = st.session_state.data_manager.get_current_stock(category)
        total_items = len(current_stock)
        total_qty = current_stock['remaining_qty'].sum() if not current_stock.empty else 0

        with [col1, col2, col3, col4][i]:
            st.metric(
                label=f"{category} Items",
                value=total_items,
                help=f"Total quantity: {total_qty:,.0f}"
            )

    st.markdown("---")

    # Show recent transactions
    st.subheader("Recent Transactions (Last 10)")
    recent_transactions = st.session_state.data_manager.get_recent_transactions(10)

    if not recent_transactions.empty:
        # Format the dataframe for display
        display_df = recent_transactions.copy()
        display_df['quantity'] = display_df['quantity'].apply(lambda x: f"{x:,.0f}")
        if 'date' in display_df.columns:
            display_df['date'] = pd.to_datetime(display_df['date'], errors='coerce').dt.strftime('%Y-%m-%d')

        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No transactions recorded yet.")

    # Show low stock alerts
    st.subheader("Stock Alerts")
    low_stock_threshold = st.number_input("Low Stock Alert Threshold", min_value=0, value=10, step=1)

    for category in categories:
        current_stock = st.session_state.data_manager.get_current_stock(category)
        if not current_stock.empty:
            low_stock = current_stock[current_stock['remaining_qty'] <= low_stock_threshold]
            if not low_stock.empty:
                st.warning(f"⚠️ Low stock in {category}: {len(low_stock)} items below threshold")
                with st.expander(f"View {category} low stock items"):
                    st.dataframe(low_stock, use_container_width=True, hide_index=True)

def show_category_page(category, include_supplier=False):
    st.header(f"{category} Stock Management")

    # Create two columns: one for adding stock, one for current stock
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Add Stock Transaction")

        # Template quick load section
        templates = st.session_state.data_manager.get_templates(category)

        if not templates.empty:
            st.markdown("**⚡ Quick Load Template**")
            template_names = templates['template_name'].tolist()
            selected_template = st.selectbox(
                "Load from template",
                options=["-- None --"] + template_names,
                key=f"template_select_{category}"
            )

            if selected_template != "-- None --":
                template_data = st.session_state.data_manager.get_template_by_name(category, selected_template)
                if template_data:
                    # Store template data in session state for autofill
                    st.session_state[f'template_subcategory_{category}'] = template_data['subcategory']
                    st.session_state[f'template_supplier_{category}'] = template_data.get('supplier', '')
                    st.info(f"Loaded template: {selected_template}")
            else:
                # Clear template data
                if f'template_subcategory_{category}' in st.session_state:
                    del st.session_state[f'template_subcategory_{category}']
                if f'template_supplier_{category}' in st.session_state:
                    del st.session_state[f'template_supplier_{category}']

            st.markdown("---")

        # Get existing subcategories for this category
        existing_subcategories = st.session_state.data_manager.get_subcategories(category)

        # Check if template data exists
        default_subcategory = st.session_state.get(f'template_subcategory_{category}', "")

        # Determine if template subcategory is new or existing
        template_is_new = default_subcategory and default_subcategory not in existing_subcategories

        # Subcategory input (dropdown + new option)
        subcategory_options = ["-- Select Existing --"] + existing_subcategories + ["+ Add New Subcategory"]

        # Set default selection based on template
        if default_subcategory and default_subcategory in existing_subcategories:
            default_index = subcategory_options.index(default_subcategory)
        elif template_is_new:
            # Auto-select "Add New" when template has new subcategory
            default_index = subcategory_options.index("+ Add New Subcategory")
        else:
            default_index = 0

        selected_option = st.selectbox("Subcategory", subcategory_options, index=default_index, key=f"subcategory_select_{category}")

        if selected_option == "+ Add New Subcategory":
            # Prefill with template value if available
            subcategory = st.text_input(
                "New Subcategory Name", 
                value=default_subcategory if template_is_new else "",
                placeholder="e.g., A4 80gsm, Blue Ink, etc.",
                key=f"new_subcategory_{category}"
            )
        elif selected_option == "-- Select Existing --":
            subcategory = ""
        else:
            subcategory = selected_option

        # Transaction details
        transaction_type = st.selectbox("Transaction Type", ["Stock In", "Stock Out"], key=f"transaction_type_{category}")
        quantity = st.number_input("Quantity", min_value=0.0, step=1.0, format="%.0f", key=f"quantity_{category}")
        transaction_date = st.date_input("Date", value=date.today(), key=f"date_{category}")

        # Supplier name (only for Paper)
        supplier = ""
        if include_supplier:
            default_supplier = st.session_state.get(f'template_supplier_{category}', "")
            supplier = st.text_input("Supplier Name", value=default_supplier, placeholder="Enter supplier name", key=f"supplier_{category}")

        notes = st.text_area("Notes (Optional)", placeholder="Additional notes about this transaction", key=f"notes_{category}")

        # Quick best-fit helper for Paper while adding transactions (uses current stock)
        if category == "Paper":
            with st.expander("✂️ Find best fit now (from current stock)", expanded=False):
                helper_col1, helper_col2 = st.columns(2)
                with helper_col1:
                    # Try to parse a size from the subcategory text if present; user can override
                    default_size_text = subcategory if subcategory else ""
                    query_size_text = st.text_input(
                        "Required size (e.g., 15x20)",
                        value=default_size_text,
                        placeholder="width x height",
                        key=f"instant_fit_size_{category}"
                    )
                with helper_col2:
                    min_pieces_now = st.number_input(
                        "Min pieces/sheet (optional)",
                        min_value=0,
                        value=0,
                        step=1,
                        key=f"instant_fit_min_{category}"
                    )

                if query_size_text:
                    rw_now, rh_now = parse_size_string(query_size_text)
                    if rw_now is None or rh_now is None or rw_now <= 0 or rh_now <= 0:
                        st.error("Could not parse size. Use format like '15x20'.")
                    else:
                        paper_stock_now = st.session_state.data_manager.get_current_stock("Paper")
                        results_now = evaluate_paper_fit_options(rw_now, rh_now, paper_stock_now)
                        if min_pieces_now > 0:
                            results_now = [r for r in results_now if r['pieces_per_sheet'] >= min_pieces_now]

                        if results_now:
                            try:
                                df_now = pd.DataFrame([
                                    {
                                        "Stock Size": f"{int(r['stock_width'])}x{int(r['stock_height'])}",
                                        "Subcategory": r['subcategory'],
                                        "Qty": r['remaining_qty'],
                                        "Pieces/Sheet": r['pieces_per_sheet'],
                                        "Layout": r['orientation'],
                                        "RowsxCols": f"{r['rows']}x{r['cols']}",
                                        "Utilization": f"{r['utilization']*100:.1f}%",
                                        "Waste Area": f"{r['waste_area']:.0f}",
                                        "Total Pieces": int(r['total_pieces_possible'])
                                    }
                                    for r in results_now
                                ])
                                st.dataframe(df_now, use_container_width=True, hide_index=True)
                            except Exception:
                                st.json([
                                    {
                                        "Stock Size": f"{int(r['stock_width'])}x{int(r['stock_height'])}",
                                        "Subcategory": r['subcategory'],
                                        "Qty": r['remaining_qty'],
                                        "Pieces/Sheet": r['pieces_per_sheet'],
                                        "Layout": r['orientation'],
                                        "RowsxCols": f"{r['rows']}x{r['cols']}",
                                        "Utilization": f"{r['utilization']*100:.1f}%",
                                        "Waste Area": f"{r['waste_area']:.0f}",
                                        "Total Pieces": int(r['total_pieces_possible'])
                                    }
                                    for r in results_now
                                ])
                        else:
                            st.info("No fitting options found for this size in current Paper stock.")

        # (Inline best-fit helper removed to avoid indentation issues in some deployments)

        # Submit button
        if st.button("Add Transaction", type="primary", key=f"add_transaction_{category}"):
            if subcategory and quantity > 0:
                success = st.session_state.data_manager.add_transaction(
                    category=category,
                    subcategory=subcategory,
                    transaction_type=transaction_type,
                    quantity=quantity,
                    transaction_date=transaction_date,
                    supplier=supplier,
                    notes=notes
                )

                if success:
                    st.success("Transaction added successfully!")
                    st.rerun()
                else:
                    st.error("Failed to add transaction. Please try again.")
            else:
                st.error("Please fill in all required fields.")

        st.markdown("---")
        with st.expander("Debug: Latest transactions for this category"):
            _hist = st.session_state.data_manager.get_transaction_history(category, limit=5)
            st.dataframe(_hist, use_container_width=True, hide_index=True)
        # Excel upload section
        st.subheader("📊 Bulk Upload")
        uploaded_file = st.file_uploader(
            "Upload Excel file (.xlsx format recommended)",
            type=['xlsx'],
            help="Upload an Excel file (.xlsx format) with columns: subcategory, transaction_type, quantity, date, supplier (for Paper), notes",
            key=f"uploader_{category}"
        )

        if uploaded_file is not None:
            try:
                # Read Excel file (using openpyxl engine for .xlsx files)
                df = pd.read_excel(uploaded_file, engine='openpyxl')
                
                st.write("**Preview of uploaded data:**")
                st.dataframe(df.head(), use_container_width=True)
                
                # Show detected columns
                st.info(f"**Detected columns:** {', '.join(df.columns.tolist())}")
                
                # Show expected vs found columns
                required_cols = ['subcategory', 'transaction_type', 'quantity', 'date']
                if include_supplier:
                    required_cols.append('supplier')
                
                detected_lower = [col.lower().strip() for col in df.columns]
                missing = [col for col in required_cols if col.lower() not in detected_lower]
                
                if missing:
                    st.warning(
                        f"⚠️ **Expected columns:** {', '.join(required_cols)}\n\n"
                        f"**Found columns:** {', '.join(df.columns.tolist())}\n\n"
                        f"**Missing:** {', '.join(missing)}\n\n"
                        "Please ensure your Excel file has the correct column names (case-insensitive)."
                    )

                if st.button("Process Upload", key=f"process_upload_{category}"):
                    success_count = st.session_state.data_manager.bulk_upload(category, df, include_supplier)
                    if success_count > 0:
                        st.success(f"Successfully uploaded {success_count} transactions!")
                        st.rerun()
                    else:
                        st.error("No valid transactions found in the uploaded file.")

            except ImportError as e:
                if 'xlrd' in str(e).lower():
                    st.error(
                        "⚠️ Missing dependency: xlrd is required for .xls files. "
                        "Please install it with: `pip install xlrd>=2.0.1`\n\n"
                        "**Alternative:** Convert your file to .xlsx format, which is supported by default."
                    )
                else:
                    st.error(f"Error reading Excel file: {str(e)}")
            except Exception as e:
                error_msg = str(e)
                if 'xlrd' in error_msg.lower():
                    st.error(
                        "⚠️ Missing dependency: xlrd is required for .xls files. "
                        "Please install it with: `pip install xlrd>=2.0.1`\n\n"
                        "**Alternative:** Convert your file to .xlsx format, which is supported by default."
                    )
                else:
                    st.error(f"Error reading Excel file: {error_msg}")

        # Show expected format
        with st.expander("📋 Expected Excel Format"):
            sample_columns = ["subcategory", "transaction_type", "quantity", "date"]
            if include_supplier:
                sample_columns.append("supplier")
            sample_columns.append("notes")

            sample_data = {
                "subcategory": ["A4 80gsm", "A3 70gsm"],
                "transaction_type": ["Stock In", "Stock Out"],
                "quantity": [1000, 50],
                "date": ["2024-01-15", "2024-01-16"]
            }

            if include_supplier:
                sample_data["supplier"] = ["Supplier A", "Supplier B"]

            sample_data["notes"] = ["Initial stock", "Used for printing"]

            try:
                st.dataframe(pd.DataFrame(sample_data), use_container_width=True, hide_index=True)
            except Exception:
                # Fallback display if pandas import is unavailable at runtime
                st.json(sample_data)

        st.markdown("---")

        # Template management section
        st.subheader("💾 Manage Templates")

        with st.expander("Save Current Entry as Template"):
            template_name = st.text_input("Template Name", placeholder="e.g., 'A4 Paper Default'", key=f"template_name_{category}")
            template_subcategory = st.text_input("Subcategory for Template", value=subcategory if subcategory else "", placeholder="Product name/size", key=f"template_subcategory_{category}")
            template_supplier = ""
            if include_supplier:
                template_supplier = st.text_input("Supplier for Template", value=supplier, placeholder="Supplier name", key=f"template_supplier_input_{category}")

            if st.button("Save Template", key=f"save_template_{category}"):
                if template_name and template_subcategory:
                    success = st.session_state.data_manager.save_template(
                        template_name=template_name,
                        category=category,
                        subcategory=template_subcategory,
                        supplier=template_supplier
                    )
                    if success:
                        st.success(f"Template '{template_name}' saved successfully!")
                        st.rerun()
                else:
                    st.error("Please provide template name and subcategory.")

        # Show existing templates
        if not templates.empty:
            with st.expander(f"View {category} Templates ({len(templates)})"):
                for idx, row in templates.iterrows():
                    col_a, col_b = st.columns([3, 1])
                    with col_a:
                        st.text(f"📌 {row['template_name']}: {row['subcategory']}")
                    with col_b:
                        if st.button("Delete", key=f"delete_template_{row['id']}"):
                            if st.session_state.data_manager.delete_template(category, row['template_name']):
                                st.success("Template deleted!")
                                st.rerun()
    st.button("Force refresh from disk", on_click=lambda: st.rerun(), key=f"refresh_{category}")
    with col2:
        st.subheader(f"Current {category} Stock")

        # Get and display current stock
        current_stock = st.session_state.data_manager.get_current_stock(category)

        if not current_stock.empty:
            # Format quantities for display
            with st.expander("Debug: Raw stock rows for this category"):
                st.dataframe(current_stock, use_container_width=True, hide_index=True)
            display_stock = current_stock.copy()
            display_stock['remaining_qty'] = display_stock['remaining_qty'].apply(lambda x: f"{x:,.0f}")

            column_config = {
                "subcategory": "Subcategory",
                "remaining_qty": "Remaining Quantity",
            }
            if include_supplier:
                column_config["supplier"] = "Latest Supplier"
            with st.expander("Delete Subcategory", expanded=False):
                existing_subcategories = st.session_state.data_manager.get_subcategories(category)
                del_sub = st.selectbox(
                    "Select subcategory to delete",
                    options=["-- Select --"] + existing_subcategories,
                    key=f"delete_sub_{category}"
                )
                delete_txs = st.checkbox(
                    "Also delete all transactions for this subcategory",
                    key=f"delete_txs_{category}"
                )
                if st.button("Delete Subcategory", type="secondary", key=f"delete_sub_btn_{category}"):
                    if del_sub and del_sub != "-- Select --":
                        ok, removed_stock, removed_txs = st.session_state.data_manager.delete_subcategory(
                            category=category,
                            subcategory=del_sub,
                            delete_transactions=delete_txs
                        )
                        if ok:
                            st.success(
                                f"Deleted '{del_sub}' from {category}. "
                                f"Removed stock rows: {removed_stock}" +
                                (f", transactions: {removed_txs}" if delete_txs else "")
                            )
                            st.rerun()
                    else:
                        st.error("Please select a subcategory to delete.")
            st.dataframe(
                display_stock,
                use_container_width=True,
                hide_index=True,
                column_config=column_config
            )
            # Paper Cut Optimizer
            if category == "Paper":
                with st.expander("✂️ Paper Cut Optimizer", expanded=False):
                    c1, c2 = st.columns(2)
                    with c1:
                        custom_size_text = st.text_input(
                            "Custom required size (e.g., 15x20)",
                            placeholder="width x height"
                        )
                    with c2:
                        min_pieces = st.number_input(
                            "Minimum pieces per sheet (optional)",
                            min_value=0,
                            value=0,
                            step=1
                        )

                    if custom_size_text:
                        rw, rh = parse_size_string(custom_size_text)
                        if rw is None or rh is None or rw <= 0 or rh <= 0:
                            st.error("Could not parse custom size. Use format like '15x20'.")
                        else:
                            paper_stock = st.session_state.data_manager.get_current_stock("Paper")
                            results = evaluate_paper_fit_options(rw, rh, paper_stock)
                            if min_pieces > 0:
                                results = [r for r in results if r['pieces_per_sheet'] >= min_pieces]

                            if results:
                                # Show a compact table
                                df = pd.DataFrame([
                                    {
                                        "Stock Size": f"{int(r['stock_width'])}x{int(r['stock_height'])}",
                                        "Subcategory": r['subcategory'],
                                        "Qty": r['remaining_qty'],
                                        "Pieces/Sheet": r['pieces_per_sheet'],
                                        "Layout": r['orientation'],
                                        "RowsxCols": f"{r['rows']}x{r['cols']}",
                                        "Utilization": f"{r['utilization']*100:.1f}%",
                                        "Waste Area": f"{r['waste_area']:.0f}",
                                        "Total Pieces": int(r['total_pieces_possible'])
                                    }
                                    for r in results
                                ])
                                st.dataframe(df, use_container_width=True, hide_index=True)
                            else:
                                st.info("No fitting options found for this size in current Paper stock.")
            with st.expander("Quick Delete Subcategory (exact match)", expanded=False):
                if not current_stock.empty:
                    for idx, row in current_stock.iterrows():
                        c1, c2, c3 = st.columns([3, 2, 1])
                        with c1:
                            st.write(f"{row['subcategory']}")
                        with c2:
                            st.write(f"Qty: {row['remaining_qty']}")
                        with c3:
                            if st.button("Delete", key=f"row_del_{category}_{row['subcategory']}"):
                                ok, removed_stock, removed_txs = st.session_state.data_manager.delete_subcategory(
                                    category=category,
                                    subcategory=str(row['subcategory']),
                                    delete_transactions=True
                                )
                                if ok:
                                    st.success(f"Deleted '{row['subcategory']}' from {category} (stock rows removed: {removed_stock}, transactions: {removed_txs})")
                                    st.rerun()
            
            # Show transaction history for selected subcategory
            if len(current_stock) > 0:
                st.markdown("---")
                st.subheader("Transaction History")

                selected_subcategory = st.selectbox(
                    "Select subcategory to view history",
                    options=["All"] + list(current_stock['subcategory'].unique())
                )

                history = st.session_state.data_manager.get_transaction_history(
                    category, 
                    subcategory=None if selected_subcategory == "All" else selected_subcategory
                )

                if not history.empty:
                    # Format history for display
                    display_history = history.copy()
                    display_history['quantity'] = display_history['quantity'].apply(lambda x: f"{x:,.0f}")
                    if 'date' in display_history.columns:
                        display_history['date'] = pd.to_datetime(display_history['date'], errors='coerce').dt.strftime('%Y-%m-%d')

                    st.dataframe(
                        display_history,
                        use_container_width=True,
                        hide_index=True
                    )
                else:
                    st.info(f"No transaction history found for {selected_subcategory}.")
        else:
            st.info(f"No {category.lower()} stock recorded yet.")

def show_reports():
    st.header("📈 Reports & Analytics")

    # Filters section
    st.subheader("Filters")

    # Date range filter
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("From Date", value=date.today().replace(day=1))
    with col2:
        end_date = st.date_input("To Date", value=date.today())

    # Category and transaction type filters
    col1, col2, col3 = st.columns(3)
    with col1:
        categories = ["All", "Paper", "Inks", "Chemicals", "Poly Films"]
        selected_category = st.selectbox("Category", categories)

    with col2:
        transaction_types = ["All", "Stock In", "Stock Out"]
        selected_transaction_type = st.selectbox("Transaction Type", transaction_types)

    with col3:
        # Get all subcategories for search
        all_transactions = st.session_state.data_manager.get_all_transactions()
        if not all_transactions.empty:
            all_subcategories = ["All"] + sorted(all_transactions['subcategory'].unique().tolist())
        else:
            all_subcategories = ["All"]
        selected_subcategory = st.selectbox("Subcategory", all_subcategories)

    # Text search
    search_text = st.text_input("🔍 Search in notes, supplier, or subcategory", placeholder="Enter search term...")

    if st.button("Generate Report", type="primary"):
        # Get filtered transactions
        all_transactions = st.session_state.data_manager.get_all_transactions()

        if not all_transactions.empty:
            # Filter by date range
            all_transactions['date'] = pd.to_datetime(all_transactions['date'], errors='coerce')
            filtered_df = all_transactions[
                (all_transactions['date'] >= pd.to_datetime(start_date)) &
                (all_transactions['date'] <= pd.to_datetime(end_date))
            ]

            # Filter by category
            if selected_category != "All":
                filtered_df = filtered_df[filtered_df['category'] == selected_category]

            # Filter by transaction type
            if selected_transaction_type != "All":
                filtered_df = filtered_df[filtered_df['transaction_type'] == selected_transaction_type]

            # Filter by subcategory
            if selected_subcategory != "All":
                filtered_df = filtered_df[filtered_df['subcategory'] == selected_subcategory]

            # Text search filter
            if search_text:
                search_lower = search_text.lower()
                mask = (
                    filtered_df['subcategory'].astype(str).str.lower().str.contains(search_lower, na=False) |
                    filtered_df['notes'].astype(str).str.lower().str.contains(search_lower, na=False) |
                    filtered_df['supplier'].astype(str).str.lower().str.contains(search_lower, na=False)
                )
                filtered_df = filtered_df[mask]

            if not filtered_df.empty:
                st.subheader(f"Transactions Report ({start_date} to {end_date})")

                # Summary metrics
                col1, col2, col3, col4 = st.columns(4)

                with col1:
                    total_transactions = len(filtered_df)
                    st.metric("Total Transactions", total_transactions)

                with col2:
                    stock_in_qty = filtered_df[filtered_df['transaction_type'] == 'Stock In']['quantity'].sum()
                    st.metric("Total Stock In", f"{stock_in_qty:,.0f}")

                with col3:
                    stock_out_qty = filtered_df[filtered_df['transaction_type'] == 'Stock Out']['quantity'].sum()
                    st.metric("Total Stock Out", f"{stock_out_qty:,.0f}")

                with col4:
                    net_change = stock_in_qty - stock_out_qty
                    st.metric("Net Change", f"{net_change:,.0f}")

                st.markdown("---")

                # Visual charts
                st.subheader("📊 Visual Analytics")

                # Create charts in columns
                chart_col1, chart_col2 = st.columns(2)

                with chart_col1:
                    st.markdown("**Stock Movement Over Time**")
                    # Prepare data for time series chart
                    time_series_data = filtered_df.copy()
                    time_series_data['date'] = pd.to_datetime(time_series_data['date'], errors='coerce')
                    time_series_data = time_series_data.sort_values('date')

                    # Group by date and transaction type
                    daily_summary = time_series_data.groupby([time_series_data['date'].dt.date, 'transaction_type'])['quantity'].sum().reset_index()
                    daily_summary.columns = ['Date', 'Type', 'Quantity']

                    # Pivot for chart
                    pivot_data = daily_summary.pivot(index='Date', columns='Type', values='Quantity').fillna(0)

                    if not pivot_data.empty:
                        st.line_chart(pivot_data)
                    else:
                        st.info("No data available for chart")

                with chart_col2:
                    st.markdown("**Transactions by Category**")
                    category_summary = filtered_df.groupby('category')['quantity'].sum().reset_index()
                    category_summary.columns = ['Category', 'Total Quantity']

                    if not category_summary.empty:
                        st.bar_chart(category_summary.set_index('Category'))
                    else:
                        st.info("No data available for chart")

                # Stock In vs Stock Out comparison
                st.markdown("**Stock In vs Stock Out by Category**")
                category_type_summary = filtered_df.groupby(['category', 'transaction_type'])['quantity'].sum().reset_index()
                category_type_pivot = category_type_summary.pivot(index='category', columns='transaction_type', values='quantity').fillna(0)

                if not category_type_pivot.empty:
                    st.bar_chart(category_type_pivot)
                else:
                    st.info("No data available for chart")

                st.markdown("---")

                # Detailed transaction table
                st.subheader("Detailed Transactions")
                display_df = filtered_df.copy()
                display_df['quantity'] = display_df['quantity'].apply(lambda x: f"{x:,.0f}")
                display_df['date'] = display_df['date'].dt.strftime('%Y-%m-%d')
                display_df = display_df.sort_values('date', ascending=False)

                st.dataframe(
                    display_df,
                    use_container_width=True,
                    hide_index=True
                )

                # Download report as CSV and Excel
                col1, col2 = st.columns(2)

                with col1:
                    csv = filtered_df.to_csv(index=False)
                    st.download_button(
                        label="📥 Download Report as CSV",
                        data=csv,
                        file_name=f"stock_report_{start_date}_{end_date}.csv",
                        mime="text/csv",
                        use_container_width=True
                    )

                with col2:
                    # Create Excel file
                    buffer = BytesIO()
                    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                        filtered_df.to_excel(writer, index=False, sheet_name='Transactions')
                    buffer.seek(0)

                    st.download_button(
                        label="📊 Download Report as Excel",
                        data=buffer,
                        file_name=f"stock_report_{start_date}_{end_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True
                    )

            else:
                st.info("No transactions found for the selected criteria.")
        else:
            st.info("No transactions recorded yet.")

if __name__ == "__main__":
    main()
