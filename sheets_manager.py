import os
import pandas as pd
from typing import Optional, Dict, List

# Optional imports - only needed if Google Sheets is configured
try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False
    gspread = None
    Credentials = None

try:
    import streamlit as st
except ImportError:
    st = None

class SheetsManager:
    """Manages Google Sheets API operations."""
    
    # Define the scope for Google Sheets API
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    
    def __init__(self, credentials_path: Optional[str] = None, spreadsheet_id: Optional[str] = None):
        """
        Initialize Google Sheets manager.
        
        Args:
            credentials_path: Path to Google service account credentials JSON file
            spreadsheet_id: Google Sheets spreadsheet ID (from the URL)
        """
        self.credentials_path = credentials_path or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), 
            "data", 
            "credentials.json"
        )
        # Try multiple sources for spreadsheet ID:
        # 1. Passed as parameter
        # 2. Environment variable
        # 3. Streamlit secrets (for Streamlit Cloud) - checked lazily
        # 4. Config file
        if spreadsheet_id:
            self.spreadsheet_id = spreadsheet_id
        else:
            self.spreadsheet_id = os.getenv("GOOGLE_SHEETS_ID")
            
            # Try config file first (before Streamlit secrets to avoid context issues)
            if not self.spreadsheet_id:
                config_file = os.path.join(
                    os.path.dirname(os.path.abspath(__file__)),
                    "data",
                    "config.txt"
                )
                if os.path.exists(config_file):
                    try:
                        with open(config_file, 'r') as f:
                            for line in f:
                                line = line.strip()
                                if line.startswith('GOOGLE_SHEETS_ID='):
                                    self.spreadsheet_id = line.split('=', 1)[1].strip().strip('"').strip("'")
                                    break
                    except Exception:
                        pass
        self.client = None
        self.spreadsheet = None
        # Don't initialize client here - wait until we have spreadsheet_id
        # This avoids accessing st.secrets too early
        if self.spreadsheet_id:
            self._initialize_client()
    
    def _initialize_client(self):
        """Initialize Google Sheets client.

        Order of credential sources:
        1) Streamlit secrets as dict table [gcp_service_account]
        2) Streamlit secrets JSON string GOOGLE_SERVICE_ACCOUNT_JSON
        3) credentials.json file on disk
        """
        if not GSPREAD_AVAILABLE:
            # gspread not installed - can't use Google Sheets
            # Only show warning once to avoid spam
            try:
                if st and hasattr(st, 'session_state'):
                    if 'gspread_warning_shown' not in st.session_state:
                        st.warning(
                            "⚠️ **Google Sheets packages not installed**\n\n"
                            "To fix this:\n"
                            "1. Make sure `requirements.txt` is in your repo root\n"
                            "2. Commit and push `requirements.txt` to GitHub\n"
                            "3. In Streamlit Cloud: Settings → Reboot app\n"
                            "4. Check deployment logs for installation errors\n\n"
                            "The app will use local CSV files until packages are installed."
                        )
                        st.session_state['gspread_warning_shown'] = True
            except:
                pass
            self.client = None
            self.spreadsheet = None
            return
        
        try:
            creds = None
            self.service_account_email = None
            # 1) Try Streamlit secrets: table [gcp_service_account]
            try:
                if st and hasattr(st, 'secrets') and 'gcp_service_account' in st.secrets:
                    info_dict = dict(st.secrets['gcp_service_account'])
                    creds = Credentials.from_service_account_info(info_dict, scopes=self.SCOPES)
                    self.service_account_email = info_dict.get('client_email')
            except Exception:
                # ignore; will try other sources
                pass

            # 2) Try Streamlit secrets: JSON string GOOGLE_SERVICE_ACCOUNT_JSON
            if creds is None:
                try:
                    if st and hasattr(st, 'secrets') and 'GOOGLE_SERVICE_ACCOUNT_JSON' in st.secrets:
                        import json
                        json_str = st.secrets['GOOGLE_SERVICE_ACCOUNT_JSON']
                        info = json.loads(json_str)
                        creds = Credentials.from_service_account_info(info, scopes=self.SCOPES)
                        self.service_account_email = info.get('client_email')
                except Exception:
                    pass

            # 3) Fallback to credentials.json file
            if creds is None:
                if os.path.exists(self.credentials_path):
                    import json
                    try:
                        with open(self.credentials_path, 'r') as f:
                            info = json.load(f)
                            self.service_account_email = info.get('client_email')
                    except Exception:
                        self.service_account_email = None
                    creds = Credentials.from_service_account_file(self.credentials_path, scopes=self.SCOPES)
                else:
                    # Only show warning if not in session state (to avoid repetition)
                    try:
                        if st and hasattr(st, 'session_state') and 'sheets_warning_shown' not in st.session_state:
                            st.info(
                                "ℹ️ **Google Sheets not configured** - Using local CSV files for now.\n\n"
                                "To enable Google Sheets storage (choose ONE):\n"
                                "- Add service account JSON to Streamlit Secrets as table [gcp_service_account]\n"
                                "- OR add GOOGLE_SERVICE_ACCOUNT_JSON with the full JSON string\n"
                                "- OR upload credentials.json into the app's data/ folder\n\n"
                                "Also set GOOGLE_SHEETS_ID."
                            )
                            st.session_state['sheets_warning_shown'] = True
                    except (NameError, AttributeError, RuntimeError):
                        print("INFO: Google Sheets credentials not found. Using local CSV files.")
                    return
            
            # Create gspread client
            self.client = gspread.authorize(creds)
            
            # Open spreadsheet if ID is provided
            if self.spreadsheet_id:
                self.spreadsheet = self.client.open_by_key(self.spreadsheet_id)
            else:
                # Only show warning in Streamlit context
                try:
                    if st and hasattr(st, 'warning'):
                        st.warning(
                            "⚠️ Google Sheets ID not configured. Set GOOGLE_SHEETS_ID environment variable "
                            "or pass it to SheetsManager constructor."
                        )
                except (NameError, AttributeError, RuntimeError):
                    # Not in Streamlit context, just continue
                    pass
                
        except Exception as e:
            # Show error in Streamlit context, otherwise just print
            try:
                st.error(f"Error initializing Google Sheets client: {str(e)}")
            except (NameError, AttributeError, RuntimeError):
                print(f"ERROR: Error initializing Google Sheets client: {str(e)}")
            self.client = None
            self.spreadsheet = None
    
    def _get_spreadsheet_id(self) -> Optional[str]:
        """Lazily get spreadsheet ID, trying Streamlit secrets if not already set."""
        if self.spreadsheet_id:
            return self.spreadsheet_id
        
        # Try Streamlit secrets (lazy access - only when needed)
        try:
            import streamlit as st
            if hasattr(st, 'secrets'):
                try:
                    # Try to get the secret value directly
                    # st.secrets can be accessed like a dict or attribute
                    secret_value = None
                    try:
                        # Try dict-like access first
                        secret_value = st.secrets.get('GOOGLE_SHEETS_ID') or st.secrets['GOOGLE_SHEETS_ID']
                    except (KeyError, AttributeError, TypeError):
                        # Try attribute access
                        try:
                            secret_value = getattr(st.secrets, 'GOOGLE_SHEETS_ID', None)
                        except (AttributeError, RuntimeError):
                            pass
                    
                    if secret_value:
                        self.spreadsheet_id = str(secret_value).strip()
                        return self.spreadsheet_id
                except (RuntimeError, AttributeError, KeyError, TypeError) as e:
                    # Not in Streamlit context or secrets not available
                    # Silently fail - this is expected if not in Streamlit context
                    pass
        except (NameError, ImportError):
            pass
        
        return self.spreadsheet_id
    
    def is_configured(self) -> bool:
        """Check if Google Sheets is properly configured."""
        # Update spreadsheet_id from secrets if needed
        if not self.spreadsheet_id:
            self.spreadsheet_id = self._get_spreadsheet_id()
        
        # If we now have a spreadsheet_id but no client, try to initialize
        if self.spreadsheet_id and not self.client:
            self._initialize_client()
        
        return self.client is not None and self.spreadsheet is not None

    def get_service_account_email(self) -> Optional[str]:
        """Return detected service account email if available."""
        return getattr(self, 'service_account_email', None)
    
    def get_or_create_worksheet(self, sheet_name: str, headers: List[str]):
        """
        Get existing worksheet or create it if it doesn't exist.
        
        Args:
            sheet_name: Name of the worksheet
            headers: List of column headers
            
        Returns:
            Worksheet object or None if error
        """
        if not self.is_configured():
            return None
        
        try:
            # Try to get existing worksheet
            try:
                worksheet = self.spreadsheet.worksheet(sheet_name)
                # Ensure headers exist
                existing_headers = worksheet.row_values(1)
                if not existing_headers or existing_headers != headers:
                    # Update headers if they don't match
                    worksheet.clear()
                    worksheet.append_row(headers)
                return worksheet
            except Exception as e:
                # Check if it's a WorksheetNotFound error
                error_name = str(type(e).__name__)
                error_msg = str(e).lower()
                if 'WorksheetNotFound' in error_name or 'not found' in error_msg:
                    # Create new worksheet
                    worksheet = self.spreadsheet.add_worksheet(
                        title=sheet_name,
                        rows=1000,
                        cols=len(headers)
                    )
                    worksheet.append_row(headers)
                    return worksheet
                else:
                    # Re-raise other exceptions
                    raise
        except Exception as e:
            # Handle any other errors
            try:
                if st and hasattr(st, 'error'):
                    st.error(f"Error getting/creating worksheet '{sheet_name}': {str(e)}")
            except:
                print(f"ERROR: Error getting/creating worksheet '{sheet_name}': {str(e)}")
            return None
    
    def read_dataframe(self, sheet_name: str, headers: List[str]) -> pd.DataFrame:
        """
        Read data from Google Sheet into pandas DataFrame.
        
        Args:
            sheet_name: Name of the worksheet
            headers: Expected column headers
            
        Returns:
            DataFrame with the data
        """
        if not self.is_configured():
            return pd.DataFrame(columns=headers)
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if worksheet is None:
                return pd.DataFrame(columns=headers)
            
            # Get all values
            values = worksheet.get_all_values()
            
            if not values or len(values) <= 1:
                # Only headers or empty
                return pd.DataFrame(columns=headers)
            
            # First row should be headers
            df = pd.DataFrame(values[1:], columns=headers)
            
            # Clean empty rows
            df = df.dropna(how='all')
            
            return df
            
        except Exception as e:
            st.error(f"Error reading from sheet '{sheet_name}': {str(e)}")
            return pd.DataFrame(columns=headers)
    
    def write_dataframe(self, sheet_name: str, df: pd.DataFrame, headers: List[str]):
        """
        Write DataFrame to Google Sheet.
        
        Args:
            sheet_name: Name of the worksheet
            df: DataFrame to write
            headers: Column headers
        """
        if not self.is_configured():
            st.error("Google Sheets not configured. Cannot write data.")
            return False
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if worksheet is None:
                return False
            
            # Clear existing data (keep headers)
            worksheet.clear()
            worksheet.append_row(headers)
            
            # Convert DataFrame to list of lists
            if not df.empty:
                values = df[headers].values.tolist()
                if values:
                    worksheet.append_rows(values)
            
            return True
            
        except Exception as e:
            st.error(f"Error writing to sheet '{sheet_name}': {str(e)}")
            return False
    
    def append_row(self, sheet_name: str, row_data: List, headers: List[str]) -> bool:
        """
        Append a single row to Google Sheet.
        
        Args:
            sheet_name: Name of the worksheet
            row_data: List of values for the row
            headers: Column headers
        """
        if not self.is_configured():
            return False
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if worksheet is None:
                return False
            
            # Ensure row_data matches headers length
            while len(row_data) < len(headers):
                row_data.append("")
            
            worksheet.append_row(row_data[:len(headers)])
            return True
            
        except Exception as e:
            st.error(f"Error appending row to sheet '{sheet_name}': {str(e)}")
            return False
    
    def update_row(self, sheet_name: str, row_index: int, row_data: List, headers: List[str]) -> bool:
        """
        Update a specific row in Google Sheet (1-indexed, including header).
        
        Args:
            sheet_name: Name of the worksheet
            row_index: Row number (1-indexed, row 1 is headers)
            row_data: List of values for the row
            headers: Column headers
        """
        if not self.is_configured():
            return False
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, headers)
            if worksheet is None:
                return False
            
            # Ensure row_data matches headers length
            while len(row_data) < len(headers):
                row_data.append("")
            
            # Update row (row_index is 1-indexed, so row 2 is first data row)
            worksheet.update(f"A{row_index}", [row_data[:len(headers)]], value_input_option='RAW')
            return True
            
        except Exception as e:
            st.error(f"Error updating row in sheet '{sheet_name}': {str(e)}")
            return False
    
    def delete_rows(self, sheet_name: str, row_indices: List[int]) -> bool:
        """
        Delete rows from Google Sheet (1-indexed, including header).
        
        Args:
            sheet_name: Name of the worksheet
            row_indices: List of row numbers to delete (1-indexed)
        """
        if not self.is_configured():
            return False
        
        try:
            worksheet = self.get_or_create_worksheet(sheet_name, [])
            if worksheet is None:
                return False
            
            # Sort indices descending to avoid index shifting issues
            sorted_indices = sorted(row_indices, reverse=True)
            
            for row_idx in sorted_indices:
                worksheet.delete_rows(row_idx)
            
            return True
            
        except Exception as e:
            st.error(f"Error deleting rows from sheet '{sheet_name}': {str(e)}")
            return False
    
    def create_spreadsheet(self, title: str) -> Optional[str]:
        """
        Create a new Google Spreadsheet.
        
        Args:
            title: Title of the spreadsheet
            
        Returns:
            Spreadsheet ID if successful, None otherwise
        """
        if not self.client:
            st.error("Google Sheets client not initialized. Cannot create spreadsheet.")
            return None
        
        try:
            spreadsheet = self.client.create(title)
            # Share with service account email if needed (optional)
            return spreadsheet.id
        except Exception as e:
            st.error(f"Error creating spreadsheet: {str(e)}")
            return None



